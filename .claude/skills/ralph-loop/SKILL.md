# Ralph Wiggum Loop

Run a task autonomously — Claude iterates until complete or max iterations reached.
Powered by `.claude/hooks/stop_hook.py` which intercepts each stop event.

## When to Use

- Multi-step tasks that need to run to completion without user hand-holding
- Processing batches of files in vault/Needs_Action/
- Any task where you want Claude to self-correct and keep going if it stops early

## Usage

```
/ralph-loop "task description" --max-iterations 10
```

## Pre-Flight

Before starting the loop:

1. Check that `.claude/hooks/stop_hook.py` exists — if not, alert the user
2. Check that `.claude/settings.json` has the Stop hook registered
3. Create `vault/Plans/ACTIVE_TASK.md` with the task state (see template below)

## Steps

### Step 1: Create ACTIVE_TASK.md

Write this file to `vault/Plans/ACTIVE_TASK.md`:

```markdown
---
task: <task description from /ralph-loop argument>
max_iterations: <--max-iterations value, default 10>
current_iteration: 0
started: <ISO timestamp>
status: active
---

# Active Ralph Wiggum Task

## Task
<task description>

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
```

### Step 2: Execute the task

Start working on the task description immediately. Follow the normal AI Employee
workflow:

1. Read `vault/Needs_Action/` for items to process
2. Apply `/triage-needs-action` logic to each
3. Create plans, move items to Done
4. Update Dashboard

### Step 3: Signal completion

When finished, output this exact string anywhere in your response:

```
<promise>TASK_COMPLETE</promise>
```

OR ensure all `PLAN_*.md` files in `vault/Plans/` are moved to `vault/Done/`.

### Step 4: The stop hook takes over

You do NOT need to manage the loop manually. The stop hook:

- Fires every time Claude tries to stop
- Checks completion conditions (promise, all plans done, max iterations)
- If incomplete: prints re-injection prompt → Claude sees it and keeps working
- If complete: allows stop, archives ACTIVE_TASK.md to Done/
- Logs every iteration to `vault/Logs/YYYY-MM-DD.json`

## Output Format

When starting a loop, report:

```
Ralph Wiggum loop started.

Task: "Process all files in Needs_Action and move to Done"
Max iterations: 5
State file: vault/Plans/ACTIVE_TASK.md

Beginning task now...
[proceed with the task]
```

## Completion Strategies

| Strategy | When to Use |
|----------|------------|
| `<promise>TASK_COMPLETE</promise>` | Simple tasks — Claude knows it's done |
| Move PLAN_*.md to Done/ | Multi-step plans — completion is structural |
| Max iterations guard | Safety net — always set a reasonable limit |

## Cancelling a Loop

To cancel mid-run:
1. Move `vault/Plans/ACTIVE_TASK.md` to `vault/Done/`
2. The stop hook will see no ACTIVE_TASK.md and allow stop on next iteration

## Notes

- The stop hook only activates when a Ralph Wiggum task is active (ACTIVE_TASK.md exists)
- Normal Claude sessions without ACTIVE_TASK.md are unaffected
- Logs are written to `vault/Logs/YYYY-MM-DD.json` with `action_type: ralph_wiggum_iteration`
- Max iterations default: 10 (always override for long tasks)
