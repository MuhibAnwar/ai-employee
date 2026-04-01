"""
whatsapp_watcher.py - WhatsApp Web Watcher (Playwright-based)

Monitors WhatsApp Web for new unread messages matching keywords and drops
structured .md files into vault/Inbox/ for the AI Employee to process.

Usage:
    # Step 1 — one-time QR code scan to save session:
    python watchers/whatsapp_watcher.py --setup

    # Step 2 — run the watcher (headless, uses saved session):
    python watchers/whatsapp_watcher.py --vault ./vault

    # Dry-run (no browser, no files written):
    python watchers/whatsapp_watcher.py --vault ./vault --dry-run

Notes:
    - WhatsApp Web automation. Be aware of WhatsApp's Terms of Service.
    - This watcher is LOCAL ONLY — sessions and tokens never sync to the cloud.
    - Session is stored in ./whatsapp_session/ (gitignored).
    - Run --setup on a machine with a display before running headless.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

PROJECT_ROOT = Path(__file__).resolve().parent.parent

from base_watcher import BaseWatcher

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Path where the browser session (cookies/localStorage) is persisted
DEFAULT_SESSION_PATH = PROJECT_ROOT / "whatsapp_session"

# Keywords that trigger an action file; case-insensitive
DEFAULT_KEYWORDS = [
    "urgent", "asap", "invoice", "payment", "help", "contract",
    "proposal", "meeting", "deadline", "review", "approve",
]

# How long (ms) to wait for WhatsApp Web to load after navigating
PAGE_LOAD_TIMEOUT = 60_000   # 60 s — QR scan or chat list
CHAT_POLL_TIMEOUT = 45_000   # 45 s — chat-list selector after initial load (Firefox is slower)

# Processed-message dedup file
PROCESSED_IDS_FILE = PROJECT_ROOT / "secrets" / "whatsapp_processed_ids.txt"


class WhatsAppWatcher(BaseWatcher):
    """
    Polls WhatsApp Web for unread messages matching keywords.
    Creates structured .md files in vault/Inbox/ for each match.
    """

    def __init__(
        self,
        vault_path: str,
        session_path: str | None = None,
        keywords: list[str] | None = None,
        dry_run: bool = False,
        check_interval: int = 30,
    ):
        super().__init__(vault_path, check_interval=check_interval)
        self.session_path = Path(session_path or DEFAULT_SESSION_PATH)
        self.keywords = [kw.lower() for kw in (keywords or DEFAULT_KEYWORDS)]
        self.dry_run = dry_run

        # Ensure session dir and secrets dir exist
        self.session_path.mkdir(parents=True, exist_ok=True)
        PROCESSED_IDS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # ─────────────────────────────────────────────────────────────────────────
    # Processed ID dedup
    # ─────────────────────────────────────────────────────────────────────────

    def _load_processed_ids(self) -> set:
        if PROCESSED_IDS_FILE.exists():
            return set(PROCESSED_IDS_FILE.read_text(encoding="utf-8").splitlines())
        return set()

    def _save_processed_id(self, msg_id: str):
        with PROCESSED_IDS_FILE.open("a", encoding="utf-8") as f:
            f.write(msg_id + "\n")

    # ─────────────────────────────────────────────────────────────────────────
    # BaseWatcher interface
    # ─────────────────────────────────────────────────────────────────────────

    def check_for_updates(self) -> list:
        """
        Open WhatsApp Web with the saved session, scrape unread chats,
        filter by keywords, and return a list of message dicts.
        """
        if self.dry_run:
            self.logger.info("[DRY_RUN] Skipping WhatsApp browser — returning empty list.")
            return []

        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "Playwright is not installed.\n"
                "Run: pip install playwright && playwright install chromium"
            )

        if not self._session_exists():
            raise RuntimeError(
                f"No WhatsApp session found at {self.session_path}.\n"
                "Run setup first:  python watchers/whatsapp_watcher.py --setup"
            )

        messages = []
        processed = self._load_processed_ids()

        with sync_playwright() as p:
            browser = p.firefox.launch_persistent_context(
                str(self.session_path),
                headless=True,
            )
            try:
                page = browser.pages[0] if browser.pages else browser.new_page()
                page.goto("https://web.whatsapp.com", timeout=PAGE_LOAD_TIMEOUT)

                # Wait for chat list — if not logged in this will timeout
                try:
                    # Works in both Chromium (data-testid) and Firefox (aria-label / input)
                    page.wait_for_selector(
                        '[data-testid="chat-list"], '
                        '[aria-label*="unread message"], '
                        'div[role="textbox"], '
                        'input[type="text"]',
                        timeout=CHAT_POLL_TIMEOUT,
                    )
                except PWTimeoutError:
                    self.logger.error(
                        "Chat list did not appear — session may have expired. "
                        "Run --setup again to re-scan the QR code."
                    )
                    return []

                # Scrape unread messages by finding unread badges directly.
                # Works across Chromium (data-testid) and Firefox (aria-label only).
                unread_badges = page.query_selector_all('[aria-label*="unread message"]')
                # Fallback: Chromium data-testid approach via listitem rows
                if not unread_badges:
                    unread_badges = page.query_selector_all(
                        '[role="listitem"] [data-testid="icon-unread-count"]'
                    )

                for unread_badge in unread_badges:
                    # Walk up to find the chat container (has sender name + preview)
                    sender = unread_badge.evaluate('''el => {
                        let p = el.parentElement;
                        for (let i = 0; i < 8; i++) {
                            if (!p) break;
                            let t = p.querySelector("span[title]");
                            if (t && t.title) return t.title;
                            let dt = p.querySelector("[data-testid=\'cell-frame-title\']");
                            if (dt) return dt.textContent.trim();
                            p = p.parentElement;
                        }
                        return "Unknown";
                    }''')

                    preview = unread_badge.evaluate('''el => {
                        let p = el.parentElement;
                        for (let i = 0; i < 8; i++) {
                            if (!p) break;
                            let s = p.querySelector("span[dir=\'ltr\']");
                            if (s && s.textContent.trim()) return s.textContent.trim();
                            let dt = p.querySelector("[data-testid=\'cell-frame-secondary-detail\'] span");
                            if (dt) return dt.textContent.trim();
                            p = p.parentElement;
                        }
                        return "";
                    }''')

                    # Build a stable message ID from sender + preview hash
                    msg_id = f"{sender}::{preview[:80]}"

                    if msg_id in processed:
                        continue

                    text_lower = (sender + " " + preview).lower()
                    matched_keywords = [kw for kw in self.keywords if kw in text_lower]

                    if matched_keywords:
                        messages.append({
                            "id": msg_id,
                            "sender": sender,
                            "preview": preview,
                            "keywords": matched_keywords,
                            "detected_at": datetime.now(timezone.utc).isoformat(),
                        })
                        self._save_processed_id(msg_id)
                        self.logger.info(
                            f"Keyword match from '{sender}': {matched_keywords}"
                        )

            finally:
                browser.close()

        return messages

    def create_action_file(self, item: dict) -> Path:
        """Write a structured .md file to vault/Inbox/."""
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y%m%dT%H%M%S")
        safe_sender = "".join(
            c if c.isalnum() or c in "-_" else "_"
            for c in item["sender"][:30]
        ).strip("_")

        priority = self._classify_priority(item["keywords"])

        content = f"""---
type: whatsapp_message
source: whatsapp://{safe_sender}
received: {now.isoformat()}
priority: {priority}
status: pending
watcher: WhatsAppWatcher
sender: "{item['sender']}"
keywords_matched: {json.dumps(item['keywords'])}
---

# Action Required: WhatsApp — {item['sender']}

A new WhatsApp message matching monitored keywords has been detected.

## Message Details

| Field | Value |
|-------|-------|
| From | `{item['sender']}` |
| Keywords Matched | {', '.join(f'`{kw}`' for kw in item['keywords'])} |
| Priority | **{priority.upper()}** |
| Detected | {now.strftime('%Y-%m-%d %H:%M:%S UTC')} |

## Message Preview

> {item['preview'] or '(no preview available)'}

## Suggested Actions

- [ ] Open WhatsApp and read the full message from {item['sender']}
- [ ] Determine if a reply is required
- [ ] If reply needed → create file in `vault/Pending_Approval/` (action: send_whatsapp)
- [ ] If task is implied → create `Plan.md` in `vault/Plans/`
- [ ] Log outcome and move this file to `vault/Done/`

## Notes

_Add reasoning here after reviewing._

---
*Created by WhatsAppWatcher at {now.strftime('%Y-%m-%d %H:%M:%S UTC')}*
"""

        action_file = self.inbox / f"WHATSAPP_{ts}_{safe_sender}.md"
        action_file.write_text(content, encoding="utf-8")

        self.log_action(
            action_type="whatsapp_message_detected",
            source=f"whatsapp://{item['sender']}",
            result="success",
            notes=f"Action file: {action_file.name} | keywords: {item['keywords']}",
        )
        return action_file

    def _classify_priority(self, keywords: list) -> str:
        urgent = {"urgent", "asap", "deadline"}
        high = {"invoice", "payment", "contract", "proposal", "approve"}
        if any(kw in urgent for kw in keywords):
            return "urgent"
        if any(kw in high for kw in keywords):
            return "high"
        return "normal"

    def _session_exists(self) -> bool:
        """Return True if a saved session directory with content exists."""
        return (
            self.session_path.exists()
            and any(self.session_path.iterdir())
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Setup: one-time QR scan
    # ─────────────────────────────────────────────────────────────────────────

    def run_setup(self):
        """
        Open a headed browser so you can scan the WhatsApp QR code.
        Saves the session to self.session_path for future headless runs.
        """
        if not PLAYWRIGHT_AVAILABLE:
            print("ERROR: Playwright not installed. Run: pip install playwright && playwright install chromium")
            sys.exit(1)

        print(f"\nStarting WhatsApp Web setup...")
        print(f"Session will be saved to: {self.session_path}")
        print("\nA browser window will open. Scan the QR code with WhatsApp on your phone.")
        print("Once logged in, press ENTER here to save the session and exit.\n")

        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                str(self.session_path),
                headless=False,
                args=["--no-sandbox"],
            )
            page = browser.pages[0] if browser.pages else browser.new_page()
            page.goto("https://web.whatsapp.com", timeout=PAGE_LOAD_TIMEOUT)

            print("Browser opened — waiting for you to scan the QR code...")
            input("Press ENTER after you are logged in to WhatsApp Web: ")

            print("Session saved. You can now run the watcher in headless mode.")
            browser.close()

    # ─────────────────────────────────────────────────────────────────────────
    # Run loop override
    # ─────────────────────────────────────────────────────────────────────────

    def run(self):
        if self.dry_run:
            self.logger.info("[DRY_RUN] WhatsAppWatcher started in dry-run mode.")
        else:
            self.logger.info(
                f"Starting WhatsAppWatcher "
                f"(interval={self.check_interval}s, vault={self.vault_path}, "
                f"session={self.session_path})"
            )

        while True:
            try:
                items = self.check_for_updates()
                for item in items:
                    try:
                        path = self.create_action_file(item)
                        self.logger.info(f"Created inbox file: {path.name}")
                    except Exception as e:
                        self.logger.error(f"Failed to create action file: {e}")
                        self.log_action("create_action_file", str(item), "error", str(e))
            except KeyboardInterrupt:
                self.logger.info("WhatsAppWatcher stopped by user.")
                break
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                self.log_action("watcher_loop", "whatsapp_main", "error", str(e))

            if self.dry_run:
                self.logger.info("[DRY_RUN] Exiting after one cycle.")
                break

            time.sleep(self.check_interval)


def main():
    parser = argparse.ArgumentParser(
        description="WhatsApp Watcher for AI Employee"
    )
    parser.add_argument(
        "--vault",
        default=os.getenv("VAULT_PATH", "./vault"),
        help="Path to the Obsidian vault directory (default: ./vault)",
    )
    parser.add_argument(
        "--session",
        default=os.getenv("WHATSAPP_SESSION_PATH", str(DEFAULT_SESSION_PATH)),
        help=f"Path to store/load the WhatsApp session (default: {DEFAULT_SESSION_PATH})",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run one-time QR code setup (opens headed browser)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=os.getenv("DRY_RUN", "false").lower() == "true",
        help="Log intent without opening a browser or writing files",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=int(os.getenv("WHATSAPP_INTERVAL", "30")),
        help="Poll interval in seconds (default: 30)",
    )
    parser.add_argument(
        "--keywords",
        nargs="+",
        help="Keywords to monitor (overrides defaults)",
    )
    args = parser.parse_args()

    vault_path = Path(args.vault).resolve()
    if not args.setup and not vault_path.exists():
        print(f"ERROR: Vault path does not exist: {vault_path}")
        sys.exit(1)

    watcher = WhatsAppWatcher(
        vault_path=str(vault_path),
        session_path=args.session,
        keywords=args.keywords,
        dry_run=args.dry_run,
        check_interval=args.interval,
    )

    if args.setup:
        watcher.run_setup()
    else:
        watcher.run()


if __name__ == "__main__":
    main()
