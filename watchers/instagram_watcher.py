"""
instagram_watcher.py - Instagram Activity Watcher (Gold Tier)

Uses Playwright to visit instagram.com and check DMs + activity notifications.
Filters for business-relevant keywords and creates Needs_Action files.

Usage:
    python watchers/instagram_watcher.py --vault ./vault
    python watchers/instagram_watcher.py --vault ./vault --dry-run

Setup:
    1. Install Playwright: python -m playwright install chromium
    2. Capture session: python setup/save_social_sessions.py
    3. Set INSTAGRAM_SESSION_PATH in .env

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
    "question", "dm", "collab", "collaboration", "sponsor", "paid",
    "pricing", "rate", "deal", "refund", "support", "client", "business",
}

SEEN_FILE = Path("./secrets/instagram_seen.txt")


class InstagramWatcher(BaseWatcher):
    """
    Watches Instagram activity using Playwright browser automation.

    Gold Tier Requirement:
      "Facebook + Instagram watcher + posting"
    """

    def __init__(self, vault_path: str, dry_run: bool = False, check_interval: int = 300):
        super().__init__(vault_path, check_interval=check_interval)
        self.dry_run = dry_run
        self.session_path = Path(
            os.getenv("INSTAGRAM_SESSION_PATH", "./secrets/instagram_storage.json")
        )
        SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)

        if not self.dry_run and not self.session_path.exists():
            self.logger.warning(
                f"Instagram session file not found: {self.session_path}\n"
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
                # Check activity feed
                page.goto("https://www.instagram.com/", timeout=30_000)
                page.wait_for_load_state("domcontentloaded", timeout=20_000)

                if "login" in page.url or "accounts/login" in page.url:
                    self.logger.warning(
                        "Instagram session expired. Re-run: python setup/save_social_sessions.py"
                    )
                    context.close()
                    browser.close()
                    return []

                # Navigate to DMs (most actionable)
                page.goto("https://www.instagram.com/direct/inbox/", timeout=30_000)
                page.wait_for_load_state("domcontentloaded", timeout=20_000)

                try:
                    page.wait_for_selector(
                        "[role='listbox'], [class*='DirectInbox']",
                        timeout=8_000,
                    )
                except PlaywrightTimeout:
                    self.logger.debug("Instagram DM inbox did not load — may be empty or session issue.")

                # Extract DM previews
                items_els = page.query_selector_all("[role='listbox'] [role='option'], [class*='thread']")
                for el in items_els[:20]:
                    try:
                        text = el.inner_text().strip()
                        if not text:
                            continue
                        key = self._notification_key(text)
                        if key in seen:
                            continue
                        text_lower = text.lower()
                        if not any(kw in text_lower for kw in ACTION_KEYWORDS):
                            self._mark_seen(key)
                            continue
                        link_el = el.query_selector("a[href]")
                        url = link_el.get_attribute("href") if link_el else None
                        if url and url.startswith("/"):
                            url = "https://www.instagram.com" + url
                        new_items.append({
                            "text": text[:500],
                            "url": url or "https://www.instagram.com/direct/inbox/",
                            "key": key,
                            "detected_at": datetime.now(timezone.utc).isoformat(),
                        })
                        self._mark_seen(key)
                    except Exception as e:
                        self.logger.debug(f"Error parsing DM item: {e}")

            except Exception as e:
                self.logger.error(f"Error during Instagram scrape: {e}")
            finally:
                context.close()
                browser.close()

        if new_items:
            self.logger.info(f"Found {len(new_items)} relevant Instagram DM(s).")
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
            self.logger.info(
                "[DRY_RUN] InstagramWatcher started — no browser will be launched."
            )
            self.logger.info("[DRY_RUN] Exiting after one cycle.")
            return

        self.logger.info(f"Starting InstagramWatcher (interval={self.check_interval}s)")
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
