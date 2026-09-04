"""Supabase client for DMARC report storage.

Uses the Supabase REST API (PostgREST) with service role key.
Data persists in Supabase PostgreSQL and survives deploys.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from config import settings
from supabase import Client, create_client

logger = logging.getLogger("dmarc.db")

# ── Supabase client ──────────────────────────────────────────────────────────

_client: Optional[Client] = None


def get_client() -> Client:
    """Get or create the Supabase client singleton."""
    global _client
    if _client is None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set. "
                "Get them from Supabase Dashboard → Settings → API."
            )
        _client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
        logger.info("Supabase client initialized for %s", settings.supabase_url)
    return _client


# ── CRUD helpers ─────────────────────────────────────────────────────────────


async def select(
    table: str,
    columns: str = "*",
    filters: Optional[dict[str, Any]] = None,
    order: Optional[str] = None,
    limit: Optional[int] = None,
    count: Optional[str] = None,
):
    """Query rows from a table. Returns list[dict] or (list[dict], count) if count specified."""
    client = get_client()
    query = client.table(table).select(columns, count=count)

    if filters:
        for column, value in filters.items():
            query = query.eq(column, value)

    if order:
        parts = order.split(".")
        col = parts[0]
        desc = len(parts) > 1 and parts[1].lower() == "desc"
        query = query.order(col, desc=desc)

    if limit:
        query = query.limit(limit)

    response = query.execute()
    return response.data


async def select_single(
    table: str,
    record_id: int,
    columns: str = "*",
) -> Optional[dict]:
    """Get a single row by primary key."""
    client = get_client()
    response = client.table(table).select(columns).eq("id", record_id).single().execute()
    return response.data


async def insert(table: str, data: dict | list[dict]) -> list[dict]:
    """Insert one or more rows."""
    client = get_client()
    response = client.table(table).insert(data).execute()
    return response.data


async def update(table: str, record_id: int, data: dict) -> dict:
    """Update a row by primary key."""
    client = get_client()
    response = client.table(table).update(data).eq("id", record_id).execute()
    return response.data[0] if response.data else {}


async def delete(table: str, record_id: int) -> None:
    """Delete a row by primary key."""
    client = get_client()
    client.table(table).delete().eq("id", record_id).execute()


async def count(table: str, filters: Optional[dict] = None) -> int:
    """Count rows in a table."""
    client = get_client()
    query = client.table(table).select("*", count="exact", head=True)
    if filters:
        for column, value in filters.items():
            query = query.eq(column, value)
    response = query.execute()
    return response.count or 0


async def rpc(function_name: str, params: Optional[dict] = None) -> Any:
    """Call a Supabase Edge Function or database function."""
    client = get_client()
    response = client.rpc(function_name, params or {}).execute()
    return response.data
