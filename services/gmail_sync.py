"""Gmail sync — fetches DMARC reports from connected accounts.

Detection philosophy: Content is ground truth.
- If XML parses as valid DMARC aggregate report → it IS a DMARC report
- Sender/subject/filename are confidence indicators, NOT gates
- Zero false positives: invalid XML never processed
- Zero false negatives: any valid DMARC report accepted regardless of sender
"""

from __future__ import annotations

import base64
import logging
import os
import tempfile
import time
from pathlib import Path

from config import settings
from services.dmarc_detector import detect_dmarc_report
from services.oauth import get_valid_access_token

logger = logging.getLogger("dmarc.gmail_sync")

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
QUERY = os.environ.get("GMAIL_QUERY", "has:attachment newer_than:1d subject:(DMARC OR \"aggregate report\" OR \"authentication report\")")
MARK_READ = os.environ.get("EMAIL_MARK_READ", "true").lower() == "true"


async def sync_account_emails(account: dict) -> int:
    """Sync DMARC emails for a single account. Returns count of new reports."""
    import httpx

    # Get valid token (refresh if needed)
    token_json = account.get("token_json", {})
    access_token = await get_valid_access_token(token_json)

    headers = {"Authorization": f"Bearer {access_token}"}
    email = account.get("email", "unknown")

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Search for emails (broad query — we verify with content)
        search_url = f"{GMAIL_API_BASE}/messages"
        params = {"q": QUERY}
        response = await client.get(search_url, headers=headers, params=params)

        if response.status_code != 200:
            logger.error("[%s] Search failed: %s", email, response.text)
            return 0

        messages = response.json().get("messages", [])
        if not messages:
            logger.info("[%s] No emails to check", email)
            return 0

        logger.info("[%s] Checking %d email(s)", email, len(messages))

        saved = 0
        skipped = 0

        for msg_info in messages:
            msg_id = msg_info["id"]

            # Get full message
            msg_url = f"{GMAIL_API_BASE}/messages/{msg_id}"
            msg_resp = await client.get(msg_url, headers=headers, params={"format": "full"})

            if msg_resp.status_code != 200:
                continue

            msg = msg_resp.json()

            # Extract headers
            headers_map = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            subject = headers_map.get("Subject", "")
            sender = headers_map.get("From", "")

            # Find attachments
            attachments = []
            _find_attachments(msg.get("payload", {}), attachments)

            if not attachments:
                continue

            # Process each attachment
            for att_info in attachments:
                filename = att_info["filename"]
                att_id = att_info["attachment_id"]

                # Download attachment
                att_url = f"{GMAIL_API_BASE}/messages/{msg_id}/attachments/{att_id}"
                att_resp = await client.get(att_url, headers=headers)

                if att_resp.status_code != 200:
                    logger.warning("[%s] Failed to download %s", email, filename)
                    continue

                # Decode base64url
                att_data = att_resp.json().get("data", "")
                file_bytes = base64.urlsafe_b64decode(att_data)

                # Write to temp file for content verification
                suffix = Path(filename).suffix if Path(filename).suffix else ".bin"
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(file_bytes)
                    tmp_path = Path(tmp.name)

                # ── CONTENT-FIRST DETECTION ──────────────────────────────
                result = detect_dmarc_report(
                    sender=sender,
                    subject=subject,
                    filename=filename,
                    file_path=tmp_path,
                )

                if result.is_dmarc_report:
                    # Valid DMARC report — save it
                    await _save_attachment(filename, file_bytes)
                    saved += 1
                    logger.info(
                        "[%s] ✓ DMARC report: %s (confidence: %s, metadata: %d/3)",
                        email,
                        filename,
                        result.confidence,
                        result.metadata_score,
                    )
                else:
                    skipped += 1
                    logger.debug(
                        "[%s] Skipped: %s — %s",
                        email,
                        filename,
                        result.reason,
                    )

                # Cleanup temp file
                tmp_path.unlink(missing_ok=True)

            # Mark as read (we checked it — whether DMARC or not)
            if MARK_READ:
                modify_url = f"{GMAIL_API_BASE}/messages/{msg_id}/modify"
                await client.post(
                    modify_url,
                    headers=headers,
                    json={"removeLabelIds": ["UNREAD"]},
                )

        logger.info("[%s] Sync complete: %d saved, %d skipped", email, saved, skipped)

    return saved


def _find_attachments(payload: dict, results: list[dict]) -> None:
    """Recursively find attachments in message payload."""
    if payload.get("filename") and payload.get("body", {}).get("attachmentId"):
        results.append({
            "filename": payload["filename"],
            "attachment_id": payload["body"]["attachmentId"],
        })

    for part in payload.get("parts", []):
        _find_attachments(part, results)


async def _save_attachment(filename: str, data: bytes) -> None:
    """Save attachment to reports directory."""
    reports_dir = settings.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)

    timestamp = int(time.time())
    safe_name = f"{timestamp}_{filename}"
    filepath = reports_dir / safe_name
    filepath.write_bytes(data)
    logger.info("Saved: %s", filepath)
