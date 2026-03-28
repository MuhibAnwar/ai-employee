---
created: 2026-03-28T16:30:00Z
status: in_progress
source: vault/Needs_Action/EMAIL_PLATINUM_DEMO.md
priority: URGENT
---

# Plan: Respond to Urgent Project Proposal Request

## Objective
Reply to client@example.com acknowledging their request and confirm a proposal will follow.

## Context
Email received while local PC was offline. Codespace GmailWatcher detected it.
Client wants a project proposal by tomorrow — deadline is time-sensitive.
This is a potential new client / revenue opportunity (aligns with $10,000/month Q1 goal).

## Steps
- [x] Read and classify email
- [x] Draft acknowledgement reply → vault/Pending_Approval/
- [ ] Human approves draft reply
- [ ] Execute send via Email MCP (/execute-approved)
- [ ] Draft project proposal document
- [ ] Human approves proposal
- [ ] Send proposal via Email MCP

## Approval Required
- Step 3: Human must move APPROVAL file to vault/Approved/ before reply is sent
- Step 6: Proposal content requires human review before sending

## Notes
- HITL rule: AI never sends email autonomously (Company_Handbook.md §Communication Rules)
- Priority URGENT — client response target < 24 hours (Business_Goals.md KPI)
- Platinum demo gate: this item was triaged by Codespace while local PC was offline
