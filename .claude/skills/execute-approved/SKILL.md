---
name: execute-approved
description: |
  Process all files in vault/Approved/. For each approved action, determine the
  action type from its YAML frontmatter, route it to the correct executor (Email MCP
  or linkedin-api), log the result, and move the file to vault/Done/. This is the
  "hands" of the AI Employee — it only acts on what the human has explicitly approved.
  No Playwright or browser automation is used.
---

# Execute Approved Actions

Process every file in `vault/Approved/` and carry out the approved actions.

## When to Use

- After reviewing and moving files from `vault/Pending_Approval/` to `vault/Approved/`
- Part of the daily workflow: approve → execute → done
- Never run speculatively — only when there are files in `vault/Approved/`

## Pre-Flight

1. Read `vault/Company_Handbook.md` — confirm you understand the rules
2. List all files in `vault/Approved/` (skip `.gitkeep`)

If `vault/Approved/` is empty, report "No approved actions to execute" and stop.

## Execution Decision Tree

For each file in `vault/Approved/`:

```
Read file frontmatter (action: field)
    │
    ├─ action: send_email
    │       └─ Call Email MCP tool: send_email(to, subject, body, cc?)
    │          → On success: move file to vault/Done/, log success
    │          → On error: log error, move file to vault/Done/ with error note
    │
    ├─ action: draft_email
    │       └─ Call Email MCP tool: draft_email(to, subject, body)
    │          → On success: report draft_id, move file to vault/Done/
    │          → On error: log error, move file to vault/Done/ with error note
    │
    ├─ action: post_linkedin
    │       └─ Run: python scripts/post_to_linkedin.py --file <approved_file>
    │          Exit 0 → post published → move file to vault/Done/, log success
    │          Exit 2 → API limitation → show post content for manual paste,
    │                   move file to vault/Done/ with error note
    │          Exit 1 → config error → log error, move file to vault/Done/
    │
    ├─ action: post_facebook
    │       └─ Facebook posting via API not yet implemented.
    │          Log "not implemented", show post content, move to vault/Done/.
    │
    ├─ action: post_instagram
    │       └─ Instagram posting via API not yet implemented (requires image).
    │          Log "not implemented", show post content, move to vault/Done/.
    │
    ├─ action: post_twitter
    │       └─ Twitter posting via API not yet implemented (needs credentials).
    │          Log "not implemented", show post content, move to vault/Done/.
    │
    └─ action: (unknown)
            └─ Log warning, move file to vault/Done/ with note "unrecognised action type"
```

## Steps

### For each file in vault/Approved/:

#### 1. Parse the approval file

Read the file. Extract from YAML frontmatter:
- `action:` — the action type (send_email | draft_email | post_linkedin)
- `description:` — human-readable summary for logging

Extract the action payload from the file body (email details, post text, etc.).

---

#### 2a. Execute: send_email

Parse from the file body:
```
To: <email>
Subject: <subject>
CC: <email> (optional)
Body:
<multi-line body text>
```

Call the Email MCP tool:
```
send_email(to=..., subject=..., body=..., cc=...)
```

If `DRY_RUN=true` is set in the environment, the MCP tool will log intent without sending.

---

#### 2b. Execute: draft_email

Parse the same fields as send_email.

Call the Email MCP tool:
```
draft_email(to=..., subject=..., body=...)
```

Report the returned `draft_id` to the user.

---

#### 2c. Execute: post_linkedin

Run the posting script (no browser, no Playwright):

```bash
python scripts/post_to_linkedin.py --file vault/Approved/<filename>
```

The script reads the `## Post Content` or `## Content` section from the approved file and
attempts to publish via the linkedin-api library.

**Exit codes and what to do:**

| Exit code | Meaning | Action |
|-----------|---------|--------|
| 0 | Published successfully | Log success, move file to vault/Done/ |
| 2 | API limitation (LinkedIn requires OAuth for posting) | Show post content for manual copy-paste, move to Done/ with error note |
| 1 | Config error (missing credentials) | Log error, move to Done/ with note |

**On exit code 2 (most common):**
- The script prints the full post content between `====` lines
- Tell the user: "LinkedIn's API restricts posting to OAuth 2.0 (w_member_social scope). Please copy the post content above and paste it at https://www.linkedin.com/post/new/"
- Move the file to vault/Done/ and log the limitation

**Credentials required in .env:**
```
LINKEDIN_USERNAME=your@email.com
LINKEDIN_PASSWORD=yourpassword
```

---

#### 2d. Execute: post_facebook

Facebook posting via API is not yet implemented (unofficial APIs are fragile).

Steps:
1. Extract the post content from the `## Post Content` or `## Content` section
2. Display it to the user with instructions to post manually at https://www.facebook.com/
3. Move the file to vault/Done/ with a note: "manual posting required"
4. Log the outcome

---

#### 2e. Execute: post_instagram

Instagram posting via API requires an image file (Instagram does not allow text-only posts).

Steps:
1. Extract the caption from the `## Post Content` or `## Content` section
2. Check if an `Image Path:` field is present in the file body
3. If no image: display caption, note the limitation, move to Done/
4. If image provided: note that CLI posting via instagrapi is possible but not yet wired up
5. Log the outcome

---

#### 2f. Execute: post_twitter

Twitter/X posting via API requires API credentials (`TWITTER_API_KEY` etc. in .env).
The TwitterWatcher is already wired for credentials but the posting path is not yet implemented.

Steps:
1. Extract the tweet text from the `## Post Content` or `## Content` section
2. Display it to the user with instructions to post manually at https://x.com/
3. Move the file to vault/Done/ with a note: "manual posting required — add Twitter API credentials to enable automated posting"
4. Log the outcome

---

#### 3. Log the result

For every execution attempt (success or failure):

```json
{
  "timestamp": "<ISO>",
  "action_type": "approved_action_executed",
  "actor": "claude_code",
  "source_file": "vault/Approved/<filename>",
  "result": "success | error",
  "notes": "<action type> | <brief outcome>"
}
```

---

#### 4. Move to Done

On success: move file from `vault/Approved/` to `vault/Done/`

On persistent error (after one retry): move file to `vault/Done/` and append an error note to the file body.

**Never delete files** — even failed executions are archived in `vault/Done/`.

---

### After processing all files

Run `/update-dashboard` to refresh the dashboard.

## Output Format

```
Execute approved actions complete. Processed 2 items:

1. [send_email]    APPROVAL_20260221T120000_follow_up_client.md
                   → Sent to client@example.com ✓ | Moved to /Done

2. [post_linkedin]  APPROVAL_20260221T120500_linkedin_post.md
                    → Posted to LinkedIn ✓ | Screenshot saved | Moved to /Done

3. [post_facebook]  APPROVAL_20260221T120600_facebook_post.md
                    → Posted to Facebook ✓ | Screenshot saved | Moved to /Done

4. [post_twitter]   APPROVAL_20260221T120700_twitter_post.md
                    → Posted to X (Twitter) ✓ | Screenshot saved | Moved to /Done

Dashboard updated.
```

## Notes

- **Always** check `action:` field in YAML frontmatter before routing
- **Never** guess the action — if the field is missing or unrecognised, archive and warn
- Email MCP must be registered in Claude Code settings before `send_email` or `draft_email` work
- For LinkedIn posts: uses `scripts/post_to_linkedin.py` (no browser). Requires `LINKEDIN_USERNAME`
  and `LINKEDIN_PASSWORD` in `.env`. LinkedIn's voyager API may reject POST operations (401) —
  the script then prints post content for manual copy-paste and exits with code 2.
- `DRY_RUN=true` in `.env` makes the Email MCP log intent only — no real sends
- No Playwright or browser automation is used anywhere in this skill
- After execution, the vault/Done/ folder is the audit trail — never modify Done files
