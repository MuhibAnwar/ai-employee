"""
Headless WhatsApp Web setup for environments without a display.
Uses Firefox (which WhatsApp explicitly supports) to avoid bot detection.
Captures the QR code as a PNG so you can scan it.

Usage:
    python watchers/whatsapp_setup_headless.py
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SESSION_PATH = PROJECT_ROOT / "whatsapp_session_ff"   # Firefox profile dir
QR_SCREENSHOT = PROJECT_ROOT / "whatsapp_qr.png"

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
except ImportError:
    print("ERROR: Run: pip install playwright && playwright install firefox")
    sys.exit(1)


def main():
    SESSION_PATH.mkdir(parents=True, exist_ok=True)

    print(f"\nStarting headless WhatsApp Web setup (Firefox)...")
    print(f"Session path: {SESSION_PATH}")
    print(f"QR screenshot: {QR_SCREENSHOT}\n")

    with sync_playwright() as p:
        browser = p.firefox.launch_persistent_context(
            str(SESSION_PATH),
            headless=True,
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto("https://web.whatsapp.com", timeout=60_000)

        print("Waiting for page to load (15s)...")
        time.sleep(15)
        page.screenshot(path=str(QR_SCREENSHOT))
        print(f"Initial screenshot saved: {QR_SCREENSHOT}")

        # Try to find QR code
        qr_selectors = [
            '[data-ref]',
            'canvas',
            '[aria-label*="QR"]',
            '[aria-label*="qr"]',
        ]
        found_qr = False
        for sel in qr_selectors:
            try:
                page.wait_for_selector(sel, timeout=5_000)
                found_qr = True
                print(f"QR code detected (selector: {sel})")
                break
            except PWTimeoutError:
                continue

        # Already logged in?
        if not found_qr:
            try:
                page.wait_for_selector('[data-testid="chat-list"]', timeout=5_000)
                print("Already logged in! Session is valid.")
                browser.close()
                return
            except PWTimeoutError:
                pass

        time.sleep(2)
        page.screenshot(path=str(QR_SCREENSHOT))
        print(f"\nQR screenshot ready: {QR_SCREENSHOT}")
        print("Scan it with your phone → WhatsApp → Linked Devices → Link a Device\n")

        # Poll until logged in
        print("Waiting for scan (5 min timeout)...")
        deadline = time.time() + 300
        logged_in = False
        while time.time() < deadline:
            try:
                page.wait_for_selector('[data-testid="chat-list"]', timeout=5_000)
                logged_in = True
                break
            except PWTimeoutError:
                try:
                    page.screenshot(path=str(QR_SCREENSHOT))
                except Exception:
                    pass
                print("  ...waiting for scan...")

        if logged_in:
            print("\nLogged in! Session saved to:", SESSION_PATH)
            print("Update WHATSAPP_SESSION_PATH in .env or pass --session to the watcher.")
        else:
            print("\nTimeout. Try again.")

        browser.close()


if __name__ == "__main__":
    main()
