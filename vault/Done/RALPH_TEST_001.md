---
type: test
subject: Ralph Wiggum Loop Test
priority: normal
status: pending
created: 2026-02-21T12:10:00Z
---

## Content

This is a test item to verify the Ralph Wiggum autonomous loop.

The loop should:
1. Detect this file in vault/Needs_Action/
2. Create a plan for it
3. Process it
4. Move it to vault/Done/
5. Signal TASK_COMPLETE

## Expected Outcome

- This file moves to vault/Done/
- A PLAN_*.md is created and then moved to vault/Done/
- vault/Logs/ shows ralph_wiggum_iteration entries
- Loop exits cleanly after task completion
