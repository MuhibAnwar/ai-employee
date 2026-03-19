---
type: plan
priority: urgent
created: 2026-03-01T00:00:00Z
status: active
affected_systems:
  - GmailWatcher
  - FacebookWatcher
  - InstagramWatcher
  - TwitterWatcher
  - LinkedInWatcher
  - FileSystemWatcher
---

# PLAN: Watcher Infrastructure Recovery

**Priority:** URGENT — 6 watchers have circuit-breakers OPEN, email monitoring is down.

## Summary

All watchers tripped their circuit breakers around 2026-02-28. Each has a different root cause.
The orchestrator may have already auto-recovered some (LinkedInWatcher, FileSystemWatcher showed
clean startup logs). Resolve in priority order below.

---

## Step 1 — GmailWatcher (HIGHEST PRIORITY)

**Root cause:** Token scope mismatch. `gmail_token.json` was issued with the wrong scope
(`gmail.readonly`) but code now correctly requests `https://mail.google.com/`.
Google rejects the stale token on refresh.

**Fix:**
```
python setup/gmail_auth.py
```
This will open a browser OAuth flow. Authenticate and save the new token. The watcher will
auto-recover on the next HALF_OPEN retry from the orchestrator.

**Why it matters:** GmailWatcher is the primary email monitoring channel. The `test01` item
(send email to muhiblevels@gmail.com) is also blocked until Gmail is re-authenticated.

---

## Step 2 — TwitterWatcher

**Root cause:** API credentials not configured in `.env`.

**Fix:**
1. Add to `.env`:
   ```
   TWITTER_API_KEY=<your key>
   TWITTER_API_SECRET=<your secret>
   TWITTER_ACCESS_TOKEN=<your token>
   TWITTER_ACCESS_SECRET=<your secret>
   ```
2. Restart orchestrator or wait for next HALF_OPEN retry.

---

## Step 3 — InstagramWatcher

**Root cause:** `instagrapi` installed version does not have `news_inbox()` method.
This is a known limitation (noted in project memory). The watcher crashes 3× and trips the circuit.

**Fix options:**
- A) Accept limitation: Remove `news_inbox()` call from `watchers/instagram_watcher.py` — fall back
  to available API methods (e.g., `get_timeline_feed()` or direct DM polling).
- B) Upgrade instagrapi: `pip install --upgrade instagrapi` and test if `news_inbox()` is available.
- C) Session may also be expired — verify `secrets/instagram_session.json` contains `uuids`/`mid`/`ig_did` keys (NOT Playwright-format cookies).

**Recommended:** Option B first, then A if still missing.

---

## Step 4 — FacebookWatcher

**Root cause:** Facebook session (`secrets/facebook_storage.json`) has expired.

**Fix:**
1. On a machine with a browser, log in to Facebook manually.
2. Export cookies (e.g., using a browser extension) and save as `secrets/facebook_storage.json`.
3. Ensure `FACEBOOK_SESSION_PATH` in `.env` points to the right file.

---

## Step 5 — LinkedInWatcher

**Status:** Last log shows clean startup — may have auto-recovered.

**If still failing:**
1. Verify `LINKEDIN_USERNAME` and `LINKEDIN_PASSWORD` in `.env`.
2. `pip install linkedin-api` if not installed.
3. Wait 15 min and retry (rate-limit backoff).

---

## Step 6 — FileSystemWatcher

**Status:** Last log shows healthy: "Monitoring drop folder" + "Press Ctrl+C to stop".
Likely auto-recovered. No action needed unless it appears DOWN again.

---

## After All Fixes

1. Move each `ALERT_*_DOWN.md` file from `vault/Needs_Action/` to `vault/Done/` to acknowledge.
2. Run `/update-dashboard` to refresh watcher health indicators.
3. Once GmailWatcher is working: run `/execute-approved` to retry the `test01` email.

---

## Related Items

- `vault/Needs_Action/ALERT_GmailWatcher_DOWN.md`
- `vault/Needs_Action/ALERT_FacebookWatcher_DOWN.md`
- `vault/Needs_Action/ALERT_InstagramWatcher_DOWN.md`
- `vault/Needs_Action/ALERT_TwitterWatcher_DOWN.md`
- `vault/Needs_Action/ALERT_LinkedInWatcher_DOWN.md`
- `vault/Needs_Action/ALERT_FileSystemWatcher_DOWN.md`
- `vault/Needs_Action/FILE_20260226T010002_test01.md` (blocked on Gmail fix)
