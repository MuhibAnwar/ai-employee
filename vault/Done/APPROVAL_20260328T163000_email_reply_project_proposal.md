---
type: approval_request
action: send_email
description: Send acknowledgement reply to client@example.com re project proposal
source: vault/Needs_Action/EMAIL_PLATINUM_DEMO.md
plan: vault/Plans/PLAN_20260328T163000_Project_Proposal_Response.md
created: 2026-03-28T16:30:00Z
expires: 2026-03-29T16:30:00Z
status: pending
priority: URGENT
to: client@example.com
subject: "Re: Urgent: Project proposal needed"
drafted_by: claude_code (codespace)
---

# Approval Required: Send Email Reply — Project Proposal

## What I Need to Do
Send the following reply to **client@example.com** in response to their urgent
request for a project proposal.

## Proposed Email

**To:** client@example.com
**Subject:** Re: Urgent: Project proposal needed

---

Hi,

Thank you for reaching out. I've received your request and I'm working on the
project proposal now.

I'll have it ready for you shortly. In the meantime, could you share any
specific requirements or budget constraints that would help me tailor the
proposal to your needs?

Looking forward to working together.

Best regards

---
*Draft prepared by AI Assistant — please review before sending.*

## Why This Is Needed
Client sent an urgent email requesting a project proposal by tomorrow.
Responding promptly supports the < 24 hour client response time KPI.
This is a potential revenue opportunity aligned with Q1 $10,000/month goal.

## Risk Assessment
- Reversible: No (email is sent)
- External impact: Yes (client receives message)
- Estimated scope: Single reply to one recipient

## To Approve
Move this file to `vault/Approved/`
Then run `/execute-approved` to send via Email MCP.

## To Reject
Move this file to `vault/Rejected/`
