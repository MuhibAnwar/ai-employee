#!/usr/bin/env python3
"""
stop_hook.py — Ralph Wiggum Stop Hook (Gold Tier)

Intercepts Claude Code's Stop event. Checks whether the active task is
complete; if not, prints a re-injection prompt and exits with code 1
(blocking the stop). If done or max iterations reached, exits with code 0.

Exit codes:
  0 — allow stop  (task complete, max iterations reached, or no active task)
  1 — block stop  (re-inject prompt, keep working)

Input  (stdin):  JSON payload from Claude Code
Output (stdout): Re-injection prompt shown to Claude when blocking

Claude Code hook registration (.claude/settings.json):
  {
    "hooks": {
      "Stop": [{"matcher": "", "hooks": [{"type": "command",
                "command": "python .claude/hooks/stop_hook.py"}]}]
    }
  }
"""

import json
import sys
import os
import re
from pathlib import Path
from datetime import datetime, timezone

# ─────────────────────────────────────────────────────────────────────────────
# Paths  (resolve relative to this file's location: .claude/hooks/)
# ─────────────────────────────────────────────────────────────────────────────

HOOKS_DIR    = Path(__file__).parent                    # .claude/hooks/
CLAUDE_DIR   = HOOKS_DIR.parent                         # .claude/
PROJECT_ROOT = CLAUDE_DIR.parent                        # project root

VAULT_PATH       = Path(os.getenv("VAULT_PATH", str(PROJECT_ROOT / "vault")))
ACTIVE_TASK_FILE = VAULT_PATH / "Plans" / "ACTIVE_TASK.md"
PLANS_DIR        = VAULT_PATH / "Plans"
DONE_DIR         = VAULT_PATH / "Done"
LOGS_DIR         = VAULT_PATH / "Logs"

DEFAULT_MAX_ITERATIONS = 10

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

def log_iteration(iteration: int, max_iter: int, task: str,
                  reason: str, allowed_stop: bool) -> None:
    """Append a structured log entry to today's vault log file."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.json"

    entries: list = []
    if log_file.exists():
        try:
            entries = json.loads(log_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            entries = []

    entries.append({
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "action_type":    "ralph_wiggum_iteration",
        "actor":          "stop_hook",
        "iteration":      iteration,
        "max_iterations": max_iter,
        "task":           task[:120],
        "allowed_stop":   allowed_stop,
        "notes":          reason,
    })

    log_file.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8"
    )

# ─────────────────────────────────────────────────────────────────────────────
# ACTIVE_TASK.md helpers
# ─────────────────────────────────────────────────────────────────────────────

def read_active_task() -> dict:
    """Parse YAML frontmatter from ACTIVE_TASK.md. Returns {} if absent."""
    if not ACTIVE_TASK_FILE.exists():
        return {}

    content = ACTIVE_TASK_FILE.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}

    meta: dict = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta


def update_iteration_count(new_count: int) -> None:
    """Write updated current_iteration back into ACTIVE_TASK.md frontmatter."""
    if not ACTIVE_TASK_FILE.exists():
        return
    content = ACTIVE_TASK_FILE.read_text(encoding="utf-8")
    updated = re.sub(
        r"^(current_iteration:\s*)\d+",
        rf"\g<1>{new_count}",
        content,
        flags=re.MULTILINE,
    )
    ACTIVE_TASK_FILE.write_text(updated, encoding="utf-8")


def archive_active_task() -> None:
    """Move ACTIVE_TASK.md to vault/Done/ when the loop completes."""
    if ACTIVE_TASK_FILE.exists() and DONE_DIR.exists():
        dest = DONE_DIR / "ACTIVE_TASK_COMPLETED.md"
        if dest.exists():
            dest.unlink()
        ACTIVE_TASK_FILE.rename(dest)

# ─────────────────────────────────────────────────────────────────────────────
# Task state checks
# ─────────────────────────────────────────────────────────────────────────────

def incomplete_plans() -> list[Path]:
    """Return PLAN_*.md files in Plans/ whose names are NOT yet in Done/."""
    if not PLANS_DIR.exists():
        return []
    done_names = (
        {f.name for f in DONE_DIR.glob("PLAN_*.md")}
        if DONE_DIR.exists()
        else set()
    )
    return [
        f for f in PLANS_DIR.glob("PLAN_*.md")
        if f.name not in done_names
    ]


def task_complete_in_transcript(transcript_path: str) -> bool:
    """Return True if Claude output <promise>TASK_COMPLETE</promise>."""
    if not transcript_path:
        return False
    p = Path(transcript_path)
    if not p.exists():
        return False
    try:
        content = p.read_text(encoding="utf-8", errors="ignore")
        return "<promise>TASK_COMPLETE</promise>" in content
    except Exception:
        return False

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    # ── Parse Claude Code's JSON payload ─────────────────────────────────────
    payload: dict = {}
    try:
        raw = sys.stdin.read()
        if raw.strip():
            payload = json.loads(raw)
    except Exception:
        pass

    transcript_path: str = payload.get("transcript_path", "")

    # ── Read active task ──────────────────────────────────────────────────────
    meta = read_active_task()
    if not meta:
        # No active Ralph Wiggum task — allow Claude to stop normally
        sys.exit(0)

    task_desc    = meta.get("task", "Unknown task")
    max_iter     = int(meta.get("max_iterations", DEFAULT_MAX_ITERATIONS))
    current_iter = int(meta.get("current_iteration", 0)) + 1

    update_iteration_count(current_iter)

    # ── Check 1: TASK_COMPLETE promise in transcript ──────────────────────────
    if task_complete_in_transcript(transcript_path):
        log_iteration(current_iter, max_iter, task_desc,
                      "TASK_COMPLETE promise detected in transcript", True)
        archive_active_task()
        sys.exit(0)

    # ── Check 2: All plans moved to Done ─────────────────────────────────────
    pending = incomplete_plans()
    if not pending:
        log_iteration(current_iter, max_iter, task_desc,
                      "All PLAN_*.md files are in vault/Done/ — task complete", True)
        archive_active_task()
        sys.exit(0)

    # ── Check 3: Max iterations guard ────────────────────────────────────────
    if current_iter >= max_iter:
        log_iteration(current_iter, max_iter, task_desc,
                      f"Max iterations ({max_iter}) reached — forcing stop", True)
        print(
            f"[Ralph Wiggum] Max iterations ({max_iter}) reached.\n"
            f"Stopping to prevent infinite loop. Review vault/Plans/ manually.",
            file=sys.stderr,
        )
        archive_active_task()
        sys.exit(0)

    # ── Block stop: re-inject prompt ──────────────────────────────────────────
    pending_names = [f.name for f in pending]
    log_iteration(current_iter, max_iter, task_desc,
                  f"Iteration {current_iter}/{max_iter} — "
                  f"incomplete plans: {pending_names}", False)

    reinject = (
        f"[Ralph Wiggum — Iteration {current_iter}/{max_iter}]\n\n"
        f"You have not finished the task yet. Keep working.\n\n"
        f"ACTIVE TASK: {task_desc}\n\n"
        f"INCOMPLETE PLAN FILES ({len(pending_names)}):\n"
        + "\n".join(f"  - vault/Plans/{n}" for n in pending_names)
        + "\n\n"
        "Continue working. When finished, do ONE of:\n"
        "  A) Move all plan files from vault/Plans/ to vault/Done/\n"
        "  B) Output exactly: <promise>TASK_COMPLETE</promise>\n\n"
        "Do NOT stop until one of those conditions is met."
    )

    print(reinject)
    sys.exit(1)


if __name__ == "__main__":
    main()
