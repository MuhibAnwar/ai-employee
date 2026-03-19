---
task: Check vault/Needs_Action/ for any remaining items, process them, then generate a daily status report in vault/Briefings/Daily_Status_2026-03-01.md showing: watcher health, emails processed today, pending approvals, and completed tasks
max_iterations: 3
current_iteration: 2
started: 2026-03-01T00:10:00Z
status: active
---

# Active Ralph Wiggum Task

## Task
Check vault/Needs_Action/ for any remaining items, process them, then generate a daily status report in vault/Briefings/Daily_Status_2026-03-01.md showing: watcher health, emails processed today, pending approvals, and completed tasks.

## Completion Criteria

The stop hook (`stop_hook.py`) will allow Claude to stop when ONE of these is true:
- All `PLAN_*.md` files in `vault/Plans/` have been moved to `vault/Done/`
- Claude outputs: `<promise>TASK_COMPLETE</promise>`
- `max_iterations` is reached (safety guard)

## Iteration Log

| Iteration | Timestamp | Status |
|-----------|-----------|--------|
| (updated by stop_hook.py) | | |

## Notes
- Do not delete this file while the loop is running
- The stop hook reads `current_iteration` and `max_iterations` from frontmatter
- Move this file to vault/Done/ manually if you want to cancel the loop
