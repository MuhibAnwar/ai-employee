# Silver Tier — Go-Live Setup Checklist

Every item below requires a manual action **outside Claude Code**.
Work through them in order. Check each box when done.

---

## 0. Prerequisites (confirm before anything else)

- [ ] Python 3.13+ installed: `python --version`
- [ ] Node.js 18+ installed: `node --version`
- [ ] Claude Code installed: `claude --version`
- [ ] Project root is: `D:\aa-3\hi\ai-employee-bronze`

---

## 1. Copy and fill in .env

```cmd
cd D:\aa-3\hi\ai-employee-bronze
copy .env.example .env
notepad .env
```

Uncomment and fill these lines (remove the `#`):

```env
VAULT_PATH=./vault
DRY_RUN=true

GMAIL_TOKEN_PATH=./secrets/gmail_token.json
GMAIL_CREDENTIALS_PATH=./secrets/gmail_credentials.json

LINKEDIN_SESSION_PATH=./secrets/linkedin_session
EMAIL_MCP_PORT=3001
```

Leave `DRY_RUN=true` for now — you will flip it to `false` at the end.

- [ ] `.env` file created and filled in

---

## 2. Gmail API — Create OAuth2 credentials

**Do this once. The token is reused by both the Gmail watcher and the Email MCP server.**

### 2a. Create a Google Cloud project and enable Gmail API

1. Go to https://console.cloud.google.com/
2. Create a new project (e.g. "AI Employee")
3. Go to **APIs & Services > Library**
4. Search for **Gmail API** → click **Enable**

### 2b. Create OAuth2 credentials

1. Go to **APIs & Services > Credentials**
2. Click **+ Create Credentials > OAuth client ID**
3. Application type: **Desktop app**
4. Name: "AI Employee"
5. Click **Create**
6. Click **Download JSON**
7. Save the file as:
   ```
   D:\aa-3\hi\ai-employee-bronze\secrets\gmail_credentials.json
   ```
   (create the `secrets\` folder if it doesn't exist)

### 2c. Configure OAuth consent screen

1. Go to **APIs & Services > OAuth consent screen**
2. User type: **External** (unless you have a Google Workspace org)
3. Fill in app name ("AI Employee") and your email
4. Under **Scopes**, add:
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/gmail.send`
   - `https://www.googleapis.com/auth/gmail.compose`
5. Under **Test users**, add your Gmail address
6. Save

### 2d. Run the OAuth consent flow (opens browser)

```cmd
cd D:\aa-3\hi\ai-employee-bronze
python watchers/gmail_watcher.py --vault ./vault
```

A browser window opens. Log in with your Gmail account and click **Allow**.
Token is saved to `secrets\gmail_token.json`. The watcher then starts polling.
Press `Ctrl+C` to stop it after you see "Gmail API authenticated successfully."

- [ ] `secrets\gmail_credentials.json` downloaded and saved
- [ ] `secrets\gmail_token.json` generated (OAuth flow completed)

---

## 3. LinkedIn — Save browser session

**Playwright needs a saved login session so the LinkedIn watcher can run headless.**

### 3a. Install Playwright browser

```cmd
cd D:\aa-3\hi\ai-employee-bronze
python -m playwright install chromium
```

### 3b. Open a browser, log in to LinkedIn, save session

```cmd
python -m playwright open --save-storage=secrets\linkedin_session https://www.linkedin.com
```

A Chromium window opens. Log in to LinkedIn manually. Once you are on the
LinkedIn home page and fully logged in, **close the browser window**.
The session is saved to `secrets\linkedin_session`.

### 3c. Verify the session works

```cmd
python watchers/linkedin_watcher.py --vault ./vault --interval 9999
```

Expected log: `"Starting LinkedInWatcher"` — NOT `"LinkedIn session expired"`.
Press `Ctrl+C` after confirming.

- [ ] `python -m playwright install chromium` completed
- [ ] LinkedIn session saved to `secrets\linkedin_session`
- [ ] LinkedIn watcher starts without "session expired" warning

---

## 4. Register Email MCP server with Claude Code

### 4a. Find or create settings.json

```cmd
notepad %USERPROFILE%\.claude\settings.json
```

If the file is empty or new, start with `{}`.

### 4b. Add the `mcpServers` block

Merge this into your existing `settings.json` (keep any other keys you already have):

```json
{
  "mcpServers": {
    "email": {
      "command": "node",
      "args": ["D:\\aa-3\\hi\\ai-employee-bronze\\mcp-servers\\email-mcp\\index.js"],
      "env": {
        "GMAIL_TOKEN_PATH": "D:\\aa-3\\hi\\ai-employee-bronze\\secrets\\gmail_token.json",
        "DRY_RUN": "true"
      }
    }
  }
}
```

**Use absolute paths with double backslashes** on Windows.

### 4c. Restart Claude Code and verify

```cmd
claude
/mcp
```

Expected output includes: `email` with status `connected`.

- [ ] `settings.json` updated with `mcpServers` block
- [ ] Claude Code restarted
- [ ] `/mcp` shows `email` connected

---

## 5. Schedule with Windows Task Scheduler

### 5a. Edit the XML with your actual project path

```cmd
notepad D:\aa-3\hi\ai-employee-bronze\scheduler\schedule_windows.xml
```

Find this line and replace the path:
```xml
<WorkingDirectory>C:\Users\YourName\ai-employee-bronze</WorkingDirectory>
```
Replace with:
```xml
<WorkingDirectory>D:\aa-3\hi\ai-employee-bronze</WorkingDirectory>
```

Also confirm the Python path. If `python` is not on your PATH, replace:
```xml
<Command>python</Command>
```
with the full path (find it with `where python` in cmd):
```xml
<Command>C:\Users\YourName\AppData\Local\Programs\Python\Python313\python.exe</Command>
```

### 5b. Import the task (run as Administrator)

Open **Command Prompt as Administrator**:

```cmd
schtasks /create /xml "D:\aa-3\hi\ai-employee-bronze\scheduler\schedule_windows.xml" /tn "AIEmployee" /f
```

### 5c. Verify

```cmd
schtasks /query /tn "AIEmployee" /fo LIST /v
```

Look for: `Status: Ready`

### 5d. Test it manually

```cmd
schtasks /run /tn "AIEmployee"
```

Check the log file (replace date):
```cmd
type D:\aa-3\hi\ai-employee-bronze\vault\Logs\2026-02-21.json
```

Look for `"actor": "orchestrator"` and `"action_type": "orchestrator_started"`.

- [ ] XML `WorkingDirectory` updated to `D:\aa-3\hi\ai-employee-bronze`
- [ ] Task imported with `schtasks /create`
- [ ] `schtasks /query` shows `Status: Ready`
- [ ] Test run produces log entry with `orchestrator_started`

---

## 6. Flip DRY_RUN to false when ready for live actions

Once you have confirmed everything works end-to-end (watcher creates action file →
triage creates approval → you move to Approved → execute-approved runs dry):

```cmd
notepad D:\aa-3\hi\ai-employee-bronze\.env
```

Change:
```env
DRY_RUN=false
```

Also update `settings.json` MCP entry:
```json
"DRY_RUN": "false"
```

Then restart Claude Code and the orchestrator.

- [ ] `DRY_RUN=false` in `.env`
- [ ] `DRY_RUN: "false"` in `settings.json` MCP config
- [ ] Claude Code and orchestrator restarted

---

## 7. End-to-end smoke test

Run through this sequence once with `DRY_RUN=true` before going live:

```cmd
cd D:\aa-3\hi\ai-employee-bronze
claude
```

Then inside Claude Code:

```
/process-inbox
/triage-needs-action
/post-linkedin
```

1. Confirm `/post-linkedin` creates a file in `vault\Pending_Approval\`
2. Open Obsidian, move that file to `vault\Approved\`
3. Back in Claude Code:
   ```
   /execute-approved
   ```
4. Confirm the log shows `[DRY_RUN] Would send...` or `[DRY_RUN] Would post...`
5. Confirm file moved to `vault\Done\`

- [ ] `/post-linkedin` creates Pending_Approval file
- [ ] `/execute-approved` runs and logs DRY_RUN intent
- [ ] File appears in `vault\Done\`

---

## Secrets Folder Summary

After setup, `secrets\` should contain:

```
secrets\
├── gmail_credentials.json   ← Downloaded from Google Cloud Console
├── gmail_token.json          ← Auto-generated by gmail_watcher.py OAuth flow
├── gmail_processed_ids.txt   ← Auto-created by gmail_watcher.py
├── linkedin_session          ← Folder, auto-created by playwright open
└── linkedin_seen.txt         ← Auto-created by linkedin_watcher.py
```

**None of these files should ever be committed to git.**
They are already covered by `.gitignore`.

---

## Quick Reference — Key Commands

| Action | Command |
|--------|---------|
| Start all watchers | `python scheduler/orchestrator.py --vault ./vault` |
| Gmail only (dry run) | `python watchers/gmail_watcher.py --vault ./vault --dry-run` |
| LinkedIn only (dry run) | `python watchers/linkedin_watcher.py --vault ./vault --dry-run` |
| Verify MCP syntax | `node --check mcp-servers/email-mcp/index.js` |
| Check Task Scheduler | `schtasks /query /tn "AIEmployee" /fo LIST /v` |
| Stop scheduled task | `schtasks /end /tn "AIEmployee"` |
| Delete scheduled task | `schtasks /delete /tn "AIEmployee" /f` |
