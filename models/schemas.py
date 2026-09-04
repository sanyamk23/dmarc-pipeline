"""Pydantic schemas for DMARC report API responses."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ── API Response Schemas ──────────────────────────────────────────────────────


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
    created_at: Optional[datetime] = None


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


class UploadResponse(BaseModel):
    """Response from uploading a DMARC report file."""

    status: str  # "ingested" | "duplicate" | "error"
    filename: str
    extracted_files: list[str] = Field(default_factory=list)
    failed_files: list[str] = Field(default_factory=list)
    skipped_duplicates: list[str] = Field(default_factory=list)
    per_file_analysis: list[dict] = Field(default_factory=list)
    collective_analysis: Optional[dict] = None
