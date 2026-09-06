"""Gmail account management — OAuth tokens stored in Supabase.

Table: gmail_accounts
- id: bigint PK
- user_id: text (for future multi-user support)
- email: text (Gmail address)
- credentials_json: jsonb (OAuth client config)
- token_json: jsonb (OAuth tokens — encrypted at rest in production)
- is_active: boolean
- last_sync: timestamptz
- created_at: timestamptz
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from models import insert, select, select_single, update, delete

logger = logging.getLogger("dmarc.accounts")

TABLE = "gmail_accounts"


def add_account(email: str, credentials: dict, token: dict) -> dict:
    """Store a new Gmail account with OAuth tokens."""
    data = {
        "email": email,
        "credentials_json": credentials,
        "token_json": token,
        "is_active": True,
    }
    result = insert(TABLE, data)
    logger.info("Added Gmail account: %s", email)
    return result[0] if result else {}


def list_accounts(active_only: bool = True) -> list[dict]:
    """List all connected Gmail accounts."""
    filters = {"is_active": True} if active_only else {}
    return select(TABLE, filters=filters, order="created_at.desc")


def get_account(account_id: int) -> Optional[dict]:
    """Get a single account by ID."""
    return select_single(TABLE, account_id)


def get_account_by_email(email: str) -> Optional[dict]:
    """Get account by email address."""
    results = select(TABLE, filters={"email": email, "is_active": True}, limit=1)
    return results[0] if results else None


def update_token(account_id: int, token: dict) -> None:
    """Update OAuth token (after refresh)."""
    update(TABLE, account_id, {"token_json": token})


def update_sync_time(account_id: int, sync_time: str) -> None:
    """Update last sync timestamp."""
    update(TABLE, account_id, {"last_sync": sync_time})


def deactivate_account(account_id: int) -> None:
    """Soft-delete an account."""
    update(TABLE, account_id, {"is_active": False})


def delete_account(account_id: int) -> None:
    """Hard-delete an account."""
    delete(TABLE, account_id)
