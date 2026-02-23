---
name: process-inbox
description: |
  Scan vault/Inbox/ for new files and convert them into structured action items
  in vault/Needs_Action/. Creates one .md action file per inbox item with
  metadata, priority classification, and suggested next actions. Logs all
  activity to vault/Logs/. Run this skill whenever new files appear in Inbox.
---

# Process Inbox

Scan `vault/Inbox/` for new files and create structured action items in `vault/Needs_Action/`.

## When to Use

- After dropping new files, notes, or documents into `vault/Inbox/`
- When the filesystem watcher is not running and you want to manually process the inbox
- As the first step in any new task workflow

## Steps

1. **List inbox contents**
   - Read all files in `vault/Inbox/` (skip `.gitkeep` and hidden files)
   - If inbox is empty, report "Inbox is empty" and stop

2. **For each file in Inbox:**
   - Read the file content (or note its metadata if it's a non-text file)
   - Classify priority using `vault/Company_Handbook.md` rules:
     - `URGENT` → keywords: urgent, asap, deadline, overdue, critical
     - `HIGH` → keywords: invoice, payment, contract, meeting, proposal, client
     - `NORMAL` → everything else
   - Create a structured action file in `vault/Needs_Action/`:
     ```
     FILE_YYYYMMDDTHHMMSS_<original-name>.md
     ```

3. **Action file format:**
   ```markdown
   ---
   type: file_drop
   source: vault/Inbox/<filename>
   received: <ISO timestamp>
   priority: <urgent|high|normal>
   status: pending
   watcher: manual
   ---

   # Action Required: <filename>

   ## File Details
   | Field | Value |
   |-------|-------|
   | Name | `<filename>` |
   | Priority | **<PRIORITY>** |
   | Received | <timestamp> |

   ## Content Summary
   <1-3 sentence summary of the file content>

   ## Suggested Actions
   - [ ] Review content
   - [ ] Determine if external action is needed
   - [ ] If approval needed, create file in vault/Pending_Approval/
   - [ ] Move to vault/Done/ when complete
   ```

4. **Log the action** to `vault/Logs/YYYY-MM-DD.json`:
   ```json
   {
     "timestamp": "<ISO>",
     "action_type": "inbox_processed",
     "actor": "claude_code",
     "source_file": "vault/Inbox/<filename>",
     "result": "success",
     "notes": "Action file created: <action_filename>"
   }
   ```

5. **Report summary** to the user:
   - Number of files processed
   - Names of action files created
   - Any priority flags

6. **Run `/update-dashboard`** to refresh the Dashboard

## Notes

- Do NOT delete or move inbox files — leave them in place until `/triage-needs-action` completes them
- If a file already has a corresponding action file in `Needs_Action`, skip it (check by source filename in frontmatter)
- Always read `vault/Company_Handbook.md` before processing

## Example Output

```
Processed 2 inbox items:

1. ✅ [HIGH] FILE_20260219T103000_invoice_client_a.md
   → Created: vault/Needs_Action/FILE_20260219T103000_invoice_client_a.md

2. ✅ [NORMAL] FILE_20260219T103001_notes.md
   → Created: vault/Needs_Action/FILE_20260219T103001_notes.md

Dashboard updated.
```
