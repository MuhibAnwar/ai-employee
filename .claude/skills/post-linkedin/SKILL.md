---
name: post-linkedin
description: |
  Draft a professional LinkedIn post based on current Business_Goals.md objectives.
  Creates a Pending_Approval file for human review. When the approval file is moved
  to vault/Approved/ and /execute-approved is run, posts to LinkedIn via Playwright.
---

# Post to LinkedIn

Draft a LinkedIn post that promotes current business offerings, then queue it for
human approval before publishing.

## When to Use

- Proactively promote services or achievements from `vault/Business_Goals.md`
- After a new project, milestone, or insight that's worth sharing publicly
- When a LinkedIn notification suggests an opportunity for visibility
- Run weekly as part of the sales/marketing loop

## Pre-Flight

1. Read `vault/Company_Handbook.md` — ensure the post tone matches company voice
2. Read `vault/Business_Goals.md` — identify current services, KPIs, and focus areas
3. Check `vault/Pending_Approval/` — don't create a second LinkedIn post if one is already pending

If a pending LinkedIn post already exists, report it and stop.

## Drafting the Post

Write a LinkedIn post following these guidelines:

### Content Rules
- **Length:** 150–300 words (3 short paragraphs max)
- **Tone:** Professional, confident, human — not salesy or robotic
- **Structure:**
  1. Opening hook — one punchy sentence that earns the scroll
  2. Value statement — what you offer and why it matters right now
  3. Call to action — one clear next step (comment, DM, link)
- **Hashtags:** 3–5 relevant hashtags at the end
- **No emojis unless** the Company_Handbook.md explicitly allows them

### What to Include
- Reference a specific service, goal, or achievement from `Business_Goals.md`
- Make it timely — reference Q1 goals, recent wins, or current market context
- Keep the call to action soft (invite conversation, not a hard sell)

## Steps

### 1. Gather context
```
Read vault/Business_Goals.md
Read vault/Company_Handbook.md
```

### 2. Draft the post

Write a draft following the content rules above. The draft must be complete — ready to post as-is.

### 3. Create Pending_Approval file

Create `vault/Pending_Approval/APPROVAL_<YYYYMMDDTHHMMSS>_linkedin_post.md`:

```markdown
---
type: approval_request
action: post_linkedin
description: Post the following content to LinkedIn
created: <ISO timestamp>
expires: <48 hours from now>
status: pending
---

# Approval Required: LinkedIn Post

## Proposed Post

<paste the full draft here>

---

## Why Now

<one sentence explaining why this is timely, referencing Business_Goals.md>

## Risk Assessment

- Reversible: No (once posted, deleting looks unprofessional)
- External impact: Yes (visible to all LinkedIn connections)
- Estimated scope: 1 LinkedIn post, ~200 words

## To Approve

Move this file to `vault/Approved/` then run `/execute-approved`.

## To Reject

Move this file to `vault/Rejected/`.

## To Edit

Edit the "Proposed Post" section above, then move to `vault/Approved/`.
```

### 4. Log the action

```json
{
  "action_type": "linkedin_post_drafted",
  "actor": "claude_code",
  "source_file": "vault/Pending_Approval/APPROVAL_..._linkedin_post.md",
  "result": "success",
  "notes": "LinkedIn post draft created, awaiting human approval"
}
```

### 5. Report to user

```
LinkedIn post draft created.

Pending your review: vault/Pending_Approval/APPROVAL_<timestamp>_linkedin_post.md

To publish:
  1. Review and edit the draft in Obsidian
  2. Move the file to vault/Approved/
  3. Run /execute-approved
```

## Execution (via /execute-approved)

When `/execute-approved` processes a LinkedIn post approval file, it will:

1. Start Playwright browser with LinkedIn session (`LINKEDIN_SESSION_PATH`)
2. Navigate to `https://www.linkedin.com/` and click "Start a post"
3. Paste the post text from the approval file
4. Click "Post" and wait for confirmation
5. Take a screenshot to confirm the post appeared
6. Move the approval file to `vault/Done/`
7. Log the result

See `/execute-approved` skill for the full execution workflow.

## Notes

- Never post without going through Pending_Approval → Approved workflow
- If the LinkedIn session is expired, remind the user to re-authenticate:
  `playwright open --save-storage=./secrets/linkedin_session https://www.linkedin.com`
- A rejected or edited post can be re-queued — just create a new Pending_Approval file
