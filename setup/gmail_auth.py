"""
setup/gmail_auth.py — One-time Gmail OAuth2 consent flow

Run this once to authorise the AI Employee to access Gmail.
It opens a browser, asks you to log in and grant permission,
then saves the token to ./secrets/gmail_token.json.

The saved token is reused by:
  - watchers/gmail_watcher.py  (reading unread important emails)
  - mcp-servers/email-mcp/     (sending / drafting emails)

Usage:
    python setup/gmail_auth.py

Requirements:
    pip install google-auth-oauthlib
"""

import sys
from pathlib import Path

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("ERROR: google-auth-oauthlib is not installed.")
    print("Run: pip install google-auth-oauthlib")
    sys.exit(1)

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_FILE = PROJECT_ROOT / "secrets" / "gmail_credentials.json"
TOKEN_FILE       = PROJECT_ROOT / "secrets" / "gmail_token.json"

# Full https://mail.google.com/ scope covers read + send + compose + modify.
# This is the broadest Gmail scope — use it so both the watcher and MCP server
# share one token without scope mismatch errors.
SCOPES = ["https://mail.google.com/"]
# ── Pre-flight ────────────────────────────────────────────────────────────────
if not CREDENTIALS_FILE.exists():
    print(f"ERROR: Credentials file not found:")
    print(f"  {CREDENTIALS_FILE}")
    print()
    print("Download it from Google Cloud Console:")
    print("  APIs & Services > Credentials > your OAuth client > Download JSON")
    print(f"  Save as: {CREDENTIALS_FILE}")
    sys.exit(1)

# ── OAuth flow ────────────────────────────────────────────────────────────────
print(f"Credentials file: {CREDENTIALS_FILE}")
print(f"Token will be saved to: {TOKEN_FILE}")
print()
print("Opening browser for Google OAuth consent...")
print("Log in with your Gmail account and click Allow.")
print()

flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)

# run_local_server opens a browser tab and spins up a temporary localhost server
# to catch the OAuth redirect. Port 0 = OS picks a free port automatically.
creds = flow.run_local_server(port=0)

# ── Save token ────────────────────────────────────────────────────────────────
TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

print()
print(f"SUCCESS: Token saved to {TOKEN_FILE}")
print()
print("Next steps:")
print("  1. Confirm the file exists: dir secrets\\gmail_token.json")
print("  2. Tell Claude Code 'token is saved' to update .env")
