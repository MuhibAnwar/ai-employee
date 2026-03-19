"""
twitter_watcher.py - Twitter/X Mentions Watcher (Gold Tier)

Uses tweepy (Twitter API v1.1 OAuth1) to check mentions.
Falls back to WAITING mode if credentials are missing.

Usage:
    python watchers/twitter_watcher.py --vault ./vault
    python watchers/twitter_watcher.py --vault ./vault --dry-run

Setup:
    Set in .env:
        TWITTER_API_KEY=...
        TWITTER_API_SECRET=...
        TWITTER_ACCESS_TOKEN=...
        TWITTER_ACCESS_SECRET=...
    Get credentials from https://developer.twitter.com/

Keyword filtering (creates action file if ANY match):
    urgent, invoice, payment, order, complaint, dm, mention,
    pricing, proposal, partnership, sponsor, deal, support

Requirements:
    pip install tweepy python-dotenv  (or: uv add tweepy)
"""

import argparse
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
    import tweepy
    TWEEPY_AVAILABLE = True
except ImportError:
    TWEEPY_AVAILABLE = False


ACTION_KEYWORDS = {
    "urgent", "asap", "invoice", "payment", "order", "complaint",
    "dm", "mention", "pricing", "proposal", "partnership", "sponsor",
    "deal", "support", "client", "refund", "deadline", "collaboration",
}

SEEN_FILE = PROJECT_ROOT / "secrets" / "twitter_seen.txt"


class TwitterWatcher(BaseWatcher):
    """
    Watches Twitter/X mentions using Tweepy API (no browser required).

    Gold Tier Requirement:
      "Twitter/X watcher + posting"
    """

    def __init__(self, vault_path: str, dry_run: bool = False, check_interval: int = 300):
        super().__init__(vault_path, check_interval=check_interval)
        self.dry_run = dry_run
        self.api_key = os.getenv("TWITTER_API_KEY", "")
        self.api_secret = os.getenv("TWITTER_API_SECRET", "")
        self.access_token = os.getenv("TWITTER_ACCESS_TOKEN", "")
        self.access_secret = os.getenv("TWITTER_ACCESS_SECRET", "")
        self._api = None
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

    # ── Tweepy API (lazy init) ────────────────────────────────────────────────

    def _has_credentials(self) -> bool:
        return bool(self.api_key and self.api_secret and self.access_token and self.access_secret)

    def _get_api(self) -> "tweepy.API":
        """Return a cached Tweepy API client."""
        if self._api is None:
            auth = tweepy.OAuth1UserHandler(
                consumer_key=self.api_key,
                consumer_secret=self.api_secret,
                access_token=self.access_token,
                access_token_secret=self.access_secret,
            )
            self._api = tweepy.API(auth, wait_on_rate_limit=True)
        return self._api

    # ── BaseWatcher interface ─────────────────────────────────────────────────

    def check_for_updates(self) -> list:
        if self.dry_run:
            self.logger.info("[DRY_RUN] Skipping Twitter API call — returning empty list.")
            return []

        if not TWEEPY_AVAILABLE:
            raise RuntimeError(
                "tweepy is not installed.\n"
                "Run: pip install tweepy  (or: uv add tweepy)"
            )

        if not self._has_credentials():
            self.logger.warning(
                "[WAITING] Twitter credentials not set. "
                "Set TWITTER_API_KEY, TWITTER_API_SECRET, "
                "TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET in .env"
            )
            return []

        seen = self._load_seen()
        new_items = []

        try:
            api = self._get_api()
            mentions = api.mentions_timeline(count=20, tweet_mode="extended")

            for mention in mentions:
                try:
                    text = mention.full_text.strip()
                    if not text:
                        continue

                    key = self._notification_key(text)
                    if key in seen:
                        continue

                    text_lower = text.lower()
                    if not any(kw in text_lower for kw in ACTION_KEYWORDS):
                        self._mark_seen(key)
                        continue

                    screen_name = mention.user.screen_name
                    tweet_id = mention.id_str
                    url = f"https://x.com/{screen_name}/status/{tweet_id}"

                    new_items.append({
                        "text": text[:500],
                        "url": url,
                        "key": key,
                        "detected_at": datetime.now(timezone.utc).isoformat(),
                    })
                    self._mark_seen(key)

                except Exception as e:
                    self.logger.debug(f"Error parsing mention: {e}")

        except tweepy.TweepyException as e:
            self.logger.error(f"Twitter API error: {e}")
            # Reset so next cycle creates a fresh auth object
            self._api = None
        except Exception as e:
            self.logger.error(f"Unexpected Twitter error: {e}")
            self._api = None

        if new_items:
            self.logger.info(f"Found {len(new_items)} relevant Twitter/X mention(s).")
        else:
            self.logger.debug("No new relevant Twitter/X mentions.")

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

A relevant Twitter/X mention was detected.

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
            self.logger.info("[DRY_RUN] TwitterWatcher started — no API calls will be made.")
            self.check_for_updates()
            self.logger.info("[DRY_RUN] Exiting after one cycle.")
            return

        if not TWEEPY_AVAILABLE:
            self.logger.error(
                "tweepy not installed. Run: pip install tweepy\n"
                "TwitterWatcher cannot start."
            )
            return

        self.logger.info(f"Starting TwitterWatcher (interval={self.check_interval}s)")

        if not self._has_credentials():
            self.logger.warning(
                "[WAITING] Twitter API credentials not set in .env. "
                "Set TWITTER_API_KEY, TWITTER_API_SECRET, "
                "TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET. "
                "Sleeping until credentials are available."
            )
            while not self._has_credentials():
                try:
                    time.sleep(60)
                except KeyboardInterrupt:
                    self.logger.info("TwitterWatcher stopped by user.")
                    return
                # Reload from env in case .env was updated
                self.api_key = os.getenv("TWITTER_API_KEY", "")
                self.api_secret = os.getenv("TWITTER_API_SECRET", "")
                self.access_token = os.getenv("TWITTER_ACCESS_TOKEN", "")
                self.access_secret = os.getenv("TWITTER_ACCESS_SECRET", "")
            self.logger.info("Twitter credentials found. Starting TwitterWatcher.")

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
