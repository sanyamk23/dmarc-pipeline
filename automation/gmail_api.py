"""Gmail API watcher — uses OAuth2 instead of app passwords.

More reliable than IMAP for Gmail. Requires:
1. Google Cloud project with Gmail API enabled
2. credentials.json downloaded from Google Cloud Console
3. First run opens browser for OAuth consent

Usage:
    python -m automation.gmail_api        # Run once
    python -m automation.gmail_api --loop # Poll every 5 min
"""

from __future__ import annotations

import base64
import logging
import os
import time
from pathlib import Path

from config import settings

logger = logging.getLogger("dmarc.gmail_api")

# ── Configuration ─────────────────────────────────────────────────────────────

CREDENTIALS_FILE = os.environ.get("GMAIL_CREDENTIALS_FILE", "credentials.json")
TOKEN_FILE = os.environ.get("GMAIL_TOKEN_FILE", "token.json")
GMAIL_QUERY = os.environ.get("GMAIL_QUERY", "subject:DMARC has:attachment newer_than:1d")
POLL_INTERVAL = int(os.environ.get("EMAIL_POLL_INTERVAL", "300"))
MARK_READ = os.environ.get("EMAIL_MARK_READ", "true").lower() == "true"

# ── Gmail API setup ───────────────────────────────────────────────────────────

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False
    logger.warning("google-api-python-client not installed. Run: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")


SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def get_gmail_service():
    """Authenticate and return Gmail API service."""
    if not GMAIL_AVAILABLE:
        raise RuntimeError("Gmail API libraries not installed")

    creds = None
    token_path = Path(TOKEN_FILE)
    credentials_path = Path(CREDENTIALS_FILE)

    # Load existing token
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    # Refresh or create new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not credentials_path.exists():
                raise RuntimeError(
                    f"Credentials file not found: {credentials_path}. "
                    "Download from Google Cloud Console → APIs & Services → Credentials"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token for future runs
        token_path.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def fetch_dmarc_emails(service) -> list[tuple[str, bytes]]:
    """Search for DMARC emails and extract attachments."""
    results = service.users().messages().list(userId="me", q=GMAIL_QUERY).execute()
    messages = results.get("messages", [])

    if not messages:
        return []

    logger.info("Found %d new DMARC email(s)", len(messages))

    attachments: list[tuple[str, bytes]] = []

    for msg_info in messages:
        msg = service.users().messages().get(userId="me", id=msg_info["id"], format="full").execute()

        # Extract headers
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        subject = headers.get("Subject", "Unknown")
        sender = headers.get("From", "Unknown")
        logger.info("Processing: %s (from %s)", subject, sender)

        # Extract attachments from parts
        if "parts" in msg["payload"]:
            for part in msg["payload"]["parts"]:
                if part.get("filename") and part.get("body", {}).get("attachmentId"):
                    filename = part["filename"]
                    if filename.lower().endswith((".zip", ".xml", ".gz")):
                        att_id = part["body"]["attachmentId"]
                        att = service.users().messages().attachments().get(
                            userId="me", messageId=msg_info["id"], id=att_id
                        ).execute()
                        data = base64.urlsafe_b64decode(att["data"])
                        attachments.append((filename, data))
                        logger.info("  → %s (%d bytes)", filename, len(data))

        # Mark as read
        if MARK_READ:
            service.users().messages().modify(
                userId="me", id=msg_info["id"], body={"removeLabelIds": ["UNREAD"]}
            ).execute()

    return attachments


def process_attachments(attachments: list[tuple[str, bytes]]) -> int:
    """Save attachments to reports directory for processing."""
    if not attachments:
        return 0

    reports_dir = settings.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for filename, data in attachments:
        timestamp = int(time.time())
        safe_name = f"{timestamp}_{filename}"
        filepath = reports_dir / safe_name
        filepath.write_bytes(data)
        logger.info("Saved: %s", filepath)
        count += 1

    return count


# ── Main loop ─────────────────────────────────────────────────────────────────


def run_once() -> int:
    """Run a single check."""
    service = get_gmail_service()
    attachments = fetch_dmarc_emails(service)
    return process_attachments(attachments)


def run_loop() -> None:
    """Run continuous polling."""
    logger.info("Starting Gmail API watcher (poll interval: %ds)", POLL_INTERVAL)

    while True:
        try:
            count = run_once()
            if count > 0:
                logger.info("Processed %d new report(s)", count)
        except Exception as exc:
            logger.error("Gmail check failed: %s", exc)

        time.sleep(POLL_INTERVAL)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DMARC Gmail API Watcher")
    parser.add_argument("--loop", action="store_true", help="Run in continuous polling mode")
    args = parser.parse_args()

    from logging_config import setup_logging
    setup_logging()

    if args.loop:
        run_loop()
    else:
        count = run_once()
        print(f"Processed {count} new report(s)")
