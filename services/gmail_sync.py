"""Gmail sync — fetches DMARC reports from connected accounts.

Uses multi-layer detection to ensure zero false positives:
  Layer 1: Sender verification (known DMARC reporters)
  Layer 2: Subject line pattern matching
  Layer 3: Attachment filename (RFC 7489 convention)
  Layer 4: XML content validation (ground truth)
"""

from __future__ import annotations

import base64
import logging
import os
import time

from config import settings
from services.dmarc_detector import detect_dmarc_report
from services.oauth import get_valid_access_token

logger = logging.getLogger("dmarc.gmail_sync")

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
QUERY = os.environ.get("GMAIL_QUERY", "subject:DMARC has:attachment newer_than:1d")
MARK_READ = os.environ.get("EMAIL_MARK_READ", "true").lower() == "true"


async def sync_account_emails(account: dict) -> int:
    """Sync DMARC emails for a single account. Returns count of new reports."""
    import httpx

    # Get valid token (refresh if needed)
    token_json = account.get("token_json", {})
    access_token = await get_valid_access_token(token_json)

    headers = {"Authorization": f"Bearer {access_token}"}
    email = account.get("email", "unknown")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Search for emails
        search_url = f"{GMAIL_API_BASE}/messages"
        params = {"q": QUERY}
        response = await client.get(search_url, headers=headers, params=params)

        if response.status_code != 200:
            logger.error("[%s] Search failed: %s", email, response.text)
            return 0

        messages = response.json().get("messages", [])
        if not messages:
            logger.info("[%s] No new DMARC emails", email)
            return 0

        logger.info("[%s] Found %d email(s) to check", email, len(messages))

        count = 0
        skipped = 0

        for msg_info in messages:
            msg_id = msg_info["id"]

            # Get full message
            msg_url = f"{GMAIL_API_BASE}/messages/{msg_id}"
            msg_resp = await client.get(
                msg_url, headers=headers, params={"format": "full"}
            )

            if msg_resp.status_code != 200:
                continue

            msg = msg_resp.json()

            # Extract headers
            headers_map = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            subject = headers_map.get("Subject", "")
            sender = headers_map.get("From", "")

            # Find attachments
            attachments_to_fetch = []
            _find_attachments(msg.get("payload", {}), attachments_to_fetch)

            if not attachments_to_fetch:
                continue

            # Process each attachment
            for att_info in attachments_to_fetch:
                filename = att_info["filename"]
                att_id = att_info["attachment_id"]

                # Layer 1-3: Quick checks before downloading
                result = detect_dmarc_report(
                    sender=sender,
                    subject=subject,
                    filename=filename,
                )

                if not result.is_dmarc_report:
                    logger.info(
                        "[%s] Skipped: %s (reason: %s)",
                        email,
                        filename,
                        result.reason,
                    )
                    skipped += 1
                    continue

                # Download attachment
                att_url = (
                    f"{GMAIL_API_BASE}/messages/{msg_id}"
                    f"/attachments/{att_id}"
                )
                att_resp = await client.get(att_url, headers=headers)

                if att_resp.status_code != 200:
                    logger.warning("[%s] Failed to fetch %s", email, filename)
                    continue

                # Decode
                att_data = att_resp.json().get("data", "")
                file_bytes = base64.urlsafe_b64decode(att_data)

                # Layer 4: Content validation (ground truth)
                from pathlib import Path
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=Path(filename).suffix, delete=False) as tmp:
                    tmp.write(file_bytes)
                    tmp_path = Path(tmp.name)

                final_result = detect_dmarc_report(
                    sender=sender,
                    subject=subject,
                    filename=filename,
                    file_path=tmp_path,
                )

                if not final_result.is_dmarc_report:
                    logger.info(
                        "[%s] Rejected after content check: %s (reason: %s)",
                        email,
                        filename,
                        final_result.reason,
                    )
                    skipped += 1
                    tmp_path.unlink(missing_ok=True)
                    continue

                # All layers passed — save it
                await _save_attachment(filename, file_bytes)
                count += 1
                tmp_path.unlink(missing_ok=True)

                logger.info(
                    "[%s] ✓ DMARC report saved: %s (confidence: %s)",
                    email,
                    filename,
                    final_result.confidence,
                )

            # Mark as read
            if MARK_READ:
                modify_url = f"{GMAIL_API_BASE}/messages/{msg_id}/modify"
                await client.post(
                    modify_url,
                    headers=headers,
                    json={"removeLabelIds": ["UNREAD"]},
                )

        logger.info(
            "[%s] Sync complete: %d saved, %d skipped",
            email,
            count,
            skipped,
        )

    return count


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
    logger.info("Saved to: %s", filepath)
