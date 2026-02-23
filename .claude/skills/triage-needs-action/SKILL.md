---
name: triage-needs-action
description: |
  Read and reason about all items in vault/Needs_Action/. For each item,
  assess priority, create a Plan.md in vault/Plans/ for multi-step tasks,
  create a Pending_Approval file for sensitive actions, and move completed
  simple items to vault/Done/. This is the core reasoning loop of the
  AI Employee. Always reads Company_Handbook.md rules before acting.
  Handles items from ALL watcher sources: email, linkedin, facebook,
  instagram, twitter, and filesystem.
---

# Triage Needs Action

Reason about items in `vault/Needs_Action/` and decide what to do with each one.
Handles items from all six watcher sources with source-appropriate routing.

## When to Use

- After running `/process-inbox`
- When `vault/Needs_Action/` has unprocessed items
- As the main "work" step in the AI Employee loop

## Pre-Flight

**Before processing any item:**

1. Read `vault/Company_Handbook.md` — internalize the rules
2. Read `vault/Business_Goals.md` — understand current objectives
3. List all files in `vault/Needs_Action/` (skip `.gitkeep`)

If `Needs_Action/` is empty, report "Nothing to triage" and stop.

## Source Identification

Every action file has a `watcher:` field in its YAML frontmatter. Use this to
apply source-appropriate triage logic:

| Watcher | File Prefix | Source Domain | Key Routing Rule |
|---------|-------------|---------------|-----------------|
| `FileSystemWatcher` | `FILE_` | Local filesystem | Classify by filename keywords |
| `GmailWatcher` | `EMAIL_` | Email | Replies → NEEDS_APPROVAL (send_email) |
| `LinkedInWatcher` | `LINKEDIN_` | LinkedIn | Comments/DMs → NEEDS_APPROVAL; notifications → INFO_ONLY |
| `FacebookWatcher` | `FACEBOOK_` | Facebook | Comments → NEEDS_APPROVAL; posts → INFO_ONLY |
| `InstagramWatcher` | `INSTAGRAM_` | Instagram | Comments → NEEDS_APPROVAL; likes → INFO_ONLY |
| `TwitterWatcher` | `TWITTER_` | Twitter/X | Replies/DMs → NEEDS_APPROVAL; likes/RTs → INFO_ONLY |

If `watcher:` is missing, fall back to filename-based classification.

## Decision Tree

For each item in `vault/Needs_Action/`, apply this decision tree:

```
Read item → identify watcher source
    │
    ├─ FileSystemWatcher (FILE_*)
    │       ├─ Filename has urgent/deadline keywords → URGENT priority
    │       ├─ Filename has invoice/contract keywords → HIGH priority, NEEDS_APPROVAL
    │       └─ Otherwise → classify by content
    │
    ├─ GmailWatcher (EMAIL_*)
    │       ├─ Subject has urgent/invoice/payment → HIGH/URGENT + NEEDS_APPROVAL
    │       ├─ Requires a reply → NEEDS_APPROVAL (action: send_email)
    │       └─ FYI / newsletter / notification → INFO_ONLY
    │
    ├─ LinkedInWatcher (LINKEDIN_*)
    │       ├─ Direct message or comment requiring reply → NEEDS_APPROVAL (action: post_linkedin)
    │       ├─ Connection request → NEEDS_APPROVAL
    │       └─ Like / view notification → INFO_ONLY
    │
    ├─ FacebookWatcher (FACEBOOK_*)
    │       ├─ Comment or message requiring reply → NEEDS_APPROVAL (action: post_facebook)
    │       └─ Like / reaction notification → INFO_ONLY
    │
    ├─ InstagramWatcher (INSTAGRAM_*)
    │       ├─ Comment requiring reply → NEEDS_APPROVAL (action: post_instagram)
    │       └─ Like / follow notification → INFO_ONLY
    │
    ├─ TwitterWatcher (TWITTER_*)
    │       ├─ Reply or DM requiring response → NEEDS_APPROVAL (action: post_twitter)
    │       └─ Like / retweet / follow → INFO_ONLY
    │
    └─ Any source — apply general rules:
            ├─ Is this a simple note/info file with no action needed?
            │       └─ YES → Add summary to Dashboard, move to /Done
            ├─ Does acting on this require external communication (email, message)?
            │       └─ YES → Create Pending_Approval file
            ├─ Does acting on this require a payment or financial action?
            │       └─ YES → ALWAYS create Pending_Approval file (no exceptions)
            ├─ Is this a multi-step task requiring planning?
            │       └─ YES → Create Plan.md in /Plans → move item to /Done
            └─ Is this a simple, safe, local task?
                    └─ YES → Execute directly → log → move to /Done
```

## Steps

### For each item:

1. **Read the action file** in `vault/Needs_Action/`

2. **Classify the action needed:**
   - `INFO_ONLY` — No action, just a note or reference
   - `NEEDS_PLAN` — Multi-step task requiring a Plan.md
   - `NEEDS_APPROVAL` — External action (email, payment, message)
   - `SAFE_LOCAL` — Simple local task (create a file, update a note)

3. **Act based on classification:**

   **INFO_ONLY:**
   - Note the content in your response
   - Move file to `vault/Done/`
   - Log action

   **NEEDS_PLAN:**
   - Create `vault/Plans/PLAN_YYYYMMDDTHHMMSS_<topic>.md`:
     ```markdown
     ---
     created: <ISO timestamp>
     status: in_progress
     source: vault/Needs_Action/<filename>
     priority: <priority from source file>
     ---

     # Plan: <Task Name>

     ## Objective
     <Clear one-line goal>

     ## Steps
     - [ ] Step 1
     - [ ] Step 2
     - [ ] Step 3

     ## Approval Required
     <List any steps that need human approval>

     ## Notes
     <Reasoning and context>
     ```
   - Move source file to `vault/Done/`
   - Log action

   **NEEDS_APPROVAL:**
   - Create `vault/Pending_Approval/APPROVAL_YYYYMMDDTHHMMSS_<topic>.md`:
     ```markdown
     ---
     type: approval_request
     action: <action_type>
     description: <what will happen>
     source: vault/Needs_Action/<filename>
     created: <ISO timestamp>
     expires: <24 hours from now>
     status: pending
     ---

     # Approval Required: <Action Description>

     ## What I Need to Do
     <Clear description of the proposed action>

     ## Why This Is Needed
     <Context from the source item>

     ## Risk Assessment
     - Reversible: <Yes/No>
     - External impact: <Yes/No>
     - Estimated scope: <description>

     ## To Approve
     Move this file to `vault/Approved/`

     ## To Reject
     Move this file to `vault/Rejected/`
     ```
   - Leave source file in `vault/Needs_Action/` (link it to the approval file)
   - Log action

   **SAFE_LOCAL:**
   - Execute the action directly (e.g., create a note, update a file)
   - Move source file to `vault/Done/`
   - Log action

4. **Log every decision** to `vault/Logs/YYYY-MM-DD.json`

5. **After all items processed**, run `/update-dashboard`

## Output Format

Report a triage summary grouped by source domain:

```
Triage complete. Processed 5 items:

[FileSystem]
1. [INFO_ONLY]      FILE_20260219T103000_notes.md → /Done

[Email]
2. [NEEDS_APPROVAL] EMAIL_20260222T090000_invoice_client_a.md
                    → APPROVAL created: APPROVAL_..._reply_invoice.md

[LinkedIn]
3. [INFO_ONLY]      LINKEDIN_20260222T090100_post_liked.md → /Done

[Facebook]
4. [NEEDS_APPROVAL] FACEBOOK_20260222T090200_comment_on_post.md
                    → APPROVAL created: APPROVAL_..._facebook_reply.md

[Twitter]
5. [INFO_ONLY]      TWITTER_20260222T090300_new_follower.md → /Done

Pending your approval: 2 items in vault/Pending_Approval/
Dashboard updated.
```

## Notes

- Never send emails, messages, or social posts — always go through Pending_Approval
- If uncertain about classification, default to `NEEDS_APPROVAL`
- Read `Company_Handbook.md` for keyword-based priority rules
- All plan files and approval files must have complete YAML frontmatter
- The `watcher:` frontmatter field is authoritative for source routing
- Social media replies use `action: post_facebook / post_instagram / post_twitter / post_linkedin`
