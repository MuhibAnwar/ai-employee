"""
base_watcher.py - Abstract base class for all AI Employee watchers.

All watchers follow the same pattern:
  1. check_for_updates() - detect new items from external source
  2. create_action_file() - write structured .md file to /Needs_Action
  3. run() - loop forever, calling the above on a schedule

Usage:
    Subclass BaseWatcher and implement check_for_updates() and create_action_file().
"""

import time
import logging
import json
from pathlib import Path
from abc import ABC, abstractmethod
from datetime import datetime, timezone


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)


class BaseWatcher(ABC):
    """Abstract base class for all AI Employee watchers."""

    def __init__(self, vault_path: str, check_interval: int = 60):
        self.vault_path = Path(vault_path)
        self.inbox = self.vault_path / "Inbox"
        self.needs_action = self.vault_path / "Needs_Action"
        self.logs_dir = self.vault_path / "Logs"
        self.check_interval = check_interval
        self.logger = logging.getLogger(self.__class__.__name__)

        # Ensure required folders exist
        for folder in [self.inbox, self.needs_action, self.logs_dir]:
            folder.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def check_for_updates(self) -> list:
        """Return list of new items to process."""
        pass

    @abstractmethod
    def create_action_file(self, item) -> Path:
        """Create a structured .md file in Needs_Action folder."""
        pass

    def log_action(self, action_type: str, source: str, result: str, notes: str = ""):
        """Append a structured log entry to today's log file."""
        log_file = self.logs_dir / f"{datetime.now().strftime('%Y-%m-%d')}.json"
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action_type": action_type,
            "actor": self.__class__.__name__,
            "source_file": source,
            "result": result,
            "notes": notes,
        }

        # Read existing log or start fresh
        entries = []
        if log_file.exists():
            try:
                entries = json.loads(log_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                entries = []

        entries.append(entry)
        log_file.write_text(
            json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def run(self):
        """Main loop — check for updates on the configured interval."""
        self.logger.info(
            f"Starting {self.__class__.__name__} "
            f"(interval={self.check_interval}s, vault={self.vault_path})"
        )
        while True:
            try:
                items = self.check_for_updates()
                if items:
                    self.logger.info(f"Found {len(items)} new item(s) to process")
                for item in items:
                    try:
                        path = self.create_action_file(item)
                        self.logger.info(f"Created action file: {path.name}")
                    except Exception as e:
                        self.logger.error(f"Failed to create action file: {e}")
                        self.log_action("create_action_file", str(item), "error", str(e))
            except KeyboardInterrupt:
                self.logger.info("Watcher stopped by user")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error in main loop: {e}")
                self.log_action("watcher_loop", "main", "error", str(e))

            time.sleep(self.check_interval)
