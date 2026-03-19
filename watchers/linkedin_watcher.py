"""
linkedin_watcher.py - LinkedIn Notifications Watcher (Silver Tier)

Uses linkedin-api library to check conversations/messages.
Falls back to WAITING mode if credentials are missing or library unavailable.

Usage:
    python watchers/linkedin_watcher.py --vault ./vault
    python watchers/linkedin_watcher.py --vault ./vault --dry-run

Setup:
    Set LINKEDIN_USERNAME and LINKEDIN_PASSWORD in .env

Requirements:
    pip install linkedin-api python-dotenv
"""

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
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
    from linkedin_api import Linkedin
    LINKEDIN_API_AVAILABLE = True
except ImportError:
    LINKEDIN_API_AVAILABLE = False


# Keywords that trigger an action file
ACTION_KEYWORDS = {
    "pricing", "proposal", "project", "contract", "budget",
    "urgent", "asap", "deadline", "action required",
    "interview", "partnership", "collaboration", "opportunity",
    "invoice", "payment", "meeting request", "follow up",
}

SEEN_FILE = PROJECT_ROOT / "secrets" / "linkedin_seen.txt"


class LinkedInWatcher(BaseWatcher):
    """
    Watches LinkedIn conversations using linkedin-api (no browser required).

    Silver Tier Requirement:
      "Two+ watcher scripts (Gmail + LinkedIn)"
    """

    def __init__(self, vault_path: str, dry_run: bool = False, check_interval: int = 300):
        super().__init__(vault_path, check_interval=check_interval)
        self.dry_run = dry_run
        self.username = os.getenv("LINKEDIN_USERNAME", "")
        self.password = os.getenv("LINKEDIN_PASSWORD", "")
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

    # ── LinkedIn client (lazy init) ────────────────────────────────────────────

    def _get_client(self):
        """Return a cached LinkedIn client, creating it on first call.

        Linkedin.__init__ calls authenticate() immediately, which makes
        blocking HTTP requests with no timeout. We wrap it in a thread
        so we can enforce a deadline on Windows (signal.alarm not available).
        """
        if self._client is None:
            self.logger.info("Authenticating with LinkedIn API...")
            with ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(Linkedin, self.username, self.password)
                try:
                    self._client = future.result(timeout=30)
                except FuturesTimeoutError:
                    raise RuntimeError(
                        "LinkedIn authentication timed out after 30s — "
                        "check network or LinkedIn credentials"
                    )
            self.logger.info("LinkedIn API authenticated successfully.")
        return self._client

    # ── BaseWatcher interface ─────────────────────────────────────────────────

    def check_for_updates(self) -> list:
        """
        Fetch LinkedIn conversations via linkedin-api and return new relevant items.
        """
        if self.dry_run:
            self.logger.info("[DRY_RUN] Skipping LinkedIn API call — returning empty list.")
            return []

        if not LINKEDIN_API_AVAILABLE:
            raise RuntimeError(
                "linkedin-api is not installed.\n"
                "Run: pip install linkedin-api"
            )

        if not self.username or not self.password:
            self.logger.warning(
                "[WAITING] LINKEDIN_USERNAME or LINKEDIN_PASSWORD not set in .env."
            )
            return []

        seen = self._load_seen()
        new_items = []

        try:
            api = self._get_client()
            self.logger.info("Fetching LinkedIn conversations...")
            with ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(api.get_conversations)
                try:
                    convos_data = future.result(timeout=30)
                except FuturesTimeoutError:
                    raise RuntimeError(
                        "get_conversations() timed out after 30s"
                    )
            elements = convos_data.get("elements", []) if isinstance(convos_data, dict) else []

            for convo in elements[:30]:
                try:
                    # Extract the most recent event body from the conversation
                    events = convo.get("events", [])
                    if not events:
                        continue

                    latest_event = events[0]
                    event_content = latest_event.get("eventContent", {})
                    msg_event = event_content.get(
                        "com.linkedin.voyager.messaging.event.MessageEvent", {}
                    )
                    body = msg_event.get("body", "").strip()
                    if not body:
                        continue

                    key = self._notification_key(body)
                    if key in seen:
                        continue

                    text_lower = body.lower()
                    if not any(kw in text_lower for kw in ACTION_KEYWORDS):
                        self._mark_seen(key)
                        continue

                    # Try to build a URL from the conversation URN
                    urn = convo.get("entityUrn", "")
                    convo_id = urn.split(":")[-1] if urn else ""
                    url = (
                        f"https://www.linkedin.com/messaging/thread/{convo_id}/"
                        if convo_id
                        else "https://www.linkedin.com/messaging/"
                    )

                    new_items.append({
                        "text": body[:500],
                        "url": url,
                        "key": key,
                        "detected_at": datetime.now(timezone.utc).isoformat(),
                    })
                    self._mark_seen(key)

                except Exception as e:
                    self.logger.debug(f"Error parsing conversation: {e}")

        except Exception as e:
            self.logger.error(f"LinkedIn API error: {e}")
            # Reset client so next cycle re-authenticates
            self._client = None

        if new_items:
            self.logger.info(f"Found {len(new_items)} relevant LinkedIn message(s).")
        else:
            self.logger.info("No new relevant LinkedIn messages.")

        return new_items

    def create_action_file(self, item: dict) -> Path:
        """Create a structured Needs_Action .md file for a LinkedIn message."""
        now = datetime.now(timezone.utc)
        timestamp_str = now.strftime("%Y%m%dT%H%M%S")
        priority = self._classify_priority(item["text"])

        safe_text = "".join(
            c if c.isalnum() or c in "-_" else "_"
            for c in item["text"][:40]
        ).strip("_")

        content = f"""---
type: linkedin_notification
source: {item['url']}
received: {now.isoformat()}
priority: {priority}
status: pending
watcher: LinkedInWatcher
detected_at: {item['detected_at']}
---

# Action Required: LinkedIn Message

A relevant LinkedIn message was detected that may require a response.

## Message

> {item['text']}

## Details

| Field | Value |
|-------|-------|
| Priority | **{priority.upper()}** |
| Detected | {now.strftime("%Y-%m-%d %H:%M:%S UTC")} |
| Source URL | {item['url']} |

## Suggested Actions

- [ ] Visit the LinkedIn conversation link to read the full message
- [ ] Determine if a reply is needed
- [ ] If posting a LinkedIn update would help → run `/post-linkedin`
- [ ] If a direct message response is needed → create file in `vault/Pending_Approval/`
- [ ] Log outcome and move this file to `vault/Done/`

## Notes

_Add reasoning here after reviewing._

---
*Created by LinkedInWatcher at {now.strftime("%Y-%m-%d %H:%M:%S UTC")}*
"""

        action_file = self.needs_action / f"LINKEDIN_{timestamp_str}_{safe_text}.md"
        action_file.write_text(content, encoding="utf-8")

        self.log_action(
            action_type="linkedin_notification_detected",
            source=item["url"],
            result="success",
            notes=f"Action file created: {action_file.name}",
        )
        return action_file

    def _classify_priority(self, text: str) -> str:
        lower = text.lower()
        urgent = {"urgent", "asap", "deadline", "action required", "overdue"}
        high = {"proposal", "contract", "budget", "pricing", "invoice", "payment",
                "interview", "partnership"}
        if any(kw in lower for kw in urgent):
            return "urgent"
        if any(kw in lower for kw in high):
            return "high"
        return "normal"

    def run(self):
        """Main loop with WAITING mode when credentials are absent."""
        if self.dry_run:
            self.logger.info(
                "[DRY_RUN] LinkedInWatcher started in dry-run mode. "
                "No API calls will be made."
            )
            items = self.check_for_updates()
            self.logger.info("[DRY_RUN] Exiting after one cycle.")
            return

        if not LINKEDIN_API_AVAILABLE:
            self.logger.error(
                "linkedin-api not installed. Run: pip install linkedin-api\n"
                "LinkedInWatcher cannot start."
            )
            return

        if not self.username or not self.password:
            self.logger.warning(
                "[WAITING] LINKEDIN_USERNAME / LINKEDIN_PASSWORD not set in .env. "
                "Sleeping until credentials are provided."
            )
            while not (
                os.getenv("LINKEDIN_USERNAME") and os.getenv("LINKEDIN_PASSWORD")
            ):
                try:
                    time.sleep(60)
                except KeyboardInterrupt:
                    self.logger.info("LinkedInWatcher stopped by user.")
                    return
            self.username = os.getenv("LINKEDIN_USERNAME", "")
            self.password = os.getenv("LINKEDIN_PASSWORD", "")
            self.logger.info("Credentials found. Starting LinkedInWatcher.")

        self.logger.info(
            f"Starting LinkedInWatcher "
            f"(interval={self.check_interval}s, vault={self.vault_path})"
        )

        while True:
            try:
                items = self.check_for_updates()
                for item in items:
                    try:
                        path = self.create_action_file(item)
                        self.logger.info(f"Created action file: {path.name}")
                    except Exception as e:
                        self.logger.error(f"Failed to create action file: {e}")
                        self.log_action(
                            "create_action_file", item.get("url", "?"), "error", str(e)
                        )
                time.sleep(self.check_interval)
            except KeyboardInterrupt:
                self.logger.info("LinkedInWatcher stopped by user.")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error in main loop: {e}")
                self.log_action("watcher_loop", "linkedin_main", "error", str(e))
                time.sleep(self.check_interval)


def main():
    parser = argparse.ArgumentParser(
        description="LinkedIn Messages Watcher for AI Employee (Silver Tier)"
    )
    parser.add_argument(
        "--vault",
        default=os.getenv("VAULT_PATH", "./vault"),
        help="Path to the Obsidian vault directory (default: ./vault)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=os.getenv("DRY_RUN", "false").lower() == "true",
        help="Log intent without making API calls",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Poll interval in seconds (default: 300 = 5 min)",
    )
    args = parser.parse_args()

    vault_path = Path(args.vault).resolve()
    if not vault_path.exists():
        print(f"ERROR: Vault path does not exist: {vault_path}")
        sys.exit(1)

    watcher = LinkedInWatcher(
        vault_path=str(vault_path),
        dry_run=args.dry_run,
        check_interval=args.interval,
    )
    watcher.run()


if __name__ == "__main__":
    main()
