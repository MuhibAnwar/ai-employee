---
name: ceo-briefing
description: |
  Reads the latest Weekly_Audit from vault/Accounting/ and writes a structured
  CEO Briefing to vault/Briefings/<date>_Monday_CEO_Briefing.md. Designed to
  run every Monday at 8AM. Sections: Executive Summary, Wins, Bottlenecks,
  Proactive Suggestions.
---

# CEO Monday Morning Briefing

Generate a concise, executive-level briefing for the start of the work week.

## When to Use

- Every Monday at 8AM (triggered by Windows Task Scheduler)
- After `/weekly-audit` has been run (Sunday night or earlier Monday)
- On demand when a business summary is needed

## Pre-Flight

1. Read `vault/Company_Handbook.md` — confirm rules
2. Find the most recent file in `vault/Accounting/` matching `Weekly_Audit_*.md`
3. If no audit exists, run `/weekly-audit` first, then proceed

## Steps

### Step 1 — Load data sources

Read the following files:
- Latest `vault/Accounting/Weekly_Audit_*.md` — primary data source (contains Odoo section)
- `vault/Business_Goals.md` — revenue targets and project status
- `vault/Dashboard.md` — current system state
- Any files in `vault/Pending_Approval/` — actions awaiting human sign-off

If the Weekly_Audit contains an Odoo Financial Summary section, extract:
- `odoo_revenue_mtd` — total posted invoice revenue this month
- `odoo_outstanding_count` and `odoo_outstanding_total` — draft invoices not yet posted
- `odoo_top_client` — client name and their total billed amount

If the Weekly_Audit has no Odoo section (older audit), these fields will be "N/A".

### Step 2 — Synthesise the briefing

Using the data above, reason through each section:

**Executive Summary (3-5 sentences)**
- What happened this week in concrete terms (tasks completed, posts published, emails handled)
- Is the system running smoothly or are there issues?
- One sentence on business goal progress

**Wins (bulleted)**
- List concrete achievements from vault/Done/ this week
- Include: tasks processed, social posts published, plans completed, alerts resolved
- Focus on outcomes, not process

**Bottlenecks (bulleted)**
- Any watchers with circuit breaker OPEN (system down — needs human action)
- Any Pending_Approval items older than 48 hours (stalled pipeline)
- Business metrics that are below 50% of target
- Recurring errors (same error type 3+ times in logs)
- If none: state "No bottlenecks identified this week."

**Proactive Suggestions (bulleted)**
- Based on goals and metrics, suggest 2-4 concrete next actions
- Examples:
  - "Review and approve N items in Pending_Approval"
  - "Restart FileSystemWatcher — circuit breaker tripped, needs diagnosis"
  - "Revenue at 0% of monthly target — consider publishing a lead-generation post this week"
  - "Update Business_Goals.md with current MTD revenue figures"
  - "Consider scheduling a weekly LinkedIn post to support [goal]"

### Step 3 — Write vault/Briefings/<date>_Monday_CEO_Briefing.md

`<date>` = today's date in YYYY-MM-DD format.

Use this template:

```markdown
---
briefing_date: <YYYY-MM-DD>
type: Monday_CEO_Briefing
audit_source: vault/Accounting/Weekly_Audit_<audit_date>.md
generated_by: claude_code
---

# Monday CEO Briefing — <YYYY-MM-DD>

_Prepared by your AI Employee at 8:00 AM_

---

## Executive Summary

<3-5 sentence summary of the week and current status>

---

## Wins This Week

- <concrete win 1>
- <concrete win 2>
- <concrete win 3>
_(... continue as appropriate)_

---

## Bottlenecks

- <bottleneck 1 with specific file/system reference>
- <bottleneck 2>
_(or: No bottlenecks identified this week.)_

---

## Proactive Suggestions

1. **<Action title>** — <one-sentence explanation of why and what to do>
2. **<Action title>** — <one-sentence explanation>
3. **<Action title>** — <one-sentence explanation>
4. **<Action title>** — <one-sentence explanation>

---

## Quick Stats

| Metric | This Week |
|--------|-----------|
| Tasks completed | N |
| Items pending | N |
| Watcher alerts | N |
| Revenue MTD (posted) | $X |
| Outstanding invoices | N invoices — $X |
| Active clients | N |
| Top client | Name — $X |

---

_Source: vault/Accounting/Weekly_Audit_<date>.md_
_Next briefing: <next Monday date>_
```

### Step 4 — Log the action

Append to `vault/Logs/<today>.json`:

```json
{
  "timestamp": "<ISO>",
  "action_type": "ceo_briefing_generated",
  "actor": "claude_code",
  "source_file": "vault/Briefings/<date>_Monday_CEO_Briefing.md",
  "audit_source": "vault/Accounting/Weekly_Audit_<audit_date>.md",
  "result": "success",
  "notes": "Monday CEO Briefing for <date>. N wins, N bottlenecks, N suggestions."
}
```

### Step 5 — Update Dashboard

Run `/update-dashboard` to reflect the new Briefing file.

## Output Format

```
CEO Monday Briefing generated.

Output: vault/Briefings/2026-02-23_Monday_CEO_Briefing.md
Source: vault/Accounting/Weekly_Audit_2026-02-22.md

Preview:

  Executive Summary: [first sentence of summary]

  Wins: N items
  Bottlenecks: N items
  Suggestions: N items

Dashboard updated.
```

## Scheduler Integration

This skill is triggered every Monday at 8AM by Windows Task Scheduler.
See: `scheduler/ceo_briefing_windows.xml`

The scheduled task runs:
```
claude --no-browser /ceo-briefing
```
from the project root directory.

## Notes

- Always source data from the most recent Weekly_Audit — do not generate from memory
- Keep the briefing concise — a CEO reads this in under 2 minutes
- Bottlenecks require specific file references so the human knows exactly what to act on
- Never create an alarm-tone briefing — factual and calm, with clear calls to action
- If the Weekly_Audit is from more than 3 days ago, note it may be stale
