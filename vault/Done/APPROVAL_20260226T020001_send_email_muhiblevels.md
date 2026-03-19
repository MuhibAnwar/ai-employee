---
type: approval_request
action: send_email
description: Send an introductory email about the AI Employee program to muhiblevels@gmail.com
source: vault/Needs_Action/FILE_20260226T010002_test01.md
created: 2026-02-26T02:00:01Z
expires: 2026-02-27T02:00:01Z
status: pending
to: muhiblevels@gmail.com
subject: "Introduction to the AI Employee Program"
---

# Approval Required: Send Email to muhiblevels@gmail.com

## Proposed Email Draft

**To:** muhiblevels@gmail.com
**Subject:** Introduction to the AI Employee Program

---

Hi,

I wanted to share a quick overview of the Personal AI Employee system I've been building.

This is a Silver/Gold Tier autonomous agent built on Claude Code that helps manage personal and business affairs. Here's what it does:

Core Features:
- Monitors vault/Inbox/ for new tasks (file drop zone)
- Watches Gmail, LinkedIn, Facebook, Instagram, and Twitter for notifications
- Reasons about each item and routes it through an approval workflow
- Sends emails and posts to LinkedIn — but only after human approval
- Keeps a full audit log in vault/Logs/
- Updates a live Dashboard.md after every task

How It Works:
1. Drop a file in vault/Inbox/ (or receive an email/notification)
2. Run /process-inbox — creates structured action items
3. Run /triage-needs-action — Claude reasons and creates approval requests
4. Review vault/Pending_Approval/ — approve or reject each action
5. Run /execute-approved — sends approved emails or posts

Tech Stack: Python watchers, Playwright browser automation, Gmail OAuth2, Node.js MCP server for email, Claude Code as the reasoning engine, Obsidian as the vault/dashboard.

Let me know if you have any questions!

Draft prepared by AI Assistant — please review before sending.

## To Approve
Already in vault/Approved/ — run /execute-approved after restarting Claude Code.

## To Reject
Move this file to vault/Rejected/
