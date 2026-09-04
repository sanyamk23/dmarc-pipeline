"""ORM models + Pydantic schemas for DMARC report data."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pydantic import BaseModel, ConfigDict, Field

from models.database import Base


# ── ORM Models ────────────────────────────────────────────────────────────────


class DmarcReport(Base):
    """One row per uploaded DMARC feedback report (the XML envelope)."""

    __tablename__ = "dmarc_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    xml_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    archive_filename: Mapped[Optional[str]] = mapped_column(String(255))
    org_name: Mapped[Optional[str]] = mapped_column(String(255))
    org_email: Mapped[Optional[str]] = mapped_column(String(255))
    report_id: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    date_begin: Mapped[Optional[datetime]] = mapped_column(DateTime)
    date_end: Mapped[Optional[datetime]] = mapped_column(DateTime)
    domain: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    adkim: Mapped[Optional[str]] = mapped_column(String(8))
    aspf: Mapped[Optional[str]] = mapped_column(String(8))
    p: Mapped[Optional[str]] = mapped_column(String(16))
    sp: Mapped[Optional[str]] = mapped_column(String(16))
    pct: Mapped[Optional[int]] = mapped_column(Integer)
    raw_xml: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return f"<DmarcReport id={self.id} report_id={self.report_id}>"


class DmarcRecord(Base):
    """One row per DMARC auth result record (per source IP / evaluated message)."""

    __tablename__ = "dmarc_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(Integer, index=True)
    source_ip: Mapped[Optional[str]] = mapped_column(String(45), index=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    header_from: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    envelope_from: Mapped[Optional[str]] = mapped_column(String(255))
    envelope_to: Mapped[Optional[str]] = mapped_column(String(255))
    disposition: Mapped[Optional[str]] = mapped_column(String(16))
    dkim_aligned: Mapped[Optional[bool]] = mapped_column()
    spf_aligned: Mapped[Optional[bool]] = mapped_column()
    dkim_result: Mapped[Optional[str]] = mapped_column(String(16))
    spf_result: Mapped[Optional[str]] = mapped_column(String(16))
    dkim_domain: Mapped[Optional[str]] = mapped_column(String(255))
    spf_domain: Mapped[Optional[str]] = mapped_column(String(255))
    auth_failure: Mapped[Optional[str]] = mapped_column(String(255))
    # Full auth detail as JSON — stores lists of {domain, result, selector, scope}
    dkim_auth_json: Mapped[Optional[str]] = mapped_column(Text)
    spf_auth_json: Mapped[Optional[str]] = mapped_column(Text)

    def __repr__(self) -> str:  # pragma: no cover - convenience
        return f"<DmarcRecord ip={self.source_ip} dkim={self.dkim_result} spf={self.spf_result}>"


# ── Pydantic API Schemas ──────────────────────────────────────────────────────


class ReportMetadata(BaseModel):
    """Public view of a stored report envelope."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    xml_filename: str
    org_name: Optional[str] = None
    report_id: Optional[str] = None
    date_begin: Optional[datetime] = None
    date_end: Optional[datetime] = None
    domain: Optional[str] = None
    adkim: Optional[str] = None
    aspf: Optional[str] = None
    p: Optional[str] = None
    sp: Optional[str] = None
    pct: Optional[int] = None
    record_count: int = 0
    pass_count: int = 0
    fail_count: int = 0
    created_at: datetime


class RecordRow(BaseModel):
    """Public view of a single DMARC record row."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    report_id: int
    source_ip: Optional[str] = None
    count: int = 0
    header_from: Optional[str] = None
    disposition: Optional[str] = None
    dkim_aligned: Optional[bool] = None
    spf_aligned: Optional[bool] = None
    dkim_result: Optional[str] = None
    spf_result: Optional[str] = None
    dkim_domain: Optional[str] = None
    spf_domain: Optional[str] = None


class StatsSummary(BaseModel):
    """Aggregated DMARC statistics across all (or filtered) reports."""

    total_reports: int = 0
    total_records: int = 0
    total_messages: int = 0
    pass_count: int = 0
    fail_count: int = 0
    dkim_pass: int = 0
    dkim_fail: int = 0
    spf_pass: int = 0
    spf_fail: int = 0
    top_source_ips: list[dict] = Field(default_factory=list)
    top_header_froms: list[dict] = Field(default_factory=list)
    per_domain: list[dict] = Field(default_factory=list)


# ── Upload response schemas ───────────────────────────────────────────────────


class UploadResponse(BaseModel):
    """Response from uploading a DMARC report file."""

    status: str  # "ingested" | "duplicate" | "error"
    filename: str
    extracted_files: list[str] = Field(default_factory=list)
    failed_files: list[str] = Field(default_factory=list)
    skipped_duplicates: list[str] = Field(default_factory=list)
    per_file_analysis: list[dict] = Field(default_factory=list)
    collective_analysis: Optional[dict] = None
