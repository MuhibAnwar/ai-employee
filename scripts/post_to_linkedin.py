#!/usr/bin/env python3
"""
post_to_linkedin.py — LinkedIn text post via OAuth 2.0 (primary) or linkedin-api (fallback)

Usage:
    python scripts/post_to_linkedin.py "Your post text here"
    python scripts/post_to_linkedin.py --file vault/Approved/LINKEDIN_POST_xxx.md

Exit codes:
    0  — post published successfully
    2  — API limitation (post content printed for manual copy-paste)
    1  — configuration error (missing credentials)

OAuth 2.0 (primary path):
    Set LINKEDIN_ACCESS_TOKEN in .env.
    The token must have the w_member_social scope.
    Get one via: https://www.linkedin.com/developers/apps → OAuth 2.0 tools → Generate token

Cookie-based fallback:
    linkedin-api uses cookie-based auth (unofficial voyager API).
    LinkedIn restricts content creation (POST /contentcreation/normShares)
    to OAuth 2.0 sessions, so this fallback typically returns 401 for posting.
"""

import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path

import urllib.request
import urllib.error

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "watchers"))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

try:
    from linkedin_api import Linkedin
    LINKEDIN_AVAILABLE = True
except ImportError:
    LINKEDIN_AVAILABLE = False


def extract_post_content(md_path: Path) -> str:
    """Extract post text from a Pending_Approval / Approved .md file.

    Looks for a '## Post Content' or '## Content' section and returns
    everything up to the next '---' or '##' heading.
    """
    text = md_path.read_text(encoding="utf-8")
    # Match the content block after ## Post Content or ## Content
    m = re.search(
        r"^##\s+(?:Post\s+)?Content\s*\n(.*?)(?=\n##|\n---|\Z)",
        text,
        re.DOTALL | re.MULTILINE,
    )
    if m:
        return m.group(1).strip()
    return ""


def _linkedin_request(method: str, url: str, token: str, body: dict | None = None) -> dict:
    """Send an authenticated LinkedIn API request. Returns (status_code, parsed_body)."""
    data = json.dumps(body).encode() if body else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode()
            return {"status": resp.status, "body": json.loads(raw) if raw else {}}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            body_parsed = json.loads(raw)
        except Exception:
            body_parsed = {"raw": raw[:300]}
        return {"status": e.code, "body": body_parsed}


def get_member_urn(token: str) -> str | None:
    """Return the LinkedIn member URN (urn:li:person:<id>) for the token owner."""
    result = _linkedin_request("GET", "https://api.linkedin.com/v2/userinfo", token)
    if result["status"] != 200:
        return None
    sub = result["body"].get("sub", "")
    if not sub:
        return None
    return f"urn:li:person:{sub}"


def try_oauth_post(text: str) -> dict:
    """Post to LinkedIn using OAuth 2.0 (ugcPosts endpoint).

    Requires LINKEDIN_ACCESS_TOKEN in .env with w_member_social scope.

    Returns:
        {"success": True, "urn": "urn:li:ugcPost:..."}
        {"success": False, "error": "...", "status": int}
    """
    token = os.getenv("LINKEDIN_ACCESS_TOKEN", "").strip()
    if not token:
        return {"success": False, "error": "LINKEDIN_ACCESS_TOKEN not set in .env", "status": 0}

    # Step 1: resolve member URN
    member_urn = get_member_urn(token)
    if not member_urn:
        return {"success": False, "error": "Could not fetch member URN from /v2/userinfo — token may be expired or lack profile scope", "status": 0}

    print(f"  Member URN: {member_urn}")

    # Step 2: publish ugcPost
    payload = {
        "author": member_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }

    result = _linkedin_request("POST", "https://api.linkedin.com/v2/ugcPosts", token, payload)

    if result["status"] in (200, 201):
        post_urn = result["body"].get("id", "")
        return {"success": True, "urn": post_urn}
    else:
        body = result["body"]
        message = body.get("message", body.get("serviceErrorCode", str(body)))
        return {
            "success": False,
            "error": f"HTTP {result['status']}: {message}",
            "status": result["status"],
        }


def try_api_post(text: str) -> dict:
    """Attempt to publish via linkedin-api voyager endpoint.

    Returns:
        {"success": True, "urn": "..."}   on success
        {"success": False, "error": "...", "status": int}  on failure
    """
    username = os.getenv("LINKEDIN_USERNAME", "")
    password = os.getenv("LINKEDIN_PASSWORD", "")

    if not username or not password:
        return {"success": False, "error": "LINKEDIN_USERNAME or LINKEDIN_PASSWORD not set in .env"}

    # Authenticate with timeout
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(Linkedin, username, password)
            api = future.result(timeout=30)
    except FuturesTimeoutError:
        return {"success": False, "error": "Authentication timed out after 30s"}
    except Exception as e:
        return {"success": False, "error": f"Authentication failed: {e}"}

    cookies = dict(api.client.session.cookies)
    jsessionid = cookies.get("JSESSIONID", "").replace('"', "")

    # Attempt POST via voyager content creation endpoint
    # NOTE: This returns 401 when LinkedIn enforces OAuth for write operations.
    payload = json.dumps({
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
    })

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(
                api._post,
                "/contentcreation/normShares",
                headers={
                    "csrf-token": jsessionid,
                    "content-type": "application/json",
                    "accept": "application/vnd.linkedin.normalized+json+2.1",
                    "x-restli-protocol-version": "2.0.0",
                },
                data=payload,
            )
            res = future.result(timeout=30)
    except FuturesTimeoutError:
        return {"success": False, "error": "API call timed out after 30s", "status": 0}
    except Exception as e:
        return {"success": False, "error": str(e), "status": 0}

    if res.status_code in (200, 201):
        try:
            data = res.json()
            urn = data.get("urn", data.get("data", {}).get("urn", ""))
        except Exception:
            urn = ""
        return {"success": True, "urn": urn}
    else:
        return {
            "success": False,
            "error": f"HTTP {res.status_code} from LinkedIn API",
            "status": res.status_code,
            "body": res.text[:300],
        }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Post to LinkedIn via linkedin-api")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("text", nargs="?", help="Post text (positional)")
    group.add_argument("--file", type=Path, help="Path to approved .md file")
    args = parser.parse_args()

    if args.file:
        if not args.file.exists():
            print(f"ERROR: file not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        post_text = extract_post_content(args.file)
        if not post_text:
            print(f"ERROR: no '## Post Content' or '## Content' section found in {args.file}", file=sys.stderr)
            sys.exit(1)
    else:
        post_text = args.text

    # ── Try OAuth 2.0 first (official API, w_member_social scope) ──────────
    oauth_token = os.getenv("LINKEDIN_ACCESS_TOKEN", "").strip()
    if oauth_token:
        print(f"Trying OAuth 2.0 post ({len(post_text)} chars)...")
        result = try_oauth_post(post_text)
        if result["success"]:
            print(f"SUCCESS: Post published via OAuth 2.0!")
            if result.get("urn"):
                print(f"URN: {result['urn']}")
            sys.exit(0)
        else:
            print(f"OAuth failed: {result['error']}")
            print("Falling back to cookie-based method...\n")
    else:
        print("LINKEDIN_ACCESS_TOKEN not set — skipping OAuth, trying cookie-based method...")

    # ── Fallback: cookie-based linkedin-api ────────────────────────────────
    if not LINKEDIN_AVAILABLE:
        print("ERROR: linkedin-api not installed. Run: pip install linkedin-api", file=sys.stderr)
        print("\n" + "=" * 60)
        print("POST CONTENT (copy and paste to LinkedIn manually):")
        print("=" * 60)
        print(post_text)
        print("=" * 60)
        sys.exit(2)

    print(f"Attempting cookie-based LinkedIn API post ({len(post_text)} chars)...")
    result = try_api_post(post_text)

    if result["success"]:
        print(f"SUCCESS: Post published!")
        if result.get("urn"):
            print(f"URN: {result['urn']}")
        sys.exit(0)
    else:
        # Graceful failure — print content for manual paste
        print(f"\nAPI_LIMITATION: {result['error']}")
        if result.get("status") == 401:
            print(
                "\nNote: LinkedIn's voyager API restricts content creation to OAuth 2.0\n"
                "sessions (w_member_social scope). Cookie-based auth works for reading\n"
                "but not for posting. Set LINKEDIN_ACCESS_TOKEN in .env to use the\n"
                "official API instead.\n"
            )
        print("\n" + "=" * 60)
        print("POST CONTENT (copy and paste to LinkedIn manually):")
        print("=" * 60)
        print(post_text)
        print("=" * 60)
        sys.exit(2)


if __name__ == "__main__":
    main()
