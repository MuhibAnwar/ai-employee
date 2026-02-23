"""
twitter_watcher.py - Twitter/X Notifications + Mentions Watcher (Gold Tier)

Uses Playwright to visit x.com/notifications, loading a saved session.
Filters for business-relevant mentions and DMs, creates Needs_Action files.

Usage:
    python watchers/twitter_watcher.py --vault ./vault
    python watchers/twitter_watcher.py --vault ./vault --dry-run

Setup:
    1. Install Playwright: python -m playwright install chromium
    2. Capture session: python setup/save_social_sessions.py
    3. Set TWITTER_SESSION_PATH in .env

Keyword filtering (creates action file if ANY match):
    urgent, invoice, payment, order, complaint, dm, mention,
    pricing, proposal, partnership, sponsor, deal, support

Requirements:
    pip install playwright python-dotenv
    python -m playwright install chromium
"""

import argparse
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


ACTION_KEYWORDS = {
    "urgent", "asap", "invoice", "payment", "order", "complaint",
    "dm", "mention", "pricing", "proposal", "partnership", "sponsor",
    "deal", "support", "client", "refund", "deadline", "collaboration",
}

SEEN_FILE = Path("./secrets/twitter_seen.txt")


class TwitterWatcher(BaseWatcher):
    """
    Watches Twitter/X notifications and mentions using Playwright.

    Gold Tier Requirement:
      "Twitter/X watcher + posting"
    """

    def __init__(self, vault_path: str, dry_run: bool = False, check_interval: int = 300):
        super().__init__(vault_path, check_interval=check_interval)
        self.dry_run = dry_run
        self.session_path = Path(
            os.getenv("TWITTER_SESSION_PATH", "./secrets/twitter_storage.json")
        )
        SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)

        if not self.dry_run and not self.session_path.exists():
            self.logger.warning(
                f"Twitter/X session file not found: {self.session_path}\n"
                "Run: python setup/save_social_sessions.py"
            )

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

    def check_for_updates(self) -> list:
        if self.dry_run:
            self.logger.info("[DRY_RUN] Skipping Playwright browser — returning empty list.")
            return []

        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "Playwright not installed. Run: pip install playwright && "
                "python -m playwright install chromium"
            )

        if not self.session_path.exists():
            self.logger.error(
                f"Session file not found: {self.session_path}. "
                "Run: python setup/save_social_sessions.py"
            )
            return []

        seen = self._load_seen()
        new_items = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(storage_state=str(self.session_path))
            page = context.new_page()

            try:
                page.goto("https://x.com/notifications/mentions", timeout=30_000)
                page.wait_for_load_state("domcontentloaded", timeout=20_000)

                if "login" in page.url or "i/flow/login" in page.url:
                    self.logger.warning(
                        "Twitter/X session expired. Re-run: python setup/save_social_sessions.py"
                    )
                    context.close()
                    browser.close()
                    return []

                try:
                    page.wait_for_selector(
                        "[data-testid='tweet'], [data-testid='notification']",
                        timeout=10_000,
                    )
                except PlaywrightTimeout:
                    self.logger.debug("Twitter notification list did not load — may be empty.")

                tweets = page.query_selector_all(
                    "[data-testid='tweet'], [data-testid='notification']"
                )

                for tweet in tweets[:30]:
                    try:
                        text = tweet.inner_text().strip()
                        if not text:
                            continue
                        key = self._notification_key(text)
                        if key in seen:
                            continue
                        text_lower = text.lower()
                        if not any(kw in text_lower for kw in ACTION_KEYWORDS):
                            self._mark_seen(key)
                            continue
                        link_el = tweet.query_selector("a[href*='/status/']")
                        url = link_el.get_attribute("href") if link_el else None
                        if url and url.startswith("/"):
                            url = "https://x.com" + url
                        new_items.append({
                            "text": text[:500],
                            "url": url or "https://x.com/notifications/mentions",
                            "key": key,
                            "detected_at": datetime.now(timezone.utc).isoformat(),
                        })
                        self._mark_seen(key)
                    except Exception as e:
                        self.logger.debug(f"Error parsing tweet/notification: {e}")

            except Exception as e:
                self.logger.error(f"Error during Twitter/X scrape: {e}")
            finally:
                context.close()
                browser.close()

        if new_items:
            self.logger.info(f"Found {len(new_items)} relevant Twitter/X mention(s).")
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
type: twitter_mention
source: {item['url']}
received: {now.isoformat()}
priority: {priority}
status: pending
watcher: TwitterWatcher
detected_at: {item['detected_at']}
---

# Action Required: Twitter/X Mention or DM

A relevant Twitter/X mention or notification was detected.

## Tweet / Message Preview

> {item['text']}

## Details

| Field | Value |
|-------|-------|
| Priority | **{priority.upper()}** |
| Detected | {now.strftime("%Y-%m-%d %H:%M:%S UTC")} |
| Source URL | {item['url']} |

## Suggested Actions

- [ ] Open the Twitter/X link to read the full context
- [ ] Determine if a reply or retweet is appropriate
- [ ] If posting a new tweet is needed → create approval file (action: post_twitter)
- [ ] If a DM response is needed → create file in `vault/Pending_Approval/`
- [ ] Log outcome and move this file to `vault/Done/`

---
*Created by TwitterWatcher at {now.strftime("%Y-%m-%d %H:%M:%S UTC")}*
"""
        action_file = self.needs_action / f"SOCIAL_TW_{ts}_{safe}.md"
        action_file.write_text(content, encoding="utf-8")
        self.log_action(
            action_type="twitter_mention_detected",
            source=item["url"],
            result="success",
            notes=f"Action file created: {action_file.name}",
        )
        return action_file

    def _classify_priority(self, text: str) -> str:
        lower = text.lower()
        if any(kw in lower for kw in {"urgent", "asap", "complaint", "refund", "deadline"}):
            return "urgent"
        if any(kw in lower for kw in {"invoice", "payment", "order", "sponsor", "deal", "pricing"}):
            return "high"
        return "normal"

    def run(self):
        if self.dry_run:
            self.logger.info(
                "[DRY_RUN] TwitterWatcher started — no browser will be launched."
            )
            self.logger.info("[DRY_RUN] Exiting after one cycle.")
            return

        self.logger.info(f"Starting TwitterWatcher (interval={self.check_interval}s)")
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
            except KeyboardInterrupt:
                self.logger.info("TwitterWatcher stopped by user.")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error: {e}")
                self.log_action("watcher_loop", "twitter_main", "error", str(e))
            time.sleep(self.check_interval)


def main():
    parser = argparse.ArgumentParser(
        description="Twitter/X Mentions Watcher for AI Employee (Gold Tier)"
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

    TwitterWatcher(
        vault_path=str(vault_path),
        dry_run=args.dry_run,
        check_interval=args.interval,
    ).run()


if __name__ == "__main__":
    main()
