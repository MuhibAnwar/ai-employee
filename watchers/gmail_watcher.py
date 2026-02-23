"""
gmail_watcher.py - Gmail Inbox Watcher (Silver Tier)

Polls Gmail API every 120 seconds for unread, important emails.
When new emails are found, creates structured .md action files in
vault/Needs_Action/ so Claude Code can reason about and respond to them.

Usage:
    python watchers/gmail_watcher.py --vault ./vault
    python watchers/gmail_watcher.py --vault ./vault --dry-run

Setup:
    1. Enable Gmail API at https://console.cloud.google.com/
    2. Download OAuth2 credentials JSON → save to ./secrets/gmail_credentials.json
    3. Set GMAIL_CREDENTIALS_PATH and GMAIL_TOKEN_PATH in .env
    4. First run opens a browser for OAuth consent; token cached afterwards.

Requirements:
    pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client python-dotenv
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

# Allow running from project root or watchers/ directory
sys.path.insert(0, str(Path(__file__).parent))

from base_watcher import BaseWatcher

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional; env vars may be set directly

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False


# OAuth scopes — read-only is enough for watching; send scope needed for MCP server
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# File to track processed message IDs so we never duplicate action files
PROCESSED_IDS_FILE = Path("./secrets/gmail_processed_ids.txt")


class GmailWatcher(BaseWatcher):
    """
    Polls Gmail for unread important emails and creates Needs_Action files.

    Silver Tier Requirement:
      "Two+ watcher scripts (Gmail + LinkedIn)"
    """

    def __init__(self, vault_path: str, dry_run: bool = False, check_interval: int = 120):
        super().__init__(vault_path, check_interval=check_interval)
        self.dry_run = dry_run
        self._service = None

        # Paths from env or defaults
        self.credentials_path = Path(
            os.getenv("GMAIL_CREDENTIALS_PATH", "./secrets/gmail_credentials.json")
        )
        self.token_path = Path(
            os.getenv("GMAIL_TOKEN_PATH", "./secrets/gmail_token.json")
        )

        # Ensure secrets dir exists
        self.credentials_path.parent.mkdir(parents=True, exist_ok=True)
        PROCESSED_IDS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # ─────────────────────────────────────────────────────────────────────────
    # Authentication
    # ─────────────────────────────────────────────────────────────────────────

    def _authenticate(self):
        """Build authenticated Gmail API service. Caches token after first OAuth flow."""
        if not GMAIL_AVAILABLE:
            raise RuntimeError(
                "Gmail API libraries are not installed.\n"
                "Run: pip install google-auth google-auth-oauthlib "
                "google-auth-httplib2 google-api-python-client"
            )

        creds = None

        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(
                        f"Gmail credentials file not found: {self.credentials_path}\n"
                        "Download it from Google Cloud Console and save it there."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), SCOPES
                )
                creds = flow.run_local_server(port=0)

            self.token_path.write_text(creds.to_json(), encoding="utf-8")
            self.logger.info(f"Gmail token saved to {self.token_path}")

        self._service = build("gmail", "v1", credentials=creds)
        self.logger.info("Gmail API authenticated successfully.")

    # ─────────────────────────────────────────────────────────────────────────
    # Processed ID tracking
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
        Query Gmail for unread important messages not previously processed.
        Returns a list of message detail dicts.
        """
        if self.dry_run:
            self.logger.info("[DRY_RUN] Skipping Gmail API call — returning empty list.")
            return []

        if self._service is None:
            self._authenticate()

        processed = self._load_processed_ids()

        # Search for unread messages in the IMPORTANT category
        response = (
            self._service.users()
            .messages()
            .list(userId="me", q="is:unread is:important", maxResults=20)
            .execute()
        )

        raw_messages = response.get("messages", [])
        new_items = []

        for msg_stub in raw_messages:
            msg_id = msg_stub["id"]
            if msg_id in processed:
                continue

            # Fetch full message metadata (no body download)
            full_msg = (
                self._service.users()
                .messages()
                .get(userId="me", id=msg_id, format="metadata",
                     metadataHeaders=["From", "Subject", "Date"])
                .execute()
            )

            # Extract headers
            headers = {
                h["name"]: h["value"]
                for h in full_msg.get("payload", {}).get("headers", [])
            }

            snippet = full_msg.get("snippet", "")[:300]

            new_items.append(
                {
                    "id": msg_id,
                    "from": headers.get("From", "unknown"),
                    "subject": headers.get("Subject", "(no subject)"),
                    "date": headers.get("Date", ""),
                    "snippet": snippet,
                    "labels": full_msg.get("labelIds", []),
                }
            )

            self._save_processed_id(msg_id)

        if new_items:
            self.logger.info(f"Found {len(new_items)} new important email(s).")
        else:
            self.logger.debug("No new important emails.")

        return new_items

    def create_action_file(self, item: dict) -> Path:
        """
        Create a structured Needs_Action .md file for a Gmail message.
        """
        now = datetime.now(timezone.utc)
        timestamp_str = now.strftime("%Y%m%dT%H%M%S")

        # Classify priority based on subject keywords
        priority = self._classify_priority(item["subject"])

        # Sanitise subject for use in filename (keep alphanumeric + hyphens)
        safe_subject = "".join(
            c if c.isalnum() or c in "-_" else "_"
            for c in item["subject"][:40]
        ).strip("_")

        content = f"""---
type: gmail_email
source: gmail://message/{item['id']}
received: {now.isoformat()}
priority: {priority}
status: pending
watcher: GmailWatcher
from: {item['from']}
subject: "{item['subject']}"
gmail_date: {item['date']}
---

# Action Required: Email — {item['subject']}

A new important unread email has arrived in Gmail.

## Email Details

| Field | Value |
|-------|-------|
| From | `{item['from']}` |
| Subject | {item['subject']} |
| Date | {item['date']} |
| Priority | **{priority.upper()}** |
| Gmail ID | `{item['id']}` |

## Preview

> {item['snippet']}

## Suggested Actions

- [ ] Read the full email in Gmail
- [ ] Determine if a response is required
- [ ] If response needed → create file in `vault/Pending_Approval/` (action: send_email)
- [ ] If task is implied → create `Plan.md` in `vault/Plans/`
- [ ] Log outcome and move this file to `vault/Done/`

## Notes

_Add reasoning here after reviewing._

---
*Created by GmailWatcher at {now.strftime("%Y-%m-%d %H:%M:%S UTC")}*
"""

        action_file = self.needs_action / f"EMAIL_{timestamp_str}_{safe_subject}.md"
        action_file.write_text(content, encoding="utf-8")

        self.log_action(
            action_type="gmail_email_detected",
            source=f"gmail://message/{item['id']}",
            result="success",
            notes=f"Action file created: {action_file.name} | Subject: {item['subject']}",
        )
        return action_file

    def _classify_priority(self, subject: str) -> str:
        """Classify email priority based on subject keywords."""
        lower = subject.lower()
        urgent = {"urgent", "asap", "critical", "overdue", "deadline", "action required"}
        high = {"invoice", "payment", "contract", "proposal", "meeting", "client", "follow up"}

        if any(kw in lower for kw in urgent):
            return "urgent"
        if any(kw in lower for kw in high):
            return "high"
        return "normal"

    def run(self):
        """Override run to handle authentication errors gracefully."""
        if self.dry_run:
            self.logger.info(
                "[DRY_RUN] GmailWatcher started in dry-run mode. "
                "No Gmail API calls will be made."
            )
        else:
            self.logger.info(
                f"Starting GmailWatcher (interval={self.check_interval}s, vault={self.vault_path})"
            )
            try:
                self._authenticate()
            except Exception as e:
                self.logger.error(f"Gmail authentication failed: {e}")
                self.logger.error("Fix credentials and restart. Exiting.")
                sys.exit(1)

        while True:
            try:
                items = self.check_for_updates()
                for item in items:
                    try:
                        path = self.create_action_file(item)
                        self.logger.info(f"Created action file: {path.name}")
                    except Exception as e:
                        self.logger.error(f"Failed to create action file: {e}")
                        self.log_action("create_action_file", item.get("id", "?"), "error", str(e))
            except KeyboardInterrupt:
                self.logger.info("GmailWatcher stopped by user.")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error in main loop: {e}")
                self.log_action("watcher_loop", "gmail_main", "error", str(e))

            if self.dry_run:
                self.logger.info("[DRY_RUN] Exiting after one cycle.")
                break

            time.sleep(self.check_interval)


def main():
    parser = argparse.ArgumentParser(
        description="Gmail Watcher for AI Employee (Silver Tier)"
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
        help="Log intent without making Gmail API calls",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=120,
        help="Poll interval in seconds (default: 120)",
    )
    args = parser.parse_args()

    vault_path = Path(args.vault).resolve()
    if not vault_path.exists():
        print(f"ERROR: Vault path does not exist: {vault_path}")
        sys.exit(1)

    watcher = GmailWatcher(
        vault_path=str(vault_path),
        dry_run=args.dry_run,
        check_interval=args.interval,
    )
    watcher.run()


if __name__ == "__main__":
    main()
