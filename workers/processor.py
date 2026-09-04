"""File ingestion worker — unzips DMARC reports and persists parsed data.

This is the "pipeline" entry point: feed it a ``.zip``/``.xml``/``.xml.gz``
file and it extracts the XML, parses it with :mod:`parsers.dmarc_xml`, and
writes the report metadata + records into SQLite via SQLAlchemy.

Idempotency is enforced on ``report_id`` (from the XML envelope) — re-running
on the same file is a safe no-op rather than a duplicate.
"""

from __future__ import annotations

import asyncio
import logging
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import aiofiles

from models import DmarcRecord, DmarcReport, async_session
from parsers.dmarc_xml import DmarcReport as ParsedReport, parse_dmarc_xml

logger = logging.getLogger("dmarc.processor")


# ── Helpers ───────────────────────────────────────────────────────────────────

import json as _json


def _pick_dkim_domain(dkim_auth: list, reported_domain: str | None) -> str | None:
    """Choose the DKIM domain that best represents this record.

    Google (and others) may report multiple DKIM signatures. We prefer the one
    matching the reported domain; fall back to the first entry otherwise.
    """
    if not dkim_auth:
        return None
    if reported_domain:
        for dkim in dkim_auth:
            if dkim.domain == reported_domain:
                return dkim.domain
    return dkim_auth[0].domain


# ── Public API ────────────────────────────────────────────────────────────────


@dataclass
class IngestResult:
    """Detailed result of ingesting one upload (zip / xml / xml.gz)."""
    archive_name: str
    extracted_files: list[str] = field(default_factory=list)
    reports: list[DmarcReport] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # duplicate report_ids
    failed: list[str] = field(default_factory=list)  # unparseable xml names

    @property
    def is_duplicate(self) -> bool:
        return not self.reports and not self.failed and bool(self.skipped)


async def process_file(path: Path) -> IngestResult | None:
    """Ingest a single DMARC report file.

    Supported input:
        * ``.zip`` containing one or more XML files
        * ``.xml`` plain
        * ``.xml.gz`` gzip-compressed

    Returns an :class:`IngestResult` with extracted filenames and persisted rows,
    or ``None`` if the file could not be read at all.
    """
    path = Path(path)
    if not path.exists():
        logger.warning("File not found: %s", path)
        return None

    logger.info("Processing: %s", path.name)
    result = IngestResult(archive_name=path.name)

    # Collect all (xml_bytes, xml_name) pairs from this file
    try:
        xml_entries = await _extract_all_xml(path)
    except Exception as exc:
        logger.error("Failed to extract XML from %s: %s", path.name, exc)
        _quarantine(path)
        result.failed.append(path.name)
        return result

    for xml_bytes, xml_name in xml_entries:
        result.extracted_files.append(xml_name)
        try:
            parsed: ParsedReport = parse_dmarc_xml(xml_name, xml_bytes)
        except ValueError as exc:
            logger.error("Failed to parse %s: %s", xml_name, exc)
            result.failed.append(xml_name)
            continue
        row = await _persist(
            path.name, xml_name, xml_bytes.decode("utf-8", errors="replace"), parsed
        )
        if row is not None:
            result.reports.append(row)
        else:
            result.skipped.append(parsed.metadata.report_id or xml_name)

    return result


async def process_existing_files(directory: Path) -> int:
    """Process every supported file in a directory (batch/initial load)."""
    directory = Path(directory)
    count = 0
    for ext in ("*.zip", "*.xml", "*.xml.gz"):
        for path in sorted(directory.glob(ext)):
            result = await process_file(path)
            if result is not None and (result.reports or result.failed):
                count += len(result.reports)
    return count


# ── Internals ─────────────────────────────────────────────────────────────────


async def _extract_all_xml(path: Path) -> list[tuple[bytes, str]]:
    """Return a list of ``(xml_bytes, original_xml_filename)`` from any supported
    input. A zip may contain multiple XML files — all are returned."""
    suffix = path.suffix.lower()

    if suffix == ".zip":
        return await _extract_all_from_zip(path)

    if suffix == ".gz":
        async with aiofiles.open(path, "rb") as fh:
            data = await fh.read()
        return [(data, path.name)]

    # Plain XML
    async with aiofiles.open(path, "rb") as fh:
        data = await fh.read()
    return [(data, path.name)]


async def _extract_all_from_zip(path: Path) -> list[tuple[bytes, str]]:
    """Extract all XML members from a zip archive."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync_extract_all_xml, path)


def _sync_extract_all_xml(path: Path) -> list[tuple[bytes, str]]:
    """Synchronous zip extraction (CPU/IO bound, run in thread)."""
    with zipfile.ZipFile(path, "r") as zf:
        xml_members = [n for n in zf.namelist() if n.lower().endswith(".xml")]
        if not xml_members:
            raise ValueError(f"No XML files found in zip: {path.name}")
        return [(zf.read(m), Path(m).name) for m in xml_members]


async def _persist(
    archive_name: str, xml_name: str, raw_xml: str, parsed: ParsedReport
) -> DmarcReport | None:
    """Persist a parsed report, idempotent on report_id."""
    policy = parsed.metadata.policy
    report_id = parsed.metadata.report_id

    async with async_session() as session:
        from sqlalchemy import select

        # Idempotency guard — skip if we've already ingested this report_id
        if report_id:
            existing = await session.execute(
                select(DmarcReport).where(DmarcReport.report_id == report_id)
            )
            if existing.scalar_one_or_none() is not None:
                logger.info("Skipping duplicate report_id=%s", report_id)
                return None

        # Resolve domain: prefer the published policy domain, fall back to header_from
        domain = policy.domain
        if not domain and parsed.records:
            domain = parsed.records[0].header_from

        row = DmarcReport(
            xml_filename=xml_name,
            archive_filename=archive_name,
            org_name=parsed.metadata.org_name,
            org_email=parsed.metadata.org_email,
            report_id=report_id,
            date_begin=parsed.metadata.date_begin,
            date_end=parsed.metadata.date_end,
            domain=domain,
            adkim=policy.adkim,
            aspf=policy.aspf,
            p=policy.p,
            sp=policy.sp,
            pct=policy.pct,
            raw_xml=raw_xml,
        )
        session.add(row)
        await session.flush()  # populate row.id

        # Bulk-insert records for this report
        orm_records = [
            DmarcRecord(
                report_id=row.id,
                source_ip=r.source_ip,
                count=r.count or 0,
                header_from=r.header_from,
                envelope_from=r.envelope_from,
                envelope_to=r.envelope_to,
                disposition=r.disposition,
                dkim_aligned=r.dkim_aligned,
                spf_aligned=r.spf_aligned,
                dkim_result=r.dkim_result,
                spf_result=r.spf_result,
                dkim_domain=_pick_dkim_domain(r.dkim_auth, domain),
                spf_domain=r.spf_auth[0].domain if r.spf_auth else None,
                dkim_auth_json=_json.dumps([
                    {"domain": d.domain, "result": d.result, "selector": d.selector}
                    for d in r.dkim_auth
                ]),
                spf_auth_json=_json.dumps([
                    {"domain": s.domain, "result": s.result, "scope": s.scope}
                    for s in r.spf_auth
                ]),
            )
            for r in parsed.records
        ]
        session.add_all(orm_records)
        await session.commit()

        logger.info(
            "Stored report_id=%s with %d records", report_id, len(orm_records)
        )
        return row


def _quarantine(path: Path) -> None:
    """Move an unprocessable file aside so it doesn't block future runs."""
    from config import settings

    quarantine_dir = settings.quarantine_dir
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    target = quarantine_dir / path.name
    path.rename(target)
    logger.warning("Quarantined unprocessable file → %s", target)
