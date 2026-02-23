"""
save_social_sessions.py - Capture browser sessions for social media watchers.

Opens a Chromium browser window for each platform, waits for you to log in,
then saves the session (cookies + localStorage) to secrets/*.json.

Usage:
    python setup/save_social_sessions.py                    # all 3 platforms
    python setup/save_social_sessions.py --platform facebook
    python setup/save_social_sessions.py --platform instagram
    python setup/save_social_sessions.py --platform twitter

Saved files:
    secrets/facebook_storage.json
    secrets/instagram_storage.json
    secrets/twitter_storage.json

Requirements:
    pip install playwright python-dotenv
    python -m playwright install chromium
"""

import argparse
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("ERROR: Playwright not installed.")
    print("Run: pip install playwright && python -m playwright install chromium")
    sys.exit(1)

SECRETS_DIR = Path("./secrets")

PLATFORMS = {
    "facebook": {
        "url":      "https://www.facebook.com/",
        "env_key":  "FACEBOOK_SESSION_PATH",
        "default":  SECRETS_DIR / "facebook_storage.json",
        "prompt":   (
            "  1. Log in to Facebook in the browser that just opened.\n"
            "  2. Browse to https://www.facebook.com/notifications/ to confirm you're logged in.\n"
            "  3. Come back here and press ENTER."
        ),
        "verify_url": "https://www.facebook.com/notifications/",
        "verify_text": "Notifications",
    },
    "instagram": {
        "url":      "https://www.instagram.com/accounts/login/",
        "env_key":  "INSTAGRAM_SESSION_PATH",
        "default":  SECRETS_DIR / "instagram_storage.json",
        "prompt":   (
            "  1. Log in to Instagram in the browser that just opened.\n"
            "  2. Dismiss any 'Save login info' or notification prompts.\n"
            "  3. Browse to your DM inbox: https://www.instagram.com/direct/inbox/\n"
            "  4. Come back here and press ENTER."
        ),
        "verify_url": "https://www.instagram.com/direct/inbox/",
        "verify_text": "inbox",
    },
    "twitter": {
        "url":      "https://x.com/login",
        "env_key":  "TWITTER_SESSION_PATH",
        "default":  SECRETS_DIR / "twitter_storage.json",
        "prompt":   (
            "  1. Log in to X (Twitter) in the browser that just opened.\n"
            "  2. Browse to https://x.com/notifications/mentions to confirm you're logged in.\n"
            "  3. Come back here and press ENTER."
        ),
        "verify_url": "https://x.com/notifications/mentions",
        "verify_text": "notifications",
    },
}


def capture_session(platform_key: str) -> bool:
    """
    Open a browser window for the given platform, wait for user login,
    then save the storage state. Returns True on success.
    """
    cfg = PLATFORMS[platform_key]
    save_path = Path(os.getenv(cfg["env_key"], str(cfg["default"])))
    save_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"  Platform : {platform_key.upper()}")
    print(f"  Save to  : {save_path}")
    print(f"{'=' * 60}")
    print("\nOpening browser — please follow the steps below:\n")
    print(cfg["prompt"])
    print()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=50)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        try:
            page.goto(cfg["url"], timeout=30_000)
        except Exception as e:
            print(f"  [WARN] Could not load {cfg['url']}: {e}")

        # Wait for user to log in
        input("  >>> Press ENTER when you have logged in and are ready to save the session...")

        # Save storage state (cookies + localStorage)
        try:
            context.storage_state(path=str(save_path))
            print(f"\n  ✓ Session saved → {save_path}")
        except Exception as e:
            print(f"\n  ✗ Failed to save session: {e}")
            context.close()
            browser.close()
            return False

        context.close()
        browser.close()

    # Quick verification
    print(f"  Verifying session file... ", end="", flush=True)
    if save_path.exists() and save_path.stat().st_size > 100:
        print("OK ✓")
        return True
    else:
        print("FAILED ✗ (file missing or empty)")
        return False


def print_env_hint(results: dict) -> None:
    """Print .env variable hints for successfully saved sessions."""
    print(f"\n{'=' * 60}")
    print("  Add these to your .env file:")
    print(f"{'=' * 60}")
    for platform_key, success in results.items():
        if success:
            cfg = PLATFORMS[platform_key]
            save_path = Path(os.getenv(cfg["env_key"], str(cfg["default"])))
            print(f"  {cfg['env_key']}={save_path}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Save browser sessions for Facebook, Instagram, and Twitter/X watchers"
    )
    parser.add_argument(
        "--platform",
        choices=list(PLATFORMS.keys()),
        default=None,
        help="Capture session for a single platform (default: all 3)",
    )
    args = parser.parse_args()

    platforms_to_run = [args.platform] if args.platform else list(PLATFORMS.keys())

    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║       AI Employee — Social Session Capture Tool          ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"\nPlatforms: {', '.join(p.upper() for p in platforms_to_run)}")
    print("This tool opens a real browser window so you can log in.\n")
    print("IMPORTANT: Your session data is saved to secrets/ (gitignored).")
    print("           Never commit secrets/ to version control.\n")

    results = {}
    for platform_key in platforms_to_run:
        success = capture_session(platform_key)
        results[platform_key] = success

    # Summary
    print(f"\n{'=' * 60}")
    print("  SUMMARY")
    print(f"{'=' * 60}")
    all_ok = True
    for platform_key, success in results.items():
        status = "✓ Saved" if success else "✗ Failed"
        print(f"  {platform_key.upper():12s}  {status}")
        if not success:
            all_ok = False

    if any(results.values()):
        print_env_hint(results)

    if all_ok:
        print("All sessions captured. You can now run the watchers:\n")
        print("    python scheduler/orchestrator.py --vault ./vault")
    else:
        print("\nSome sessions failed. Re-run for the failed platforms:")
        for platform_key, success in results.items():
            if not success:
                print(f"    python setup/save_social_sessions.py --platform {platform_key}")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
