"""
facebook_watcher.py - Facebook Notifications Watcher (Gold Tier)

Uses requests + session cookies loaded from facebook_storage.json.
Falls back to WAITING mode if no session file is found or requests fail.

Usage:
    python watchers/facebook_watcher.py --vault ./vault
    python watchers/facebook_watcher.py --vault ./vault --dry-run

Setup:
    1. Export your Facebook session cookies to secrets/facebook_storage.json
       Use a browser extension (e.g. EditThisCookie) to export cookies as JSON,
       or use browser developer tools → Application → Cookies → export.
    2. Set FACEBOOK_SESSION_PATH in .env (optional, default: secrets/facebook_storage.json)

Keyword filtering (creates action file if ANY match):
    urgent, invoice, payment, order, complaint, question, dm, message,
    refund, support, client, pricing, proposal

Requirements:
    pip install requests python-dotenv
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))

PROJECT_ROOT = Path(__file__).resolve().parent.parent

from base_watcher import BaseWatcher

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


ACTION_KEYWORDS = {
    "urgent", "asap", "invoice", "payment", "order", "complaint",
    "question", "dm", "message", "refund", "support", "client",
    "pricing", "proposal", "deadline", "follow up",
}

SEEN_FILE = PROJECT_ROOT / "secrets" / "facebook_seen.txt"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


class FacebookWatcher(BaseWatcher):
    """
    Watches Facebook notifications using requests + stored session cookies.
    Uses mbasic.facebook.com for simpler, more parseable HTML responses.

    Gold Tier Requirement:
      "Facebook + Instagram watcher + posting"
    """

    def __init__(self, vault_path: str, dry_run: bool = False, check_interval: int = 300):
        super().__init__(vault_path, check_interval=check_interval)
        self.dry_run = dry_run
        self.session_path = Path(
            os.getenv("FACEBOOK_SESSION_PATH", str(PROJECT_ROOT / "secrets" / "facebook_storage.json"))
        )
        self._session = None
        SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)

    # ── Deduplication ─────────────────────────────────────────────────────────

    def _load_seen(self) -> set:
        if SEEN_FILE.exists():
            return set(SEEN_FILE.read_text(encoding="utf-8").splitlines())
        return set()

    def _mark_seen(self, key: str):
        with SEEN_FILE.open("a", encoding="utf-8") as f:
            f.write(key + "\n")

    @staticmethod
    def _notification_key(text: str) -> str:
        return text.strip().lower()[:80]

    # ── Session management ────────────────────────────────────────────────────

    def _get_session(self) -> "requests.Session":
        """Build a requests.Session with cookies from the session cookies JSON file."""
        if self._session is not None:
            return self._session

        session = requests.Session()
        session.headers.update(_HEADERS)

        storage = json.loads(self.session_path.read_text(encoding="utf-8"))
        for cookie in storage.get("cookies", []):
            domain = cookie.get("domain", "")
            # Strip leading dot for requests cookie jar
            domain = domain.lstrip(".")
            session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=domain,
                path=cookie.get("path", "/"),
            )

        self._session = session
        return session

    # ── BaseWatcher interface ─────────────────────────────────────────────────

    def check_for_updates(self) -> list:
        if self.dry_run:
            self.logger.info("[DRY_RUN] Skipping Facebook request — returning empty list.")
            return []

        if not REQUESTS_AVAILABLE:
            raise RuntimeError("requests library not installed. Run: pip install requests")

        if not self.session_path.exists():
            self.logger.warning(
                f"[WAITING] Facebook session file not found: {self.session_path}. "
                "Export cookies from your browser to that path."
            )
            return []

        seen = self._load_seen()
        new_items = []

        try:
            session = self._get_session()

            # Use mbasic for simpler HTML
            resp = session.get(
                "https://mbasic.facebook.com/notifications/",
                timeout=20,
                allow_redirects=True,
            )

            # Session expired if redirected to login
            if "login" in resp.url or "checkpoint" in resp.url:
                self.logger.warning(
                    f"Facebook session expired. Re-export cookies to: {self.session_path}"
                )
                self._session = None
                return []

            if resp.status_code != 200:
                self.logger.warning(f"Facebook returned HTTP {resp.status_code}")
                return []

            html = resp.text

            # Extract notification anchor tags and their text from mbasic HTML
            # mbasic notifications are in <td> blocks with <a href> links
            # Pattern: find notification item links inside the notifications list
            pattern = re.compile(
                r'<a\s+href="(/notifications/[^"]+)"[^>]*>(.*?)</a>',
                re.DOTALL | re.IGNORECASE,
            )
            matches = pattern.findall(html)

            for href, raw_text in matches[:30]:
                # Strip HTML tags from raw_text
                text = re.sub(r"<[^>]+>", " ", raw_text).strip()
                text = re.sub(r"\s+", " ", text)
                if not text or len(text) < 5:
                    continue

                key = self._notification_key(text)
                if key in seen:
                    continue

                text_lower = text.lower()
                if not any(kw in text_lower for kw in ACTION_KEYWORDS):
                    self._mark_seen(key)
                    continue

                url = "https://www.facebook.com" + href.split("?")[0]
                new_items.append({
                    "text": text[:500],
                    "url": url,
                    "key": key,
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                })
                self._mark_seen(key)

        except Exception as e:
            self.logger.error(f"Facebook request error: {e}")
            self._session = None

        if new_items:
            self.logger.info(f"Found {len(new_items)} relevant Facebook notification(s).")
        else:
            self.logger.debug("No new relevant Facebook notifications.")

        return new_items

    def create_action_file(self, item: dict) -> Path:
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y%m%dT%H%M%S")
        priority = self._classify_priority(item["text"])
        safe = "".join(
            c if c.isalnum() or c in "-_" else "_"
            for c in item["text"][:40]
        ).strip("_")

        content = f"""---
type: facebook_notification
source: {item['url']}
received: {now.isoformat()}
priority: {priority}
status: pending
watcher: FacebookWatcher
detected_at: {item['detected_at']}
---

# Action Required: Facebook Notification

A relevant Facebook notification was detected that may require a response.

## Notification

> {item['text']}

## Details

| Field | Value |
|-------|-------|
| Priority | **{priority.upper()}** |
| Detected | {now.strftime("%Y-%m-%d %H:%M:%S UTC")} |
| Source URL | {item['url']} |

## Suggested Actions

- [ ] Visit the Facebook notification link to review the full context
- [ ] Determine if a reply or post is needed
- [ ] If a public post is appropriate → create file in `vault/Pending_Approval/` (action: post_facebook)
- [ ] If a direct reply → create approval file for human review
- [ ] Log outcome and move this file to `vault/Done/`

---
*Created by FacebookWatcher at {now.strftime("%Y-%m-%d %H:%M:%S UTC")}*
"""
        action_file = self.needs_action / f"SOCIAL_FB_{ts}_{safe}.md"
        action_file.write_text(content, encoding="utf-8")
        self.log_action(
            action_type="facebook_notification_detected",
            source=item["url"],
            result="success",
            notes=f"Action file created: {action_file.name}",
        )
        return action_file

    def _classify_priority(self, text: str) -> str:
        lower = text.lower()
        if any(kw in lower for kw in {"urgent", "asap", "deadline", "complaint", "refund"}):
            return "urgent"
        if any(kw in lower for kw in {"invoice", "payment", "order", "pricing", "proposal", "client"}):
            return "high"
        return "normal"

    def run(self):
        if self.dry_run:
            self.logger.info("[DRY_RUN] FacebookWatcher started — no requests will be made.")
            self.check_for_updates()
            self.logger.info("[DRY_RUN] Exiting after one cycle.")
            return

        if not REQUESTS_AVAILABLE:
            self.logger.error("requests library not installed. Run: pip install requests")
            return

        self.logger.info(f"Starting FacebookWatcher (interval={self.check_interval}s)")

        if not self.session_path.exists():
            self.logger.warning(
                f"[WAITING] Session file not found: {self.session_path}. "
                "Export cookies from your browser to that path. Sleeping until present."
            )
            while not self.session_path.exists():
                try:
                    time.sleep(60)
                except KeyboardInterrupt:
                    self.logger.info("FacebookWatcher stopped by user.")
                    return
            self.logger.info("Session file found. Starting FacebookWatcher.")

        while True:
            try:
                items = self.check_for_updates()
                for item in items:
                    try:
                        path = self.create_action_file(item)
                        self.logger.info(f"Created action file: {path.name}")
                    except Exception as e:
                        self.logger.error(f"Failed to create action file: {e}")
                        self.log_action("create_action_file", item.get("url", "?"), "error", str(e))
                time.sleep(self.check_interval)
            except KeyboardInterrupt:
                self.logger.info("FacebookWatcher stopped by user.")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error: {e}")
                self.log_action("watcher_loop", "facebook_main", "error", str(e))
                time.sleep(self.check_interval)


def main():
    parser = argparse.ArgumentParser(
        description="Facebook Notifications Watcher for AI Employee (Gold Tier)"
    )
    parser.add_argument("--vault", default=os.getenv("VAULT_PATH", "./vault"))
    parser.add_argument(
        "--dry-run", action="store_true",
        default=os.getenv("DRY_RUN", "false").lower() == "true",
        help="Log intent without making requests",
    )
    parser.add_argument("--interval", type=int, default=300)
    args = parser.parse_args()

    vault_path = Path(args.vault).resolve()
    if not vault_path.exists():
        print(f"ERROR: Vault path does not exist: {vault_path}")
        sys.exit(1)

    FacebookWatcher(
        vault_path=str(vault_path),
        dry_run=args.dry_run,
        check_interval=args.interval,
    ).run()


if __name__ == "__main__":
    main()
