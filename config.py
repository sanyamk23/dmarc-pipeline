"""Application configuration — loads from environment with safe defaults."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """Runtime configuration, overridable via environment variables."""

    # ── Server ────────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000

    # ── Storage ───────────────────────────────────────────────────────────────
    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR / 'dmarc_reports.db'}"
    reports_dir: Path = BASE_DIR / "reports"
    quarantine_dir: Path = BASE_DIR / "quarantine"
    max_upload_size_mb: int = 50

    # ── Features ──────────────────────────────────────────────────────────────
    watch_folder: bool = True
    worker_count: int = 2

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"

    class Config:
        env_file = BASE_DIR / ".env"
        env_prefix = "DMARC_"   # e.g. DMARC_PORT=9000


settings = Settings()
