---
name: execute-approved
description: |
  Process all files in vault/Approved/. For each approved action, determine the
  action type from its YAML frontmatter, route it to the correct executor (Email MCP
  or Playwright), log the result, and move the file to vault/Done/. This is the
  "hands" of the AI Employee — it only acts on what the human has explicitly approved.
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
    │       └─ Use Playwright to post to LinkedIn (steps below)
    │          → On success: screenshot confirmation, move file to vault/Done/
    │          → On error: log error, leave file in vault/Approved/ with error note
    │
    ├─ action: post_facebook
    │       └─ Use Playwright + facebook_storage.json session (steps below)
    │          → On success: screenshot confirmation, move file to vault/Done/
    │          → On error: log error, leave file in vault/Approved/ with error note
    │
    ├─ action: post_instagram
    │       └─ Use Playwright + instagram_storage.json session (steps below)
    │          → On success: screenshot confirmation, move file to vault/Done/
    │          → On error: log error, leave file in vault/Approved/ with error note
    │
    ├─ action: post_twitter
    │       └─ Use Playwright + twitter_storage.json session (steps below)
    │          → On success: screenshot confirmation, move file to vault/Done/
    │          → On error: log error, leave file in vault/Approved/ with error note
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

Use the Playwright MCP (`/browsing-with-playwright` skill pattern):

```bash
# 1. Navigate to LinkedIn
browser_navigate url="https://www.linkedin.com/"

# 2. Take snapshot to find the "Start a post" button
browser_snapshot

# 3. Click "Start a post"
browser_click element="Start a post" ref=<ref from snapshot>

# 4. Wait for post composer to open
browser_wait_for text="What do you want to talk about?"

# 5. Type the post content
browser_type element="Post text area" ref=<ref> text=<post content>

# 6. Click "Post" button
browser_click element="Post" ref=<ref>

# 7. Wait for confirmation
browser_wait_for text="Your post is now live"

# 8. Take a screenshot as evidence
browser_take_screenshot type="png"
```

If the LinkedIn session is expired (redirected to login):
- Log error: "LinkedIn session expired"
- Leave the file in vault/Approved/ (do not move to Done)
- Instruct user: "Re-authenticate LinkedIn session and re-run /execute-approved"

---

#### 2d. Execute: post_facebook

Session file: `secrets/facebook_storage.json` (env: `FACEBOOK_SESSION_PATH`)

Parse from the file body:
```
Post Content:
<multi-line post text>
```

Use Playwright with the saved Facebook session:
```bash
# 1. Launch browser with saved session
browser_navigate url="https://www.facebook.com/"

# 2. Verify session (not redirected to login)
browser_snapshot  → check URL does not contain "login"

# 3. Click "What's on your mind?" composer
browser_click element="What's on your mind?" ref=<ref>

# 4. Type post content
browser_type element="post composer" ref=<ref> text=<post content>

# 5. Click "Post" button
browser_click element="Post" ref=<ref>

# 6. Wait for confirmation
browser_wait_for text="Your post is now shared"  (or similar)

# 7. Screenshot as evidence
browser_take_screenshot type="png"
```

If session expired (redirected to login):
- Log error: "Facebook session expired"
- Leave file in vault/Approved/
- Instruct user: "Run: python setup/save_social_sessions.py --platform facebook"

---

#### 2e. Execute: post_instagram

Session file: `secrets/instagram_storage.json` (env: `INSTAGRAM_SESSION_PATH`)

Parse from the file body:
```
Post Content:
<caption text>
Image Path: <optional local path to image>
```

Note: Instagram web does not support posting without an image. If no image is provided,
create a Pending_Approval note explaining this limitation and ask the user to provide an image.

If an image path is provided:
```bash
# 1. Launch browser with saved session
browser_navigate url="https://www.instagram.com/"

# 2. Verify session
browser_snapshot  → check URL does not contain "accounts/login"

# 3. Click "Create" / "+" button
browser_click element="New post" ref=<ref>

# 4. Upload image (click "Select from computer")
browser_click element="Select from computer" ref=<ref>
# → Use file upload dialog to select image at <Image Path>

# 5. Click "Next" through the crop/filter steps
browser_click element="Next" ref=<ref>  # crop
browser_click element="Next" ref=<ref>  # filters

# 6. Type caption
browser_type element="Write a caption" ref=<ref> text=<caption>

# 7. Click "Share"
browser_click element="Share" ref=<ref>

# 8. Screenshot as evidence
browser_take_screenshot type="png"
```

If session expired:
- Log error: "Instagram session expired"
- Leave file in vault/Approved/
- Instruct user: "Run: python setup/save_social_sessions.py --platform instagram"

---

#### 2f. Execute: post_twitter

Session file: `secrets/twitter_storage.json` (env: `TWITTER_SESSION_PATH`)

Parse from the file body:
```
Post Content:
<tweet text — max 280 characters>
```

Use Playwright with the saved Twitter/X session:
```bash
# 1. Launch browser with saved session
browser_navigate url="https://x.com/home"

# 2. Verify session (not redirected to login)
browser_snapshot  → check URL does not contain "i/flow/login"

# 3. Click "What is happening?!" composer
browser_click element="Post" (the compose button) ref=<ref>

# 4. Type tweet content
browser_type element="Post text" ref=<ref> text=<tweet text>

# 5. Click "Post" button to submit
browser_click element="Post" (submit button) ref=<ref>

# 6. Wait for success indicator
browser_wait_for text="Your post was sent"  (or similar)

# 7. Screenshot as evidence
browser_take_screenshot type="png"
```

If session expired (redirected to login):
- Log error: "Twitter/X session expired"
- Leave file in vault/Approved/
- Instruct user: "Run: python setup/save_social_sessions.py --platform twitter"

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
- For LinkedIn posts: the Playwright browser context must have an active LinkedIn session
  (session stored at `LINKEDIN_SESSION_PATH` from `.env`)
- `DRY_RUN=true` in `.env` makes the Email MCP log intent only — no real sends
- After execution, the vault/Done/ folder is the audit trail — never modify Done files
