# Platinum Tier Demo Gate

**Minimum passing requirement for Platinum Tier.**

> "Email arrives while Local PC is offline → Cloud (Codespace) detects it → drafts reply → writes approval file → Local approves when it returns → Email sent via MCP → logged → Done."

---

## Architecture: Cloud vs Local Split

```
┌─────────────────────────────────────────────────────────────────┐
│  CODESPACE  (always-on cloud)                                   │
│                                                                 │
│  PM2 → orchestrator.py                                          │
│    ├── GmailWatcher       polls every 2 min                     │
│    ├── LinkedInWatcher    polls every 5 min                     │
│    ├── FacebookWatcher    polls every 5 min                     │
│    ├── InstagramWatcher   polls every 5 min                     │
│    ├── TwitterWatcher     polls every 5 min                     │
│    └── FileSystemWatcher  watches vault/Inbox/ in real time     │
│                                                                 │
│  Claude Code (scheduled / triggered)                            │
│    ├── /process-inbox         → vault/Needs_Action/             │
│    ├── /triage-needs-action   → vault/Plans/ + Pending_Approval/│
│    ├── /weekly-audit          → vault/Accounting/               │
│    └── /ceo-briefing          → vault/Briefings/                │
│                                                                 │
│  Cloud WRITES, never SENDS. All external actions need approval. │
└───────────────────────────────────┬─────────────────────────────┘
                                    │  vault sync via Git
                                    │  (secrets excluded)
┌───────────────────────────────────▼─────────────────────────────┐
│  LOCAL PC  (human-in-the-loop, comes online when available)     │
│                                                                 │
│  Obsidian vault (synced from Codespace via git pull)            │
│    └── vault/Pending_Approval/   ← human reviews here          │
│        → moves file to vault/Approved/                          │
│                                                                 │
│  Claude Code (on demand)                                        │
│    └── /execute-approved         → Email MCP sends email        │
│                                  → Playwright posts to LinkedIn  │
│                                                                 │
│  Local ONLY: WhatsApp session, banking tokens, final send       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Work-Zone Rules

| Rule | Detail |
|------|--------|
| **Cloud owns drafts** | Email triage, reply drafts, social post drafts |
| **Local owns sends** | All actual sends/posts require human approval + local execution |
| **Claim-by-move** | First agent to move a file from `Needs_Action/` to `In_Progress/<agent>/` owns it — other agents skip it |
| **Single writer** | Only Local writes to `Dashboard.md`. Cloud writes to `vault/Updates/` and Local merges on sync. |
| **Secrets never sync** | `.env`, `secrets/`, WhatsApp sessions, banking tokens — gitignored, never pushed |

---

## Demo Gate: Step-by-Step

### Preconditions
- Codespace running with `./deployment/codespace_setup.sh` complete
- PM2 orchestrator online: `./deployment/codespace_setup.sh status`
- Gmail credentials in `secrets/gmail_token.json` (Codespace copy)
- Email MCP server configured and running on Local PC
- Vault synced: Codespace and Local share the same GitHub repo

---

### Step 1 — Local PC goes offline
Local PC is shut down or disconnected. Codespace continues running.

```
Codespace: GmailWatcher polling every 120s  ← still active
Local PC:  offline
```

---

### Step 2 — Email arrives
An email lands in the monitored Gmail inbox (e.g. subject: "Project Proposal — Q2").

**GmailWatcher detects it** (within 2 minutes) and writes:

```
vault/Inbox/EMAIL_<timestamp>_Project_Proposal_Q2.md
```

Example file content:
```markdown
---
type: email
from: client@example.com
subject: Project Proposal — Q2
received: 2026-03-28T14:05:00Z
priority: high
source: gmail
message_id: <abc123@gmail.com>
---

Hi, I'd like to discuss a new project for Q2. Can we schedule a call?

— Client Name
```

---

### Step 3 — Codespace Claude triages the email
The orchestrator detects the new Inbox file and triggers `/process-inbox`, then `/triage-needs-action`.

Claude reads `Company_Handbook.md`, determines this is a business opportunity, and creates:

**`vault/Plans/PLAN_<timestamp>_Project_Proposal_Q2.md`**
```markdown
# Plan: Respond to Q2 Project Proposal
Source: EMAIL_..._Project_Proposal_Q2.md
Priority: HIGH — potential new client revenue

Steps:
- [x] Read email and classify
- [x] Draft polite reply expressing interest, propose call times
- [ ] Await human approval
- [ ] Execute send via Email MCP
```

**`vault/Pending_Approval/DRAFT_EMAIL_<timestamp>_Project_Proposal_Q2.md`**
```markdown
---
action_type: send_email
to: client@example.com
subject: Re: Project Proposal — Q2
priority: high
drafted_by: claude_code (codespace)
drafted_at: 2026-03-28T14:07:00Z
requires_approval: true
---

Hi,

Thank you for reaching out about a Q2 project. I'd be happy to discuss further.

I'm available for a call on:
- Monday March 30, 2–4 PM
- Tuesday March 31, 10 AM–12 PM

Please let me know which works best.

Best regards
```

**Log entry appended to `vault/Logs/2026-03-28.json`:**
```json
{
  "timestamp": "2026-03-28T14:07:00Z",
  "action_type": "email_draft_created",
  "actor": "claude_code",
  "source_file": "vault/Inbox/EMAIL_..._Project_Proposal_Q2.md",
  "result": "success",
  "notes": "Draft reply created in Pending_Approval — awaiting human sign-off"
}
```

---

### Step 4 — Vault syncs to GitHub
Codespace pushes the new files to the shared GitHub repo:
```bash
./deployment/sync_vault.sh push
```

The vault now contains the draft approval file — visible in GitHub and ready for Local to pull.

---

### Step 5 — Local PC comes back online
User opens their local machine. They pull the latest vault:
```bash
./deployment/sync_vault.sh pull
```

Obsidian refreshes. The user sees in `vault/Pending_Approval/`:
```
DRAFT_EMAIL_20260328T140700_Project_Proposal_Q2.md  [HIGH]
```

---

### Step 6 — Human approves
The user reviews the draft. It looks good. They move the file:
```
vault/Pending_Approval/DRAFT_EMAIL_...md
           ↓  (drag in Obsidian or mv in terminal)
vault/Approved/DRAFT_EMAIL_...md
```

---

### Step 7 — Local executes
Local Claude Code runs:
```
/execute-approved
```

The skill reads `vault/Approved/DRAFT_EMAIL_...md`, detects `action_type: send_email`, and calls the **Email MCP server**:
```
send_email(to, subject, body)
```

The email is sent. The file is moved to `vault/Done/`.

Log entry appended:
```json
{
  "timestamp": "2026-03-28T16:30:00Z",
  "action_type": "email_sent",
  "actor": "claude_code",
  "source_file": "vault/Approved/DRAFT_EMAIL_..._Project_Proposal_Q2.md",
  "result": "success",
  "notes": "Reply sent via Email MCP. Moved to Done."
}
```

---

### Step 8 — Dashboard updated
```
/update-dashboard
```

Dashboard reflects: 0 Pending Approvals, +1 Done, latest activity logged.

---

## Demo Gate Checklist

To pass Platinum, demonstrate this sequence end-to-end:

- [ ] Codespace PM2 orchestrator running (`./deployment/codespace_setup.sh status` shows `online`)
- [ ] GmailWatcher active (check `vault/Logs/pm2-out.log`)
- [ ] Email arrives → `vault/Inbox/` file created within 2 minutes
- [ ] `/process-inbox` runs → file moves to `vault/Needs_Action/`
- [ ] `/triage-needs-action` runs → Plan created, draft in `vault/Pending_Approval/`
- [ ] Log entry written to `vault/Logs/<date>.json`
- [ ] Vault pushed to GitHub by Codespace
- [ ] Local pulls vault, draft visible in Obsidian
- [ ] Human moves draft to `vault/Approved/`
- [ ] `/execute-approved` sends email via Email MCP
- [ ] File in `vault/Done/`
- [ ] Dashboard updated

---

## Running the Demo

```bash
# 1. Start Codespace cloud agent (run once on Codespace)
./deployment/codespace_setup.sh

# 2. Verify orchestrator is running
./deployment/codespace_setup.sh status

# 3. Watch live logs
./deployment/codespace_setup.sh logs

# 4. Trigger test: drop a fake email into Inbox manually
cat > vault/Inbox/TEST_EMAIL_demo.md << 'EOF'
---
type: email
from: demo@example.com
subject: Demo Email — Platinum Gate Test
received: 2026-03-28T12:00:00Z
priority: high
source: gmail
---
This is a test email to validate the Platinum demo gate.
Please reply to confirm receipt.
EOF

# 5. Run the reasoning loop
/process-inbox
/triage-needs-action

# 6. Check what was drafted
ls vault/Pending_Approval/

# 7. Approve and execute
mv vault/Pending_Approval/DRAFT_EMAIL_*.md vault/Approved/
/execute-approved

# 8. Confirm it reached Done
ls vault/Done/
```

---

## What Makes This Platinum

| Gold | Platinum |
|------|----------|
| Runs on local machine | Runs 24/7 on cloud (Codespace) |
| Watchers only active when laptop is on | Watchers active even when laptop is off |
| Human triggers processing manually | Cloud triages automatically, queues for approval |
| Single execution environment | Split: Cloud drafts, Local executes |
| No vault sync | Vault synced via Git between cloud and local |
| Odoo local only | Odoo accessible from cloud via MCP (always-on) |

*Platinum Tier — AI Employee v0.4*
