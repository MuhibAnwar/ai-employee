"""
linkedin_watcher.py - LinkedIn Notifications Watcher (Silver Tier)

Uses Playwright to visit linkedin.com/notifications, loading a saved session
from a storage-state JSON file. Extracts notification text and creates
structured .md action files in vault/Needs_Action/ for relevant items.

Usage:
    python watchers/linkedin_watcher.py --vault ./vault
    python watchers/linkedin_watcher.py --vault ./vault --dry-run

Setup:
    1. Install Playwright browsers: python -m playwright install chromium
    2. Capture session: python -m playwright open --save-storage=secrets/linkedin_storage.json https://www.linkedin.com
    3. Set LINKEDIN_SESSION_PATH=.../secrets/linkedin_storage.json in .env

Keyword filtering:
    Notifications containing these keywords create action files:
    - Business intent: pricing, proposal, project, contract, budget
    - Urgency signals: urgent, asap, deadline, action required
    - Relationship: interview, partnership, collaboration, opportunity
    All others are logged but silently discarded.

Requirements:
    pip install playwright python-dotenv
    python -m playwright install chromium
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))

from base_watcher import BaseWatcher

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


# Keywords that trigger an action file
ACTION_KEYWORDS = {
    "pricing", "proposal", "project", "contract", "budget",
    "urgent", "asap", "deadline", "action required",
    "interview", "partnership", "collaboration", "opportunity",
    "invoice", "payment", "meeting request", "follow up",
}

# File to track seen notification hashes (avoid duplicates)
SEEN_FILE = Path("./secrets/linkedin_seen.txt")


class LinkedInWatcher(BaseWatcher):
    """
    Watches LinkedIn notifications using Playwright browser automation.

    Silver Tier Requirement:
      "Two+ watcher scripts (Gmail + LinkedIn)"
    """

    def __init__(self, vault_path: str, dry_run: bool = False, check_interval: int = 300):
        super().__init__(vault_path, check_interval=check_interval)
        self.dry_run = dry_run
        self.session_path = Path(
            os.getenv("LINKEDIN_SESSION_PATH", "./secrets/linkedin_storage.json")
        )
        SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)

        if not self.dry_run and not self.session_path.exists():
            self.logger.warning(
                f"LinkedIn session file not found: {self.session_path}\n"
                "Capture it with:\n"
                "  python -m playwright open "
                "--save-storage=secrets/linkedin_storage.json "
                "https://www.linkedin.com"
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Seen notification tracking
    # ─────────────────────────────────────────────────────────────────────────

    def _load_seen(self) -> set:
        if SEEN_FILE.exists():
            return set(SEEN_FILE.read_text(encoding="utf-8").splitlines())
        return set()

    def _mark_seen(self, key: str):
        with SEEN_FILE.open("a", encoding="utf-8") as f:
            f.write(key + "\n")

    @staticmethod
    def _notification_key(text: str) -> str:
        """Stable deduplication key — first 80 chars, lowercased."""
        return text.strip().lower()[:80]

    # ─────────────────────────────────────────────────────────────────────────
    # BaseWatcher interface
    # ─────────────────────────────────────────────────────────────────────────

    def check_for_updates(self) -> list:
        """
        Open LinkedIn notifications page and return new relevant items.
        Each item is a dict: {text, url, timestamp}.
        """
        if self.dry_run:
            self.logger.info("[DRY_RUN] Skipping Playwright browser — returning empty list.")
            return []

        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "Playwright is not installed.\n"
                "Run: pip install playwright && python -m playwright install chromium"
            )

        seen = self._load_seen()
        new_items = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(storage_state=str(self.session_path))
            page = context.new_page()

            try:
                page.goto("https://www.linkedin.com/notifications/", timeout=30_000)
                page.wait_for_load_state("domcontentloaded", timeout=20_000)

                # Check if we're still logged in
                if "login" in page.url or "authwall" in page.url:
                    self.logger.warning(
                        "LinkedIn session expired. Re-capture with:\n"
                        "  python -m playwright open "
                        "--save-storage=secrets/linkedin_storage.json "
                        "https://www.linkedin.com"
                    )
                    context.close()
                    browser.close()
                    return []

                # Wait for notification list to render
                try:
                    page.wait_for_selector(
                        "li.nt-card-list__item, [data-test-notification-card]",
                        timeout=10_000,
                    )
                except PlaywrightTimeout:
                    self.logger.warning("Notification list did not load in time.")
                    browser.close()
                    return []

                # Extract notification cards
                cards = page.query_selector_all(
                    "li.nt-card-list__item, [data-test-notification-card]"
                )

                for card in cards[:30]:  # limit to 30 most recent
                    try:
                        text = card.inner_text().strip()
                        if not text:
                            continue

                        key = self._notification_key(text)
                        if key in seen:
                            continue

                        # Only create action files for relevant notifications
                        text_lower = text.lower()
                        if not any(kw in text_lower for kw in ACTION_KEYWORDS):
                            self._mark_seen(key)
                            continue

                        # Try to extract a link
                        link_el = card.query_selector("a[href]")
                        url = link_el.get_attribute("href") if link_el else None
                        if url and url.startswith("/"):
                            url = "https://www.linkedin.com" + url

                        new_items.append(
                            {
                                "text": text[:500],
                                "url": url or "https://www.linkedin.com/notifications/",
                                "key": key,
                                "detected_at": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                        self._mark_seen(key)

                    except Exception as e:
                        self.logger.debug(f"Error parsing notification card: {e}")

            except Exception as e:
                self.logger.error(f"Error during LinkedIn page scrape: {e}")

            finally:
                context.close()
                browser.close()

        if new_items:
            self.logger.info(f"Found {len(new_items)} relevant LinkedIn notification(s).")
        else:
            self.logger.debug("No new relevant LinkedIn notifications.")

        return new_items

    def create_action_file(self, item: dict) -> Path:
        """Create a structured Needs_Action .md file for a LinkedIn notification."""
        now = datetime.now(timezone.utc)
        timestamp_str = now.strftime("%Y%m%dT%H%M%S")

        priority = self._classify_priority(item["text"])

        # Safe filename from first 40 chars of notification text
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

# Action Required: LinkedIn Notification

A relevant LinkedIn notification was detected that may require a response.

## Notification

> {item['text']}

## Details

| Field | Value |
|-------|-------|
| Priority | **{priority.upper()}** |
| Detected | {now.strftime("%Y-%m-%d %H:%M:%S UTC")} |
| Source URL | {item['url']} |

## Suggested Actions

- [ ] Visit the LinkedIn notification link to read the full message
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
        """Classify priority based on notification text keywords."""
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
        """Override run to add dry-run single-cycle support."""
        if self.dry_run:
            self.logger.info(
                "[DRY_RUN] LinkedInWatcher started in dry-run mode. "
                "No browser will be launched."
            )
        else:
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
            except KeyboardInterrupt:
                self.logger.info("LinkedInWatcher stopped by user.")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error in main loop: {e}")
                self.log_action("watcher_loop", "linkedin_main", "error", str(e))

            if self.dry_run:
                self.logger.info("[DRY_RUN] Exiting after one cycle.")
                break

            time.sleep(self.check_interval)


def main():
    parser = argparse.ArgumentParser(
        description="LinkedIn Notifications Watcher for AI Employee (Silver Tier)"
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
        help="Log intent without launching browser",
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
