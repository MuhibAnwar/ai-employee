"""
instagram_watcher.py - Instagram Activity Watcher (Gold Tier)

Uses instagrapi library to check the news inbox (likes, comments, mentions).
Falls back to WAITING mode if no session file is found.

Usage:
    python watchers/instagram_watcher.py --vault ./vault
    python watchers/instagram_watcher.py --vault ./vault --dry-run

Setup:
    1. Install: pip install instagrapi python-dotenv
    2. Run once interactively to create the session file:
         python -c "
         from instagrapi import Client
         cl = Client()
         cl.login('YOUR_USERNAME', 'YOUR_PASSWORD')
         cl.dump_settings('secrets/instagram_session.json')
         print('Session saved.')
         "
    3. Set INSTAGRAM_SESSION_PATH in .env (optional)

Requirements:
    pip install instagrapi python-dotenv
"""

import argparse
import json
import os
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
    from instagrapi import Client as InstaClient
    INSTAGRAPI_AVAILABLE = True
except ImportError:
    INSTAGRAPI_AVAILABLE = False


ACTION_KEYWORDS = {
    "urgent", "asap", "invoice", "payment", "order", "complaint",
    "question", "dm", "collab", "collaboration", "sponsor", "paid",
    "pricing", "rate", "deal", "refund", "support", "client", "business",
}

SEEN_FILE = PROJECT_ROOT / "secrets" / "instagram_seen.txt"


class InstagramWatcher(BaseWatcher):
    """
    Watches Instagram DMs and activity using instagrapi (no browser required).

    Gold Tier Requirement:
      "Facebook + Instagram watcher + posting"
    """

    def __init__(self, vault_path: str, dry_run: bool = False, check_interval: int = 300):
        super().__init__(vault_path, check_interval=check_interval)
        self.dry_run = dry_run
        self.session_path = Path(
            os.getenv("INSTAGRAM_SESSION_PATH", str(PROJECT_ROOT / "secrets" / "instagram_session.json"))
        )
        self._client = None
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

    # ── Session format validation ──────────────────────────────────────────────

    def _is_instagrapi_session(self) -> bool:
        """
        Return True only if the session file looks like an instagrapi dump.
        Browser session exports have {'cookies': [...], 'origins': [...]}
        whereas instagrapi dumps have keys like 'uuids', 'mid', 'ig_did', etc.
        """
        try:
            data = json.loads(self.session_path.read_text(encoding="utf-8"))
            # Browser session export keys — not an instagrapi session
            if set(data.keys()) <= {"cookies", "origins"}:
                return False
            # instagrapi session must have at least one of these
            return bool(
                data.get("uuids") or data.get("mid") or data.get("ig_did")
                or data.get("authorization_data")
            )
        except Exception:
            return False

    # ── Client (lazy init) ────────────────────────────────────────────────────

    def _get_client(self) -> "InstaClient":
        """Return a cached instagrapi Client loaded from the session file."""
        if self._client is None:
            cl = InstaClient()
            cl.load_settings(str(self.session_path))
            self._client = cl
        return self._client

    # ── BaseWatcher interface ─────────────────────────────────────────────────

    def check_for_updates(self) -> list:
        if self.dry_run:
            self.logger.info("[DRY_RUN] Skipping Instagram API call — returning empty list.")
            return []

        if not INSTAGRAPI_AVAILABLE:
            raise RuntimeError(
                "instagrapi is not installed.\n"
                "Run: pip install instagrapi  (or: uv add instagrapi)"
            )

        if not self.session_path.exists():
            self.logger.warning(
                f"[WAITING] Instagram session file not found: {self.session_path}."
            )
            return []

        if not self._is_instagrapi_session():
            self.logger.warning(
                f"[WAITING] {self.session_path.name} is not an instagrapi session file "
                "(looks like a browser session export, not an instagrapi dump). "
                "Create one with: from instagrapi import Client; "
                "cl=Client(); cl.login('USER','PASS'); "
                "cl.dump_settings('secrets/instagram_session.json') "
                "then set INSTAGRAM_SESSION_PATH=secrets/instagram_session.json in .env"
            )
            return []

        seen = self._load_seen()
        new_items = []

        try:
            cl = self._get_client()

            # Check news inbox (likes, comments, follows, mentions)
            notifications = cl.news_inbox()
            for notif in notifications[:20]:
                try:
                    # instagrapi returns dict-like objects
                    text = ""
                    if isinstance(notif, dict):
                        text = (notif.get("text") or notif.get("message") or "").strip()
                    else:
                        text = (getattr(notif, "text", None) or str(notif)).strip()

                    if not text or len(text) < 3:
                        continue

                    key = self._notification_key(text)
                    if key in seen:
                        continue

                    text_lower = text.lower()
                    if not any(kw in text_lower for kw in ACTION_KEYWORDS):
                        self._mark_seen(key)
                        continue

                    url = "https://www.instagram.com/notifications/"

                    new_items.append({
                        "text": text[:500],
                        "url": url,
                        "key": key,
                        "detected_at": datetime.now(timezone.utc).isoformat(),
                    })
                    self._mark_seen(key)

                except Exception as e:
                    self.logger.debug(f"Error parsing notification: {e}")

        except Exception as e:
            self.logger.error(f"Instagram API error: {e}")
            # Reset client so next cycle reloads the session
            self._client = None

        if new_items:
            self.logger.info(f"Found {len(new_items)} relevant Instagram notification(s).")
        else:
            self.logger.debug("No new relevant Instagram notifications.")

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
type: instagram_dm
source: {item['url']}
received: {now.isoformat()}
priority: {priority}
status: pending
watcher: InstagramWatcher
detected_at: {item['detected_at']}
---

# Action Required: Instagram DM / Activity

A relevant Instagram message or notification was detected.

## Message Preview

> {item['text']}

## Details

| Field | Value |
|-------|-------|
| Priority | **{priority.upper()}** |
| Detected | {now.strftime("%Y-%m-%d %H:%M:%S UTC")} |
| Source URL | {item['url']} |

## Suggested Actions

- [ ] Open the Instagram DM/notification link to read in full
- [ ] Determine if a reply, collab, or business action is needed
- [ ] If posting to Instagram → create approval file (action: post_instagram)
- [ ] If replying → create file in `vault/Pending_Approval/`
- [ ] Log outcome and move this file to `vault/Done/`

---
*Created by InstagramWatcher at {now.strftime("%Y-%m-%d %H:%M:%S UTC")}*
"""
        action_file = self.needs_action / f"SOCIAL_IG_{ts}_{safe}.md"
        action_file.write_text(content, encoding="utf-8")
        self.log_action(
            action_type="instagram_dm_detected",
            source=item["url"],
            result="success",
            notes=f"Action file created: {action_file.name}",
        )
        return action_file

    def _classify_priority(self, text: str) -> str:
        lower = text.lower()
        if any(kw in lower for kw in {"urgent", "asap", "complaint", "refund"}):
            return "urgent"
        if any(kw in lower for kw in {"invoice", "payment", "order", "paid", "pricing", "sponsor", "deal"}):
            return "high"
        return "normal"

    def run(self):
        if self.dry_run:
            self.logger.info("[DRY_RUN] InstagramWatcher started — no API calls will be made.")
            self.check_for_updates()
            self.logger.info("[DRY_RUN] Exiting after one cycle.")
            return

        if not INSTAGRAPI_AVAILABLE:
            self.logger.error(
                "instagrapi not installed. Run: pip install instagrapi\n"
                "InstagramWatcher cannot start."
            )
            return

        self.logger.info(f"Starting InstagramWatcher (interval={self.check_interval}s)")

        if not self.session_path.exists() or not self._is_instagrapi_session():
            if self.session_path.exists():
                self.logger.warning(
                    f"[WAITING] {self.session_path.name} is not an instagrapi session. "
                    "Create a valid session: from instagrapi import Client; "
                    "cl=Client(); cl.login('USER','PASS'); "
                    "cl.dump_settings('secrets/instagram_session.json') "
                    "then set INSTAGRAM_SESSION_PATH in .env"
                )
            else:
                self.logger.warning(
                    f"[WAITING] Session file not found: {self.session_path}. "
                    "Create it by running:\n"
                    "  python -c \"from instagrapi import Client; cl = Client(); "
                    "cl.login('USER','PASS'); cl.dump_settings('secrets/instagram_session.json')\""
                )
            while not (self.session_path.exists() and self._is_instagrapi_session()):
                try:
                    time.sleep(60)
                except KeyboardInterrupt:
                    self.logger.info("InstagramWatcher stopped by user.")
                    return
            self.logger.info("Valid instagrapi session found. Starting InstagramWatcher.")

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
                self.logger.info("InstagramWatcher stopped by user.")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error: {e}")
                self.log_action("watcher_loop", "instagram_main", "error", str(e))
                time.sleep(self.check_interval)


def main():
    parser = argparse.ArgumentParser(
        description="Instagram DM / Activity Watcher for AI Employee (Gold Tier)"
    )
    parser.add_argument("--vault", default=os.getenv("VAULT_PATH", "./vault"))
    parser.add_argument(
        "--dry-run", action="store_true",
        default=os.getenv("DRY_RUN", "false").lower() == "true",
    )
    parser.add_argument("--interval", type=int, default=300)
    args = parser.parse_args()

    vault_path = Path(args.vault).resolve()
    if not vault_path.exists():
        print(f"ERROR: Vault path does not exist: {vault_path}")
        sys.exit(1)

    InstagramWatcher(
        vault_path=str(vault_path),
        dry_run=args.dry_run,
        check_interval=args.interval,
    ).run()


if __name__ == "__main__":
    main()
