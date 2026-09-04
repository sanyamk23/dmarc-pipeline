"""Parser for DMARC aggregate report XML (RFC 7489).

Handles the standard ``.xml`` report format and the common ``.xml.gz``/``.zip``
compression wrappers transparently — callers just hand in a filename and the
raw bytes; the parser normalises from there.
"""

from __future__ import annotations

import gzip
import io
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from xml.etree import ElementTree as ET


# ── Public data structures ────────────────────────────────────────────────────


@dataclass
class PolicyPublished:
    domain: Optional[str] = None
    adkim: Optional[str] = None
    aspf: Optional[str] = None
    p: Optional[str] = None
    sp: Optional[str] = None
    pct: Optional[int] = None


@dataclass
class DkimAuth:
    domain: Optional[str] = None
    result: Optional[str] = None
    selector: Optional[str] = None


@dataclass
class SpfAuth:
    domain: Optional[str] = None
    result: Optional[str] = None
    scope: Optional[str] = None


@dataclass
class Record:
    source_ip: Optional[str] = None
    count: int = 0
    header_from: Optional[str] = None
    envelope_from: Optional[str] = None
    envelope_to: Optional[str] = None
    disposition: Optional[str] = None
    dkim_result: Optional[str] = None
    spf_result: Optional[str] = None
    dkim_aligned: bool = False
    spf_aligned: bool = False
    dkim_auth: list[DkimAuth] = field(default_factory=list)
    spf_auth: list[SpfAuth] = field(default_factory=list)


@dataclass
class ReportMetadata:
    org_name: Optional[str] = None
    org_email: Optional[str] = None
    report_id: Optional[str] = None
    date_begin: Optional[datetime] = None
    date_end: Optional[datetime] = None
    errors: list[str] = field(default_factory=list)
    extra_uri: list[str] = field(default_factory=list)
    policy: PolicyPublished = field(default_factory=PolicyPublished)


@dataclass
class DmarcReport:
    metadata: ReportMetadata = field(default_factory=ReportMetadata)
    records: list[Record] = field(default_factory=list)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _text(node: Optional[ET.Element], default: Optional[str] = None) -> Optional[str]:
    """Return stripped text of an element, or ``default`` if missing/blank."""
    if node is None or node.text is None:
        return default
    value = node.text.strip()
    return value if value else default


def _int(node: Optional[ET.Element], default: int = 0) -> int:
    text = _text(node)
    if text is None:
        return default
    try:
        return int(text)
    except ValueError:
        return default


def _parse_timestamp(node: Optional[ET.Element]) -> Optional[datetime]:
    """DMARC timestamps are Unix epoch seconds."""
    value = _int(node)
    if value is None or value == 0:
        return None
    try:
        return datetime.utcfromtimestamp(value)
    except (OSError, OverflowError, ValueError):
        return None


def _decompress_if_needed(data: bytes) -> bytes:
    """Transparently decompress gzip payloads (``.xml.gz`` common from Gmail)."""
    if data[:2] == b"\x1f\x8b":
        return gzip.decompress(data)
    return data


# ── Core parser ───────────────────────────────────────────────────────────────


def parse_dmarc_xml(filename: str, data: bytes) -> DmarcReport:
    """Parse DMARC aggregate report XML from raw bytes.

    Args:
        filename: Original filename — used only for error context, not logic.
        data: Raw bytes of the XML file (or a gzip-compressed XML payload).

    Returns:
        A structured :class:`DmarcReport` instance.
    """
    raw = _decompress_if_needed(data)
    try:
        root = ET.fromstring(raw.decode("utf-8", errors="replace"))
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML in {filename}: {exc}") from exc

    report = DmarcReport()

    # ── Report metadata ───────────────────────────────────────────────────
    meta = root.find("report_metadata")
    if meta is not None:
        report.metadata.org_name = _text(meta.find("org_name"))
        report.metadata.org_email = _text(meta.find("email")) or _text(
            meta.find("extra_contact_info")
        )
        report.metadata.report_id = _text(meta.find("report_id"))
        report.metadata.date_begin = _parse_timestamp(meta.find("date_range/begin"))
        report.metadata.date_end = _parse_timestamp(meta.find("date_range/end"))
        for err in meta.findall("error"):
            if err.text and err.text.strip():
                report.metadata.errors.append(err.text.strip())

    # ── Policy published ──────────────────────────────────────────────────
    pp = root.find("policy_published")
    if pp is not None:
        report.metadata.policy.domain = _text(pp.find("domain"))
        report.metadata.policy.adkim = _text(pp.find("adkim"))
        report.metadata.policy.aspf = _text(pp.find("aspf"))
        report.metadata.policy.p = _text(pp.find("p"))
        report.metadata.policy.sp = _text(pp.find("sp"))
        report.metadata.policy.pct = _int(pp.find("pct"), 100)

    # ── Records ────────────────────────────────────────────────────────────
    for rec in root.findall("record"):
        row = _parse_record(rec)
        report.records.append(row)

    return report


def _parse_record(rec: ET.Element) -> Record:
    """Parse a single ``<record>`` element into a :class:`Record`."""
    source_ip_el = rec.find("row/source_ip")
    if source_ip_el is None:
        source_ip_el = rec.find("row/source")
    dkim_result = _text(rec.find("row/policy_evaluated/dkim"))
    spf_result = _text(rec.find("row/policy_evaluated/spf"))
    row = Record(
        source_ip=_text(source_ip_el),
        count=_int(rec.find("row/count")),
        header_from=_text(rec.find("identifiers/header_from")),
        envelope_from=_text(rec.find("identifiers/envelope_from")),
        envelope_to=_text(rec.find("identifiers/envelope_to")),
        disposition=_text(rec.find("row/policy_evaluated/disposition")),
        dkim_result=dkim_result,
        spf_result=spf_result,
        dkim_aligned=dkim_result == "pass",
        spf_aligned=spf_result == "pass",
    )

    # ── DKIM auth results ─────────────────────────────────────────────────
    for dkim in rec.findall("auth_results/dkim"):
        row.dkim_auth.append(
            DkimAuth(
                domain=_text(dkim.find("domain")),
                result=_text(dkim.find("result")),
                selector=_text(dkim.find("selector")),
            )
        )

    # ── SPF auth results ──────────────────────────────────────────────────
    for spf in rec.findall("auth_results/spf"):
        row.spf_auth.append(
            SpfAuth(
                domain=_text(spf.find("domain")),
                result=_text(spf.find("result")),
                scope=_text(spf.find("scope")),
            )
        )

    return row
