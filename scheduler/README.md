# Scheduler — AI Employee Orchestrator

> Runs all watcher scripts continuously and restarts them if they crash.

The orchestrator (`orchestrator.py`) manages three subprocesses:

| Watcher | Script | Interval |
|---------|--------|----------|
| File System | `watchers/filesystem_watcher.py` | Instant (watchdog) |
| Gmail | `watchers/gmail_watcher.py` | Every 120s |
| LinkedIn | `watchers/linkedin_watcher.py` | Every 300s |

---

## Running Manually

```bash
# From project root
python scheduler/orchestrator.py --vault ./vault

# Dry run (no external API calls)
python scheduler/orchestrator.py --vault ./vault --dry-run
```

Press `Ctrl+C` to stop all watchers gracefully.

---

## Scheduling on Windows 11 (Task Scheduler)

### Step 1: Edit the XML file

Open `scheduler/schedule_windows.xml` and update the three paths:

```xml
<Command>python</Command>
<Arguments>scheduler\orchestrator.py --vault .\vault</Arguments>
<WorkingDirectory>C:\Users\YourName\ai-employee-bronze</WorkingDirectory>
```

Replace `C:\Users\YourName\ai-employee-bronze` with the absolute path to your project root.

If Python is not on your PATH, use the full path to `python.exe`:
```xml
<Command>C:\Users\YourName\AppData\Local\Programs\Python\Python313\python.exe</Command>
```

### Step 2: Import the task

Open **Command Prompt as Administrator** and run:

```cmd
schtasks /create /xml "scheduler\schedule_windows.xml" /tn "AIEmployee" /f
```

### Step 3: Verify

```cmd
schtasks /query /tn "AIEmployee" /fo LIST /v
```

Expected output:
```
TaskName:    \AIEmployee
Status:      Ready
Run As User: YOURUSERNAME
```

### Step 4: Test it

```cmd
schtasks /run /tn "AIEmployee"
```

Check that `vault/Logs/YYYY-MM-DD.json` contains orchestrator startup entries.

---

## Managing the Task

```cmd
# Run manually
schtasks /run /tn "AIEmployee"

# Stop
schtasks /end /tn "AIEmployee"

# Disable (keep but don't auto-start)
schtasks /change /tn "AIEmployee" /disable

# Re-enable
schtasks /change /tn "AIEmployee" /enable

# Delete permanently
schtasks /delete /tn "AIEmployee" /f
```

---

## Alternative: PM2 (cross-platform, recommended for power users)

If you have Node.js installed, [PM2](https://pm2.keymetrics.io/) offers better
log management and auto-restart:

```bash
npm install -g pm2

# Start
pm2 start scheduler/orchestrator.py --interpreter python --name ai-employee

# Auto-start on Windows boot
pm2 startup
pm2 save

# Monitor
pm2 status
pm2 logs ai-employee

# Stop
pm2 stop ai-employee
```

---

## Logs

All orchestrator events (starts, restarts, crashes) are written to:
```
vault/Logs/YYYY-MM-DD.json
```

Look for `"actor": "orchestrator"` entries.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Task doesn't start | Check Python path in XML, run as admin |
| `Vault path does not exist` | Edit `<WorkingDirectory>` to correct project path |
| Gmail watcher exits immediately | Run `gmail_watcher.py` manually to trigger OAuth flow |
| LinkedIn watcher exits immediately | Session expired — re-authenticate (see linkedin_watcher.py docs) |
| Orchestrator not restarting crashed watchers | Check `HEALTH_INTERVAL` and `RESTART_DELAY` in orchestrator.py |
