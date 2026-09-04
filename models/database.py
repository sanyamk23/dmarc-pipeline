"""Async SQLAlchemy setup for DMARC report storage."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings

engine = create_async_engine(settings.database_url, future=True, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


async def init_db() -> None:
    """Create all tables if they don't exist.

    On Render (no persistent disk), the DB file may exist from a build cache
    but with an outdated schema. We handle this by dropping and recreating
    when running in a stateless environment.
    """
    from models import schemas  # noqa: F401  (import to register models)

    # Detect stateless environments (Render, Heroku, etc.)
    stateless = os.environ.get("RENDER") or os.environ.get("DYNO") or settings.database_url.startswith("sqlite+aiosqlite:///:")

    async with engine.begin() as conn:
        if stateless:
            # Drop all tables and recreate (clean slate on each deploy)
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        else:
            # Local dev: create only if not exists (preserves data)
            await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def session_scope():
    """Provide a transactional scope around a series of operations."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
