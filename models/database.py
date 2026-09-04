"""Async SQLAlchemy setup for DMARC report storage.

Supports:
- SQLite (local dev, file-based)
- PostgreSQL (Neon, Render Postgres, production)

Switch via DMARC_DATABASE_URL environment variable.

Postgres URL format:
    postgresql+asyncpg://user:pass@host/db?sslmode=require
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings

# ── Engine configuration ─────────────────────────────────────────────────────

_is_postgres = settings.database_url.startswith(("postgresql://", "postgresql+asyncpg://"))

_engine_kwargs: dict = {"future": True, "echo": False}

if _is_postgres:
    # Neon / Render Postgres: handle scale-to-zero and connection pooling
    _engine_kwargs.update({
        "pool_pre_ping": True,       # Check connection liveness before use
        "pool_recycle": 300,         # Recycle connections every 5 min
        "pool_size": 5,
        "max_overflow": 10,
    })

engine = create_async_engine(settings.database_url, **_engine_kwargs)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


async def init_db() -> None:
    """Create all tables if they don't exist."""
    from models import schemas  # noqa: F401  (import to register models)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose the engine — call on shutdown."""
    await engine.dispose()


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
