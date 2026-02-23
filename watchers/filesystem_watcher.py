"""
filesystem_watcher.py - File System Drop Folder Watcher

Monitors a drop folder (vault/Inbox/) for new files dropped by the user.
When a new file is detected, it creates a structured .md action file in
vault/Needs_Action/ so Claude Code can process it.

This satisfies the Bronze Tier requirement:
  "One working Watcher script (Gmail OR file system monitoring)"

Usage:
    python watchers/filesystem_watcher.py --vault ./vault

Requirements:
    pip install watchdog

How it works:
    1. Monitors vault/Inbox/ for file creation events
    2. When a new file appears, creates a Needs_Action/*.md file with metadata
    3. Logs the event to vault/Logs/YYYY-MM-DD.json
    4. The original file stays in Inbox (Claude moves it to Done after processing)
"""

import argparse
import os
import shutil
import sys
from pathlib import Path
from datetime import datetime, timezone

# Ensure watchers/ package can be imported when run directly
sys.path.insert(0, str(Path(__file__).parent))

from base_watcher import BaseWatcher

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("ERROR: 'watchdog' is not installed. Run: pip install watchdog")
    sys.exit(1)


class DropFolderHandler(FileSystemEventHandler):
    """Handles file system events for the Inbox drop folder."""

    def __init__(self, watcher: "FileSystemWatcher"):
        self.watcher = watcher
        self._processing = set()  # prevent duplicate events

    def on_created(self, event):
        if event.is_directory:
            return
        src = Path(event.src_path)
        # Skip hidden files, .gitkeep, and temp files
        if src.name.startswith(".") or src.suffix in {".tmp", ".part", ".crdownload"}:
            return
        if str(src) in self._processing:
            return
        self._processing.add(str(src))
        try:
            self.watcher.handle_new_file(src)
        finally:
            self._processing.discard(str(src))


class FileSystemWatcher(BaseWatcher):
    """
    Watches vault/Inbox/ for new files dropped by the user.
    Creates structured action files in vault/Needs_Action/.
    """

    def __init__(self, vault_path: str, dry_run: bool = False):
        super().__init__(vault_path, check_interval=5)
        self.dry_run = dry_run
        self._observer = None
        self._pending = []  # files detected but not yet processed

    def check_for_updates(self) -> list:
        """Return pending files (populated by the watchdog handler)."""
        items = list(self._pending)
        self._pending.clear()
        return items

    def handle_new_file(self, source: Path):
        """Called by DropFolderHandler when a file appears in Inbox."""
        self.logger.info(f"New file detected in Inbox: {source.name}")
        self._pending.append(source)

    def create_action_file(self, source: Path) -> Path:
        """
        Create a structured .md action file in Needs_Action/.

        The action file contains:
        - YAML frontmatter (type, source, timestamps, priority, status)
        - File metadata (name, size, extension)
        - Suggested next actions with checkboxes
        """
        now = datetime.now(timezone.utc)
        timestamp_str = now.strftime("%Y%m%dT%H%M%S")

        # Determine priority based on filename keywords
        priority = self._classify_priority(source.name)

        # Gather file metadata
        try:
            size_bytes = source.stat().st_size
            size_str = self._human_size(size_bytes)
        except OSError:
            size_str = "unknown"

        content = f"""---
type: file_drop
source: vault/Inbox/{source.name}
received: {now.isoformat()}
priority: {priority}
status: pending
watcher: FileSystemWatcher
---

# Action Required: New File — {source.name}

A new file was dropped into `/Inbox` and is awaiting processing.

## File Details

| Field | Value |
|-------|-------|
| Name | `{source.name}` |
| Extension | `{source.suffix or 'none'}` |
| Size | {size_str} |
| Dropped at | {now.strftime("%Y-%m-%d %H:%M:%S UTC")} |
| Priority | **{priority.upper()}** |

## Suggested Actions

- [ ] Read and understand the file content
- [ ] Determine if any action is required
- [ ] If action requires approval, create file in `vault/Pending_Approval/`
- [ ] Create a `Plan.md` in `vault/Plans/` if task is multi-step
- [ ] Move original file to `vault/Done/` when complete
- [ ] Update `vault/Dashboard.md`

## Notes

_Add any notes here after reviewing the file._

---
*Created by FileSystemWatcher at {now.strftime("%Y-%m-%d %H:%M:%S UTC")}*
"""

        action_file = self.needs_action / f"FILE_{timestamp_str}_{source.stem}.md"
        action_file.write_text(content, encoding="utf-8")

        self.log_action(
            action_type="file_drop_detected",
            source=str(source),
            result="success",
            notes=f"Action file created: {action_file.name}",
        )
        return action_file

    def _classify_priority(self, filename: str) -> str:
        """Classify priority based on filename keywords (per Company_Handbook.md)."""
        name_lower = filename.lower()
        urgent_keywords = {"urgent", "asap", "deadline", "overdue", "critical"}
        high_keywords = {"invoice", "payment", "contract", "meeting", "proposal", "client"}

        if any(kw in name_lower for kw in urgent_keywords):
            return "urgent"
        if any(kw in name_lower for kw in high_keywords):
            return "high"
        return "normal"

    @staticmethod
    def _human_size(size_bytes: int) -> str:
        """Convert bytes to human-readable size."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    def run(self):
        """Start the watchdog observer and enter the monitoring loop."""
        if self.dry_run:
            self.logger.info(
                "[DRY_RUN] FileSystemWatcher started — monitoring vault/Inbox/ "
                "but no action files will be created."
            )
            self.logger.info("[DRY_RUN] Exiting after one cycle.")
            return

        self.logger.info(f"Monitoring drop folder: {self.inbox}")
        self.logger.info(f"Action files will be created in: {self.needs_action}")
        self.logger.info("Press Ctrl+C to stop.")

        handler = DropFolderHandler(self)
        self._observer = Observer()
        self._observer.schedule(handler, str(self.inbox), recursive=False)
        self._observer.start()

        try:
            import time
            while True:
                # Process any pending files detected by the handler
                items = self.check_for_updates()
                for item in items:
                    try:
                        path = self.create_action_file(item)
                        self.logger.info(f"Created action file: {path.name}")
                    except Exception as e:
                        self.logger.error(f"Failed to process {item.name}: {e}")

                time.sleep(self.check_interval)
        except KeyboardInterrupt:
            self.logger.info("Stopping watcher...")
        finally:
            self._observer.stop()
            self._observer.join()
            self.logger.info("Watcher stopped.")


def main():
    parser = argparse.ArgumentParser(
        description="File System Drop Folder Watcher for AI Employee (Bronze Tier)"
    )
    parser.add_argument(
        "--vault",
        default="./vault",
        help="Path to the Obsidian vault directory (default: ./vault)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=os.getenv("DRY_RUN", "false").lower() == "true",
        help="Log intent without creating action files",
    )
    args = parser.parse_args()

    vault_path = Path(args.vault).resolve()
    if not vault_path.exists():
        print(f"ERROR: Vault path does not exist: {vault_path}")
        print("Create it first or run from the project root.")
        sys.exit(1)

    watcher = FileSystemWatcher(str(vault_path), dry_run=args.dry_run)
    watcher.run()


if __name__ == "__main__":
    main()
