"""
orchestrator.py - AI Employee Watcher Orchestrator (Gold Tier)

Starts all watcher scripts as subprocesses and keeps them alive with:
  - Circuit Breaker per watcher (CLOSED → OPEN → HALF_OPEN → CLOSED)
  - Human alert files in vault/Needs_Action/ when a watcher goes OPEN
  - Graceful degradation — one crashed watcher never kills the others
  - Comprehensive crash logging with traceback capture
  - Dashboard health section updated on every status change
  - Midnight daily summary

Usage:
    python scheduler/orchestrator.py
    python scheduler/orchestrator.py --vault ./vault --dry-run

Circuit Breaker Thresholds:
    FAILURE_THRESHOLD = 3 crashes
    CRASH_WINDOW      = 5 minutes
    BASE_WAIT         = 10 minutes (doubles on each OPEN)
    HALF_OPEN_GRACE   = 60 seconds stable = circuit CLOSED

Requirements:
    pip install python-dotenv
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] orchestrator: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("orchestrator")

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent

# Timing
RESTART_DELAY     = 10    # s between crash and next restart (CLOSED state)
HEALTH_INTERVAL   = 5     # s between health-check ticks
HALF_OPEN_GRACE   = 60    # s a HALF_OPEN process must survive to confirm recovery

# Circuit breaker
FAILURE_THRESHOLD = 3     # crashes within CRASH_WINDOW → OPEN
CRASH_WINDOW      = 300   # s = 5 minutes
BASE_WAIT         = 600   # s = 10 minutes before first HALF_OPEN attempt
MAX_WAIT          = 3600  # s = 1 hour cap on backoff

# Circuit states
CLOSED    = "CLOSED"
OPEN      = "OPEN"
HALF_OPEN = "HALF_OPEN"

# Watchers to manage
WATCHERS = [
    {
        "name": "FileSystemWatcher",
        "script": "watchers/filesystem_watcher.py",
        "extra_args": [],
    },
    {
        "name": "GmailWatcher",
        "script": "watchers/gmail_watcher.py",
        "extra_args": ["--interval", "120"],
    },
    {
        "name": "LinkedInWatcher",
        "script": "watchers/linkedin_watcher.py",
        "extra_args": ["--interval", "300"],
    },
    {
        "name": "FacebookWatcher",
        "script": "watchers/facebook_watcher.py",
        "extra_args": ["--interval", "300"],
    },
    {
        "name": "InstagramWatcher",
        "script": "watchers/instagram_watcher.py",
        "extra_args": ["--interval", "300"],
    },
    {
        "name": "TwitterWatcher",
        "script": "watchers/twitter_watcher.py",
        "extra_args": ["--interval", "300"],
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Vault log helper
# ─────────────────────────────────────────────────────────────────────────────

def log_event(logs_dir: Path, action_type: str, notes: str,
              result: str = "success", extra: dict | None = None) -> None:
    """Append a structured entry to today's vault log file."""
    log_file = logs_dir / f"{datetime.now().strftime('%Y-%m-%d')}.json"
    entry: dict = {
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "action_type": action_type,
        "actor":       "orchestrator",
        "source_file": "scheduler/orchestrator.py",
        "result":      result,
        "notes":       notes,
    }
    if extra:
        entry.update(extra)

    entries: list = []
    if log_file.exists():
        try:
            entries = json.loads(log_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            entries = []
    entries.append(entry)
    log_file.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# Circuit Breaker
# ─────────────────────────────────────────────────────────────────────────────

class CircuitBreaker:
    """
    Three-state circuit breaker per watcher.

    CLOSED   → Normal operation. Records crash timestamps.
    OPEN     → Watcher disabled. Waits `current_wait` seconds.
    HALF_OPEN→ One test restart allowed. If it survives HALF_OPEN_GRACE → CLOSED.
               If it crashes → OPEN with doubled wait.
    """

    def __init__(self, name: str,
                 failure_threshold: int = FAILURE_THRESHOLD,
                 window: int = CRASH_WINDOW,
                 base_wait: int = BASE_WAIT) -> None:
        self.name              = name
        self.failure_threshold = failure_threshold
        self.window            = window
        self.base_wait         = base_wait

        self.state: str        = CLOSED
        self.crash_wall_times: list[float] = []   # wall-clock timestamps
        self.crash_messages:   list[str]   = []   # captured stderr per crash
        self.open_count:       int         = 0    # how many times OPEN'd
        self.current_wait:     int         = base_wait
        self.open_at_mono:     float       = 0.0  # monotonic.time() when OPEN'd

    # ── Crash recording ───────────────────────────────────────────────────────

    def record_crash(self, error_msg: str) -> bool:
        """Record a crash. Returns True if the circuit just opened."""
        now = time.time()

        # Prune crashes outside the rolling window
        self.crash_wall_times = [
            t for t in self.crash_wall_times if now - t < self.window
        ]
        self.crash_wall_times.append(now)
        self.crash_messages.append(error_msg[:800])
        if len(self.crash_messages) > 20:
            self.crash_messages = self.crash_messages[-20:]

        if (self.state == CLOSED
                and len(self.crash_wall_times) >= self.failure_threshold):
            self._open()
            return True
        return False

    def record_half_open_failure(self) -> None:
        """HALF_OPEN test restart failed — go back to OPEN with doubled wait."""
        self.open_count += 1
        self.current_wait = min(self.current_wait * 2, MAX_WAIT)
        self._open()

    def record_success(self) -> None:
        """Process survived HALF_OPEN_GRACE — circuit CLOSED."""
        self.state             = CLOSED
        self.crash_wall_times  = []
        self.open_count        = 0
        self.current_wait      = self.base_wait
        self.open_at_mono      = 0.0

    # ── Time-to-half-open check ───────────────────────────────────────────────

    def ready_for_half_open(self) -> bool:
        """True if OPEN wait has elapsed and we should try HALF_OPEN."""
        return (self.state == OPEN
                and time.monotonic() - self.open_at_mono >= self.current_wait)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _open(self) -> None:
        self.state        = OPEN
        self.open_at_mono = time.monotonic()
        logger.error(
            f"[CircuitBreaker] {self.name} → OPEN "
            f"(attempt #{self.open_count + 1}, wait {self.current_wait}s)"
        )

    @property
    def recent_crash_count(self) -> int:
        now = time.time()
        return sum(1 for t in self.crash_wall_times if now - t < self.window)

# ─────────────────────────────────────────────────────────────────────────────
# Dashboard health update
# ─────────────────────────────────────────────────────────────────────────────

def update_dashboard_health(vault: Path, watchers: list) -> None:
    """
    Append or replace a '## Watcher Health' section in Dashboard.md.
    Non-destructive — only touches that one section.
    """
    dashboard = vault / "Dashboard.md"
    if not dashboard.exists():
        return

    state_labels = {
        CLOSED:    "✅ RUNNING",
        OPEN:      "🔴 OPEN",
        HALF_OPEN: "🟡 HALF-OPEN",
    }

    rows = "\n".join(
        f"| {wp.name} | {state_labels.get(wp.circuit.state, '❓')} "
        f"| {wp.circuit.recent_crash_count}/{wp.circuit.failure_threshold} "
        f"| {int(wp.circuit.current_wait // 60)}min wait "
        f"({'active' if wp.circuit.state in (OPEN, HALF_OPEN) else '-'}) |"
        for wp in watchers
    )

    health_block = (
        f"\n## Watcher Health\n\n"
        f"*Updated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}*\n\n"
        f"| Watcher | Status | Crashes (5min) | Circuit Backoff |\n"
        f"|---------|--------|----------------|----------------|\n"
        f"{rows}\n"
    )

    content = dashboard.read_text(encoding="utf-8")

    if "## Watcher Health" in content:
        content = re.sub(
            r"\n## Watcher Health\n.*?(?=\n## |\Z)",
            health_block,
            content,
            flags=re.DOTALL,
        )
    else:
        content += health_block

    dashboard.write_text(content, encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# Daily summary
# ─────────────────────────────────────────────────────────────────────────────

def write_daily_summary(logs_dir: Path, watchers: list) -> None:
    """Write a daily summary entry to the current log file."""
    today      = datetime.now().strftime("%Y-%m-%d")
    log_file   = logs_dir / f"{today}.json"

    entries: list = []
    if log_file.exists():
        try:
            entries = json.loads(log_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            entries = []

    crash_counts = {
        wp.name: sum(
            1 for e in entries
            if e.get("action_type") in ("watcher_crashed", "watcher_circuit_open")
            and wp.name in e.get("notes", "")
        )
        for wp in watchers
    }

    entries.append({
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "action_type":   "daily_summary",
        "actor":         "orchestrator",
        "date":          today,
        "crash_counts":  crash_counts,
        "total_crashes": sum(crash_counts.values()),
        "circuit_states": {wp.name: wp.circuit.state for wp in watchers},
        "result":        "success",
        "notes":         f"Daily summary for {today}",
    })

    log_file.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Daily summary written → {log_file.name}")

# ─────────────────────────────────────────────────────────────────────────────
# Suggested fixes per watcher (used in ALERT files)
# ─────────────────────────────────────────────────────────────────────────────

_SUGGESTED_FIXES: dict[str, str] = {
    "GmailWatcher": (
        "1. Check `secrets/gmail_token.json` is valid and not expired\n"
        "2. Verify `GMAIL_CREDENTIALS_PATH` and `GMAIL_TOKEN_PATH` in `.env`\n"
        "3. Re-authenticate: `python setup/gmail_auth.py`\n"
        "4. Check Gmail API quota at https://console.cloud.google.com/"
    ),
    "LinkedInWatcher": (
        "1. LinkedIn session may have expired — `secrets/linkedin_session/`\n"
        "2. Re-authenticate via Playwright: open LinkedIn in browser and save session\n"
        "3. Check `LINKEDIN_SESSION_PATH` in `.env`\n"
        "4. Verify `playwright` is installed: `pip install playwright`"
    ),
    "FileSystemWatcher": (
        "1. Check vault path exists: `ls ./vault/Inbox/`\n"
        "2. Verify `watchdog` is installed: `pip install watchdog`\n"
        "3. Check file permissions on vault directory\n"
        "4. Review recent log entries for the specific error"
    ),
    "FacebookWatcher": (
        "1. Facebook session may have expired — `secrets/facebook_storage.json`\n"
        "2. Re-authenticate: `python setup/save_social_sessions.py --platform facebook`\n"
        "3. Check `FACEBOOK_SESSION_PATH` in `.env`\n"
        "4. Verify `playwright` is installed: `pip install playwright && python -m playwright install chromium`"
    ),
    "InstagramWatcher": (
        "1. Instagram session may have expired — `secrets/instagram_storage.json`\n"
        "2. Re-authenticate: `python setup/save_social_sessions.py --platform instagram`\n"
        "3. Check `INSTAGRAM_SESSION_PATH` in `.env`\n"
        "4. Verify `playwright` is installed: `pip install playwright && python -m playwright install chromium`"
    ),
    "TwitterWatcher": (
        "1. Twitter/X session may have expired — `secrets/twitter_storage.json`\n"
        "2. Re-authenticate: `python setup/save_social_sessions.py --platform twitter`\n"
        "3. Check `TWITTER_SESSION_PATH` in `.env`\n"
        "4. Verify `playwright` is installed: `pip install playwright && python -m playwright install chromium`"
    ),
}

_DEFAULT_FIX = (
    "1. Review `vault/Logs/` for specific error messages\n"
    "2. Check Python dependencies: `pip install -r requirements.txt`\n"
    "3. Verify environment variables in `.env`\n"
    "4. Run the watcher manually to reproduce the error"
)

# ─────────────────────────────────────────────────────────────────────────────
# Watcher Process (with circuit breaker)
# ─────────────────────────────────────────────────────────────────────────────

class WatcherProcess:
    """Wraps a watcher subprocess with a circuit breaker and crash alerting."""

    def __init__(self, name: str, script: str, extra_args: list,
                 vault_path: str, dry_run: bool,
                 logs_dir: Path, needs_action_dir: Path, vault: Path) -> None:
        self.name             = name
        self.script           = script
        self.extra_args       = extra_args
        self.vault_path       = vault_path
        self.dry_run          = dry_run
        self.logs_dir         = logs_dir
        self.needs_action_dir = needs_action_dir
        self.vault            = vault

        self.process:         subprocess.Popen | None = None
        self.circuit          = CircuitBreaker(name)
        self.restart_count:   int   = 0
        self.restart_at:      float = 0.0   # monotonic timestamp for next restart
        self.half_open_start: float = 0.0   # when HALF_OPEN began
        self._last_pid:       int   = -1    # PID of last handled crash

    # ── Process management ────────────────────────────────────────────────────

    def _build_cmd(self) -> list[str]:
        cmd = [sys.executable, str(PROJECT_ROOT / self.script),
               "--vault", self.vault_path]
        if self.dry_run:
            cmd.append("--dry-run")
        cmd.extend(self.extra_args)
        return cmd

    def _spawn(self) -> None:
        cmd = self._build_cmd()
        logger.info(f"[{self.name}] Spawning: {' '.join(cmd)}")
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.restart_count += 1
        log_event(
            self.logs_dir, "watcher_started",
            f"{self.name} started (PID={self.process.pid}, "
            f"restart=#{self.restart_count}, circuit={self.circuit.state})",
            extra={"watcher": self.name, "circuit_state": self.circuit.state},
        )

    def start(self) -> None:
        """Initial start (called once at orchestrator startup)."""
        self.restart_count = 0  # reset so _spawn increments to 1
        self._spawn()

    def is_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def stop(self) -> None:
        if self.is_alive():
            logger.info(f"[{self.name}] Stopping (PID={self.process.pid})")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

    # ── Output capture ────────────────────────────────────────────────────────

    def _drain_output(self) -> str:
        """Read all buffered stdout/stderr from an already-dead process."""
        if self.process and self.process.stdout:
            try:
                raw = self.process.stdout.read()
                return (raw or "").strip()[-2000:]
            except Exception:
                return ""
        return ""

    # ── Health check tick (called every HEALTH_INTERVAL) ─────────────────────

    def check_and_restart(self, all_watchers: list) -> None:
        """
        Non-blocking health check. Must return quickly — never sleeps.
        Manages the full CLOSED → OPEN → HALF_OPEN → CLOSED state machine.
        """

        # ── State: OPEN ───────────────────────────────────────────────────────
        if self.circuit.state == OPEN:
            if self.circuit.ready_for_half_open():
                logger.info(f"[{self.name}] Circuit → HALF_OPEN — test restart")
                log_event(
                    self.logs_dir, "circuit_half_open",
                    f"{self.name}: entering HALF_OPEN after {self.circuit.current_wait}s",
                    extra={"watcher": self.name},
                )
                self.circuit.state = HALF_OPEN
                self.half_open_start = time.monotonic()
                self._spawn()
            # else: still waiting — do nothing (other watchers continue running)
            return

        # ── State: CLOSED or HALF_OPEN — process alive ────────────────────────
        if self.is_alive():
            if (self.circuit.state == HALF_OPEN
                    and time.monotonic() - self.half_open_start >= HALF_OPEN_GRACE):
                self.circuit.record_success()
                logger.info(f"[{self.name}] Circuit → CLOSED ✓ (survived {HALF_OPEN_GRACE}s)")
                log_event(
                    self.logs_dir, "circuit_closed",
                    f"{self.name}: HALF_OPEN test passed — circuit CLOSED",
                    extra={"watcher": self.name, "circuit_state": CLOSED},
                )
                update_dashboard_health(self.vault, all_watchers)
            return

        # ── Process is dead ───────────────────────────────────────────────────
        current_pid = self.process.pid if self.process else -1
        if current_pid == self._last_pid:
            # Already handled this crash event; just check if restart timer fired
            if self.restart_at > 0 and time.monotonic() >= self.restart_at:
                self.restart_at = 0.0
                self._spawn()
            return

        # New crash — handle it once
        self._last_pid  = current_pid
        exit_code       = self.process.returncode if self.process else "?"
        error_output    = self._drain_output()

        # ── Clean exit in dry-run: not a crash, just schedule a restart ───────
        # Dry-run watchers exit with code 0 after one cycle — this is correct
        # behaviour, not a failure. Don't penalise the circuit breaker.
        if exit_code == 0 and self.dry_run:
            logger.info(
                f"[{self.name}] Dry-run cycle complete (exit=0) — "
                f"rescheduling in {RESTART_DELAY}s"
            )
            self.restart_at = time.monotonic() + RESTART_DELAY
            return

        # ── HALF_OPEN crash → back to OPEN ────────────────────────────────────
        if self.circuit.state == HALF_OPEN:
            logger.error(
                f"[{self.name}] HALF_OPEN test failed (exit={exit_code}) "
                f"→ OPEN (wait {min(self.circuit.current_wait * 2, MAX_WAIT)}s)"
            )
            self.circuit.record_half_open_failure()
            self._log_crash(exit_code, error_output)
            update_dashboard_health(self.vault, all_watchers)
            return

        # ── CLOSED crash → maybe open circuit ─────────────────────────────────
        just_opened = self.circuit.record_crash(error_output)
        self._log_crash(exit_code, error_output)

        if just_opened:
            logger.error(
                f"[{self.name}] Circuit → OPEN "
                f"({self.circuit.recent_crash_count} crashes in {CRASH_WINDOW}s window)"
            )
            self._create_alert_file()
            update_dashboard_health(self.vault, all_watchers)
            return

        # Still CLOSED — schedule a simple restart
        logger.warning(
            f"[{self.name}] Crashed (exit={exit_code}), "
            f"restarting in {RESTART_DELAY}s "
            f"[{self.circuit.recent_crash_count}/{FAILURE_THRESHOLD} in window]"
        )
        self.restart_at = time.monotonic() + RESTART_DELAY

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log_crash(self, exit_code, error_output: str) -> None:
        log_event(
            self.logs_dir,
            "watcher_crashed",
            f"{self.name} exited (code={exit_code}) | circuit={self.circuit.state}",
            result="error",
            extra={
                "watcher":        self.name,
                "exit_code":      exit_code,
                "circuit_state":  self.circuit.state,
                "crash_count":    self.circuit.recent_crash_count,
                "restart_number": self.restart_count,
                "traceback":      error_output[-1000:] if error_output else "(none)",
            },
        )

    # ── Alert file ────────────────────────────────────────────────────────────

    def _create_alert_file(self) -> None:
        """Write a Needs_Action alert file so the human sees the watcher is down."""
        alert_path = self.needs_action_dir / f"ALERT_{self.name}_DOWN.md"

        # Format crash history
        crash_history_lines = []
        for wall_t, msg in zip(
            self.circuit.crash_wall_times[-5:],
            self.circuit.crash_messages[-5:],
        ):
            ts = datetime.fromtimestamp(wall_t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            preview = (msg[:120] + "…") if len(msg) > 120 else msg or "(no output)"
            crash_history_lines.append(f"- `{ts}` — {preview}")

        crash_history = "\n".join(crash_history_lines) or "- (no crash detail captured)"
        last_error    = (self.circuit.crash_messages[-1] if self.circuit.crash_messages
                         else "(none)")[:1500]
        fix           = _SUGGESTED_FIXES.get(self.name, _DEFAULT_FIX)
        wait_min      = int(self.circuit.current_wait // 60)
        now_iso       = datetime.now(timezone.utc).isoformat()
        now_fmt       = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

        content = f"""---
type: alert
watcher: {self.name}
priority: high
status: pending
created: {now_iso}
circuit_state: OPEN
crash_count: {len(self.circuit.crash_wall_times)}
next_retry_minutes: {wait_min}
---

# ALERT: {self.name} is DOWN 🔴

**{self.name} has crashed {len(self.circuit.crash_wall_times)} times within 5 minutes.**
The circuit breaker is **OPEN** — this watcher is temporarily disabled.
All other watchers continue running normally.

## Crash History (most recent 5)

{crash_history}

## Last Error Output

```
{last_error}
```

## Auto-Recovery Plan

The orchestrator will automatically attempt a **HALF-OPEN** test restart in **{wait_min} minutes**.

| Outcome | Next State |
|---------|-----------|
| Test restart survives 60s | Circuit → CLOSED ✅ (no action needed) |
| Test restart crashes again | Circuit → OPEN 🔴 (wait doubles: {wait_min * 2}min) |

## Suggested Manual Fix

{fix}

## To Cancel and Fix Now

1. Fix the underlying issue (see above)
2. Move this file to `vault/Done/` to acknowledge
3. The orchestrator will detect recovery on next HALF_OPEN attempt

---
*Generated by Orchestrator Gold Tier — {now_fmt}*
"""
        alert_path.write_text(content, encoding="utf-8")
        logger.warning(f"[{self.name}] Alert written → {alert_path.name}")
        log_event(
            self.logs_dir, "watcher_circuit_open",
            f"{self.name}: circuit OPEN — alert created at {alert_path.name}",
            result="error",
            extra={"watcher": self.name, "alert_file": str(alert_path.name)},
        )

# ─────────────────────────────────────────────────────────────────────────────
# Main orchestration loop
# ─────────────────────────────────────────────────────────────────────────────

def run(vault_path: str, dry_run: bool) -> None:
    vault            = Path(vault_path).resolve()
    logs_dir         = vault / "Logs"
    needs_action_dir = vault / "Needs_Action"
    logs_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Orchestrator (Gold) starting — vault={vault}, dry_run={dry_run}")
    log_event(logs_dir, "orchestrator_started",
              f"Gold Tier orchestrator started | vault={vault} | dry_run={dry_run}")

    processes = [
        WatcherProcess(
            name             = w["name"],
            script           = w["script"],
            extra_args       = w["extra_args"],
            vault_path       = str(vault),
            dry_run          = dry_run,
            logs_dir         = logs_dir,
            needs_action_dir = needs_action_dir,
            vault            = vault,
        )
        for w in WATCHERS
    ]

    # Start all watchers
    for wp in processes:
        wp.start()
    update_dashboard_health(vault, processes)
    logger.info("All watchers started. Health monitoring active.")

    last_summary_date = datetime.now().strftime("%Y-%m-%d")

    try:
        while True:
            # ── Health check each watcher independently ───────────────────────
            for wp in processes:
                try:
                    wp.check_and_restart(processes)
                except Exception as exc:
                    # Never let the orchestrator die because of a single watcher
                    logger.error(f"[{wp.name}] Unexpected orchestrator error: {exc}")
                    log_event(logs_dir, "orchestrator_error",
                              f"Unhandled exception managing {wp.name}: {exc}",
                              result="error")

            # ── Midnight daily summary ────────────────────────────────────────
            today = datetime.now().strftime("%Y-%m-%d")
            if today != last_summary_date:
                write_daily_summary(logs_dir, processes)
                last_summary_date = today

            time.sleep(HEALTH_INTERVAL)

    except KeyboardInterrupt:
        logger.info("Orchestrator stopping (Ctrl+C)…")
        log_event(logs_dir, "orchestrator_stopped", "Stopped by user")
        for wp in processes:
            wp.stop()
        update_dashboard_health(vault, processes)
        write_daily_summary(logs_dir, processes)
        logger.info("All watchers stopped. Goodbye.")

# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI Employee Watcher Orchestrator (Gold Tier)"
    )
    parser.add_argument(
        "--vault",
        default=os.getenv("VAULT_PATH", "./vault"),
        help="Path to the Obsidian vault (default: ./vault)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=os.getenv("DRY_RUN", "false").lower() == "true",
        help="Pass --dry-run to all watchers (no external API calls)",
    )
    args = parser.parse_args()

    vault_path = Path(args.vault).resolve()
    if not vault_path.exists():
        print(f"ERROR: Vault path does not exist: {vault_path}", file=sys.stderr)
        sys.exit(1)

    run(str(vault_path), args.dry_run)


if __name__ == "__main__":
    main()
