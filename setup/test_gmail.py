"""
setup/test_gmail.py — Quick Gmail API connection test

Loads the saved OAuth token and calls users().getProfile() to verify
the connection is working. Prints your email address and total message count.

Usage:
    python setup/test_gmail.py
"""

import sys
from pathlib import Path

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
except ImportError:
    print("ERROR: Gmail API libraries not installed.")
    print("Run: pip install google-auth google-auth-httplib2 google-api-python-client")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOKEN_FILE = PROJECT_ROOT / "secrets" / "gmail_token.json"

if not TOKEN_FILE.exists():
    print(f"ERROR: Token file not found: {TOKEN_FILE}")
    print("Run: python setup/gmail_auth.py")
    sys.exit(1)

print(f"Loading token from: {TOKEN_FILE}")

creds = Credentials.from_authorized_user_file(str(TOKEN_FILE))

# Refresh if expired
if creds.expired and creds.refresh_token:
    print("Token expired — refreshing...")
    creds.refresh(Request())
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    print("Token refreshed and saved.")

service = build("gmail", "v1", credentials=creds)

profile = service.users().getProfile(userId="me").execute()

print()
print("=" * 50)
print(f"  Gmail account : {profile['emailAddress']}")
print(f"  Total messages: {profile['messagesTotal']:,}")
print(f"  Total threads : {profile['threadsTotal']:,}")
print(f"  History ID    : {profile['historyId']}")
print("=" * 50)
print()
print("SUCCESS: Gmail API connection verified.")
