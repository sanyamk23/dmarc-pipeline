"""Email watcher — automatically fetches DMARC reports from inbox.

Supports:
- IMAP (Gmail, Outlook, Yahoo, custom)
- OAuth2 (Gmail API)
- API polling (cron-friendly)

Usage:
    python -m automation.email_watcher        # Run once
    python -m automation.email_watcher --loop # Poll every 5 min

Environment variables:
    EMAIL_HOST       — IMAP host (default: imap.gmail.com)
    EMAIL_PORT       — IMAP port (default: 993)
    EMAIL_USER       — Email address
    EMAIL_PASSWORD   — App password (not your real password!)
    EMAIL_FOLDER     — Folder to watch (default: INBOX)
    EMAIL_SEARCH     — IMAP search query (default: SUBJECT "DMARC")
    EMAIL_MARK_READ  — Mark as read after processing (default: true)
"""

from __future__ import annotations

import email
import imaplib
import logging
import os
import time
import zipfile
from pathlib import Path

from config import settings

logger = logging.getLogger("dmarc.email_watcher")

# ── Configuration ─────────────────────────────────────────────────────────────

HOST = os.environ.get("EMAIL_HOST", "imap.gmail.com")
PORT = int(os.environ.get("EMAIL_PORT", "993"))
USER = os.environ.get("EMAIL_USER", "")
PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
FOLDER = os.environ.get("EMAIL_FOLDER", "INBOX")
SEARCH_QUERY = os.environ.get("EMAIL_SEARCH", 'SUBJECT "DMARC"')
MARK_READ = os.environ.get("EMAIL_MARK_READ", "true").lower() == "true"
POLL_INTERVAL = int(os.environ.get("EMAIL_POLL_INTERVAL", "300"))  # 5 minutes

# ── Email attachment extraction ──────────────────────────────────────────────


def extract_attachments(msg: email.message.Message) -> list[tuple[str, bytes]]:
    """Extract all attachments from an email message."""
    attachments: list[tuple[str, bytes]] = []

    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get("Content-Disposition") is None:
                continue

            filename = part.get_filename()
            if filename:
                data = part.get_payload(decode=True)
                if data:
                    attachments.append((filename, data))
    else:
        filename = msg.get_filename()
        if filename:
            data = msg.get_payload(decode=True)
            if data:
                attachments.append((filename, data))

    return attachments


def is_dmarc_attachment(filename: str) -> bool:
    """Check if filename looks like a DMARC report."""
    lower = filename.lower()
    return lower.endswith((".zip", ".xml", ".xml.gz", ".gz"))


# ── IMAP connection ───────────────────────────────────────────────────────────


def connect() -> imaplib.IMAP4_SSL:
    """Connect to IMAP server."""
    if not USER or not PASSWORD:
        raise RuntimeError(
            "EMAIL_USER and EMAIL_PASSWORD must be set. "
            "For Gmail, use an App Password (not your real password)."
        )

    mail = imaplib.IMAP4_SSL(HOST, PORT)
    mail.login(USER, PASSWORD)
    logger.info("Connected to %s as %s", HOST, USER)
    return mail


def fetch_dmarc_emails(mail: imaplib.IMAP4_SSL) -> list[tuple[str, bytes]]:
    """Search for DMARC emails and extract attachments."""
    mail.select(FOLDER)

    # Search for unread emails matching the query
    status, message_ids = mail.search(None, "(UNSEEN)", SEARCH_QUERY)

    if status != "OK" or not message_ids[0]:
        return []

    email_ids = message_ids[0].split()
    logger.info("Found %d new DMARC email(s)", len(email_ids))

    attachments: list[tuple[str, bytes]] = []

    for eid in email_ids:
        status, msg_data = mail.fetch(eid, "(RFC822)")
        if status != "OK":
            continue

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        # Extract subject for logging
        subject = msg.get("Subject", "Unknown")
        sender = msg.get("From", "Unknown")
        logger.info("Processing: %s (from %s)", subject, sender)

        # Extract attachments
        for filename, data in extract_attachments(msg):
            if is_dmarc_attachment(filename):
                attachments.append((filename, data))
                logger.info("  → %s (%d bytes)", filename, len(data))

        # Mark as read if configured
        if MARK_READ:
            mail.store(eid, "+FLAGS", "\\Seen")

    return attachments


# ── Processing ────────────────────────────────────────────────────────────────


def process_attachments(attachments: list[tuple[str, bytes]]) -> int:
    """Save and process DMARC attachments. Returns count of new reports."""
    if not attachments:
        return 0

    reports_dir = settings.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for filename, data in attachments:
        # Save to reports directory
        timestamp = int(time.time())
        safe_name = f"{timestamp}_{filename}"
        filepath = reports_dir / safe_name
        filepath.write_bytes(data)
        logger.info("Saved: %s", filepath)

        # The folder watcher will pick it up automatically
        count += 1

    return count


# ── Main loop ─────────────────────────────────────────────────────────────────


def run_once() -> int:
    """Run a single email check. Returns number of new reports."""
    mail = connect()
    try:
        attachments = fetch_dmarc_emails(mail)
        return process_attachments(attachments)
    finally:
        mail.logout()


def run_loop() -> None:
    """Run continuous polling loop."""
    logger.info("Starting email watcher (poll interval: %ds)", POLL_INTERVAL)

    while True:
        try:
            count = run_once()
            if count > 0:
                logger.info("Processed %d new report(s)", count)
        except Exception as exc:
            logger.error("Email check failed: %s", exc)

        time.sleep(POLL_INTERVAL)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DMARC Email Watcher")
    parser.add_argument(
        "--loop", action="store_true", help="Run in continuous polling mode"
    )
    args = parser.parse_args()

    from logging_config import setup_logging
    setup_logging()

    if args.loop:
        run_loop()
    else:
        count = run_once()
        print(f"Processed {count} new report(s)")
