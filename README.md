# Personal AI Employee — Platinum Tier ✅

> *Your life and business on autopilot. Local-first, agent-driven, human-in-the-loop.*

This is the **Platinum Tier** implementation of the [Personal AI Employee Hackathon](https://agentfactory.panaversity.org). It is a fully autonomous, cloud-deployed AI employee running 24/7 on GitHub Codespaces — monitoring Gmail, WhatsApp, LinkedIn, Facebook, Instagram, and Twitter, managing accounting via Odoo ERP, generating weekly CEO briefings, and routing all sensitive actions through a human-in-the-loop approval workflow. Built entirely on **Claude Code** as the reasoning engine and **Obsidian** as the local knowledge base and dashboard.

---

## What's Included (Platinum Tier)

| Requirement | Status | Location |
|-------------|--------|----------|
| Obsidian vault with `Dashboard.md` | ✅ | `vault/Dashboard.md` |
| `Company_Handbook.md` | ✅ | `vault/Company_Handbook.md` |
| Basic folder structure (`/Inbox`, `/Needs_Action`, `/Done`) | ✅ | `vault/` |
| File system watcher | ✅ | `watchers/filesystem_watcher.py` |
| Gmail watcher (Silver) | ✅ | `watchers/gmail_watcher.py` |
| LinkedIn watcher (Silver) | ✅ | `watchers/linkedin_watcher.py` |
| Email MCP server (Silver) | ✅ | `mcp-servers/email-mcp/` |
| LinkedIn auto-posting skill (Silver) | ✅ | `.claude/skills/post-linkedin/` |
| Execute-approved skill (Silver) | ✅ | `.claude/skills/execute-approved/` |
| Human-in-the-loop approval workflow | ✅ | `vault/Pending_Approval/` → `vault/Approved/` |
| Claude reasoning loop with Plan.md | ✅ | `.claude/skills/triage-needs-action/` |
| Windows Task Scheduler scheduling | ✅ | `scheduler/` |
| All AI functionality as Agent Skills | ✅ | `.claude/skills/` |

---

## Architecture

```
External World
    │
    ├── Gmail API ──────────────────────────────────────┐
    ├── LinkedIn Notifications (Playwright) ────────────┤
    └── vault/Inbox/ (file drop) ──────────────────────┤
                                                        ▼
                                            vault/Needs_Action/
                                                        │
                                    ▼ (/triage-needs-action skill)
                                    ├── vault/Plans/
                                    └── vault/Pending_Approval/
                                                        │
                                    ── Human Reviews ───┤
                                                        ▼
                                            vault/Approved/
                                                        │
                                    ▼ (/execute-approved skill)
                                    ├── Email MCP → Gmail send
                                    └── Playwright MCP → LinkedIn post
                                                        │
                                                        ▼
                                    vault/Done/ + vault/Logs/
                                                        │
                                    ▼ (/update-dashboard)
                                    vault/Dashboard.md
```

---

## Quick Start

### 1. Prerequisites

```bash
# Python 3.13+
python --version

# Install dependencies (includes Silver Tier: google-auth, playwright, schedule)
pip install -r requirements.txt

# Install Playwright browser (for LinkedIn watcher + execute-approved)
python -m playwright install chromium

# Node.js 18+ (for Email MCP server)
node --version

# Claude Code (must be installed)
claude --version
```

### 2. Setup

```bash
# Clone or open the project
cd ai-employee-bronze

# Copy environment template
cp .env.example .env
# Edit .env with your settings (VAULT_PATH, DRY_RUN, etc.)

# Open vault/ as an Obsidian vault
# File > Open Vault > Select the vault/ folder
```

### 3. Start All Watchers (Orchestrator)

```bash
# Start all watchers in one command (recommended)
python scheduler/orchestrator.py --vault ./vault

# Or start individual watchers
python watchers/filesystem_watcher.py --vault ./vault
python watchers/gmail_watcher.py --vault ./vault
python watchers/linkedin_watcher.py --vault ./vault
```

### 4. Set Up Email MCP Server

```bash
cd mcp-servers/email-mcp
npm install
```

See `mcp-servers/email-mcp/README.md` for OAuth2 setup and Claude Code registration.

### 5. Use Claude Code with Agent Skills

```bash
# Start Claude Code in the project directory
claude

# Process inbox manually
/process-inbox

# Triage items needing action
/triage-needs-action

# Draft a LinkedIn post for approval
/post-linkedin

# Execute approved actions (email/LinkedIn)
/execute-approved

# Refresh the dashboard
/update-dashboard
```

### 6. Schedule with Windows Task Scheduler (optional)

```cmd
# Import the scheduled task (edit scheduler\schedule_windows.xml first)
schtasks /create /xml "scheduler\schedule_windows.xml" /tn "AIEmployee" /f
```

See `scheduler/README.md` for full instructions.

---

## Agent Skills

Five skills are registered for Claude Code:

### `/process-inbox`
Scans `vault/Inbox/` for new files and creates structured action items in `vault/Needs_Action/`. Classifies items by priority (urgent/high/normal) based on `Company_Handbook.md` rules.

### `/triage-needs-action`
Claude reasons about items in `vault/Needs_Action/` and decides:
- Simple items → moved to `vault/Done/`
- Multi-step tasks → creates `Plan.md` in `vault/Plans/`
- Sensitive actions → creates approval request in `vault/Pending_Approval/`

### `/post-linkedin` *(Silver)*
Reads `vault/Business_Goals.md` and drafts a professional LinkedIn post. Creates a `vault/Pending_Approval/` file for human review. When approved and `/execute-approved` is run, posts via Playwright.

### `/execute-approved` *(Silver)*
Processes all files in `vault/Approved/`. Routes:
- `action: send_email` → Email MCP server (Gmail API)
- `action: draft_email` → Email MCP server (saves Gmail draft)
- `action: post_linkedin` → Playwright MCP (posts to LinkedIn)

Moves each file to `vault/Done/` after execution and logs the result.

### `/update-dashboard`
Refreshes `vault/Dashboard.md` with current folder counts, recent log entries, and pending approvals.

---

## Watcher Scripts

All watchers extend `BaseWatcher` and write action files to `vault/Needs_Action/`.

### `watchers/filesystem_watcher.py`

Monitors `vault/Inbox/` using the Python `watchdog` library.

```bash
python watchers/filesystem_watcher.py --vault ./vault
```

### `watchers/gmail_watcher.py` *(Silver)*

Polls Gmail every 120s for unread important emails. Requires OAuth2 credentials in `./secrets/gmail_credentials.json`.

```bash
python watchers/gmail_watcher.py --vault ./vault
python watchers/gmail_watcher.py --vault ./vault --dry-run  # no API calls
```

### `watchers/linkedin_watcher.py` *(Silver)*

Monitors LinkedIn notifications every 5 min using Playwright. Requires a saved browser session at `LINKEDIN_SESSION_PATH`.

```bash
python watchers/linkedin_watcher.py --vault ./vault
python watchers/linkedin_watcher.py --vault ./vault --dry-run  # no browser
```

### `scheduler/orchestrator.py` *(Silver)*

Runs all three watchers as subprocesses with a crash-restart watchdog.

```bash
python scheduler/orchestrator.py --vault ./vault
```

---

## Vault Structure

```
vault/
├── Dashboard.md          ← Live status (run /update-dashboard to refresh)
├── Company_Handbook.md   ← AI rules of engagement
├── Business_Goals.md     ← Q1 objectives and KPIs
├── Inbox/                ← Drop new files here
├── Needs_Action/         ← Action items (auto-created by watcher/skill)
├── Plans/                ← Multi-step plans created by Claude
├── Pending_Approval/     ← Sensitive actions awaiting your approval
├── Approved/             ← Approved actions (move here to proceed)
├── Rejected/             ← Rejected actions (archive)
├── Done/                 ← Completed items
└── Logs/                 ← JSON audit trail (one file per day)
```

---

## Human-in-the-Loop

All sensitive actions require your explicit approval:

1. Claude creates a file in `vault/Pending_Approval/`
2. You review the file in Obsidian
3. **Approve:** Move the file to `vault/Approved/`
4. **Reject:** Move the file to `vault/Rejected/`

---

## Security

- Never commit `.env` files (added to `.gitignore`)
- All credentials go in `secrets/` or environment variables only
- `DRY_RUN=true` by default — no real external actions during development
- Full audit trail in `vault/Logs/`

---

## Platinum Tier — Full Feature Set

Everything in Bronze + Silver + Gold, plus:

| Tier | Feature | Description |
|------|---------|-------------|
| Silver | Gmail watcher | Polls for unread important emails every 120s |
| Silver | LinkedIn watcher | Monitors notifications every 5 min via Playwright |
| Silver | Email MCP server | Node.js MCP exposing `send_email` / `draft_email` tools |
| Silver | `/post-linkedin` skill | Drafts LinkedIn posts from business goals |
| Silver | `/execute-approved` skill | Routes approved actions to Email MCP or Playwright |
| Silver | Orchestrator | Manages all watchers with auto-restart on crash |
| Gold | Facebook + Instagram + Twitter watchers | 3 additional social watchers |
| Gold | Odoo ERP integration | Odoo Community via Docker + MCP server (5 tools) |
| Gold | `/weekly-audit` skill | Weekly business + accounting audit |
| Gold | `/ceo-briefing` skill | Monday 8AM CEO briefing auto-generation |
| Gold | Circuit breaker | CLOSED → OPEN → HALF_OPEN recovery per watcher |
| Gold | Ralph Wiggum loop | Autonomous Stop-hook agent loop |
| **Platinum** | 24/7 cloud agent | GitHub Codespaces + PM2 process supervisor |
| **Platinum** | Vault sync | Git push/pull between cloud and local Obsidian |
| **Platinum** | WhatsApp watcher | Playwright-based WhatsApp Web monitor (local-only) |
| **Platinum** | Work-zone rules | Cloud handles triage; local PC handles approvals + sends |
| **Platinum** | Demo gate passed | End-to-end: email detected → triaged → approved → sent via Gmail API |

---

## Tier Progression

| Tier | Status | Key Additions |
|------|--------|---------------|
| Bronze | ✅ | Vault, 1 watcher, 3 skills |
| Silver | ✅ | Gmail + LinkedIn watchers, LinkedIn posting, MCP email server, scheduling |
| Gold | ✅ | 6 watchers, Odoo ERP, weekly CEO briefing, Ralph Wiggum loop |
| **Platinum** | ✅ **This repo** | 24/7 cloud agent (Codespaces + PM2), vault sync via Git, WhatsApp watcher, demo gate passed |

---

## Hackathon

- **Tier:** Platinum ✅
- **Hackathon:** [Personal AI Employee Hackathon 0](https://agentfactory.panaversity.org)
- **Verification:** `vault/Briefings/PLATINUM_COMPLETE.md` — 15/15 requirements met
- **Submit:** [https://forms.gle/JR9T1SJq5rmQyGkGA](https://forms.gle/JR9T1SJq5rmQyGkGA)
