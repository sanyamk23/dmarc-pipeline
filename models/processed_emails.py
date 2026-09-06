"""Track processed email message IDs to avoid reprocessing.

Since we use gmail.readonly scope (can't mark as read),
we track which message IDs we've already processed in Supabase.

Table: processed_emails
- id: bigint PK
- account_id: bigint (references gmail_accounts)
- message_id: text (Gmail message ID)
- processed_at: timestamptz
"""

from __future__ import annotations

from models import insert, select

TABLE = "processed_emails"


def is_processed(account_id: int, message_id: str) -> bool:
    """Check if a message has already been processed."""
    results = select(
        TABLE,
        filters={"account_id": account_id, "message_id": message_id},
        limit=1,
    )
    return len(results) > 0


def mark_processed(account_id: int, message_id: str) -> None:
    """Mark a message as processed."""
    from datetime import datetime, timezone

    insert(TABLE, {
        "account_id": account_id,
        "message_id": message_id,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    })


def get_processed_count(account_id: int) -> int:
    """Get count of processed messages for an account."""
    return select(
        TABLE,
        filters={"account_id": account_id},
        count="exact",
    )
