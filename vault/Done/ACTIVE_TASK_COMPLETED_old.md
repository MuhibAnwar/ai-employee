---
task: Process all files in Needs_Action and move to Done
max_iterations: 5
current_iteration: 1
started: 2026-02-21T12:10:00Z
status: active
---

# Active Ralph Wiggum Task

## Task
Process all files in Needs_Action and move to Done

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
