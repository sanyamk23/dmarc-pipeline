"""FastAPI application — DMARC report API + dashboard.

Run with::

    python -m api.main
    # or
    uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections import defaultdict
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from starlette.requests import Request

from models import (
    Base,
    DmarcRecord,
    DmarcReport,
    RecordRow,
    ReportMetadata,
    StatsSummary,
    async_session,
    engine,
    init_db,
)
from parsers.dmarc_xml import parse_dmarc_xml
from analysis.engine import get_analysis, get_report_analysis, _build_analysis
from workers.processor import process_file, process_existing_files
from config import settings

logger = logging.getLogger("dmarc.api")

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# Use configured reports directory (defaults to ./reports)
REPORT_DROP_DIR = settings.reports_dir
QUARANTINE_DIR = settings.quarantine_dir

STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)
REPORT_DROP_DIR.mkdir(exist_ok=True)
QUARANTINE_DIR.mkdir(exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ── App lifecycle ──────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await engine.dispose()


app = FastAPI(
    title="DMARC Report Pipeline",
    description="Ingest, store, and browse DMARC aggregate reports.",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Health check ──────────────────────────────────────────────────────────────


@app.get("/health", include_in_schema=False)
async def health() -> dict:
    """Liveness probe for orchestrators (Render, k8s, etc.)."""
    return {"status": "ok", "version": "1.0.0"}


# ── Dependencies ──────────────────────────────────────────────────────────────


async def get_session():
    async with async_session() as session:
        yield session


# ── Dashboard ─────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


# ── Upload endpoint ───────────────────────────────────────────────────────────


@app.post("/api/upload", status_code=201)
async def upload_report(file: UploadFile = File(...)):
    """Upload a DMARC ``.zip`` / ``.xml`` / ``.xml.gz`` report.

    Returns the list of extracted files plus per-file and collective analysis.
    """
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    drop_dir = REPORT_DROP_DIR
    drop_dir.mkdir(exist_ok=True)
    target = drop_dir / file.filename
    target.write_bytes(data)

    result = await process_file(target)
    if result is None:
        return {"status": "error", "filename": file.filename}

    if result.is_duplicate:
        return {
            "status": "duplicate",
            "filename": file.filename,
            "extracted_files": result.extracted_files,
            "skipped": result.skipped,
        }

    # Build per-file analysis for each ingested report
    per_file_analysis = []
    for report in result.reports:
        analysis = await get_report_analysis(report.id)
        per_file_analysis.append({
            "report_id": report.id,
            "xml_filename": report.xml_filename,
            "org_name": report.org_name,
            "domain": report.domain,
            "date_begin": report.date_begin,
            "date_end": report.date_end,
            "analysis": analysis,
        })

    # Build collective analysis across all newly-ingested reports
    all_new_ids = [r.id for r in result.reports]
    records_by_report: dict[int, list] = {}
    async with async_session() as session:
        from sqlalchemy import select
        for rid in all_new_ids:
            recs = (
                await session.execute(
                    select(DmarcRecord).where(DmarcRecord.report_id == rid)
                )
            ).scalars().all()
            records_by_report[rid] = recs

    collective = _build_analysis(result.reports, records_by_report)

    return {
        "status": "ingested",
        "filename": file.filename,
        "extracted_files": result.extracted_files,
        "failed_files": result.failed,
        "skipped_duplicates": result.skipped,
        "per_file_analysis": per_file_analysis,
        "collective_analysis": collective,
    }


# ── Reports endpoints ─────────────────────────────────────────────────────────


@app.get("/api/reports", response_model=list[ReportMetadata])
async def list_reports(
    domain: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List report envelopes with pass/fail counts."""
    async with async_session() as session:
        stmt = select(DmarcReport)
        if domain:
            stmt = stmt.where(DmarcReport.domain == domain)
        stmt = stmt.order_by(DmarcReport.date_end.desc()).limit(limit).offset(offset)
        rows = (await session.execute(stmt)).scalars().all()

        result: list[ReportMetadata] = []
        for r in rows:
            records = (
                await session.execute(
                    select(DmarcRecord).where(DmarcRecord.report_id == r.id)
                )
            ).scalars().all()
            pass_count = sum(1 for rec in records if rec.dkim_aligned or rec.spf_aligned)
            fail_count = len(records) - pass_count
            result.append(
                ReportMetadata(
                    id=r.id,
                    xml_filename=r.xml_filename,
                    org_name=r.org_name,
                    report_id=r.report_id,
                    date_begin=r.date_begin,
                    date_end=r.date_end,
                    domain=r.domain,
                    adkim=r.adkim,
                    aspf=r.aspf,
                    p=r.p,
                    sp=r.sp,
                    pct=r.pct,
                    record_count=len(records),
                    pass_count=pass_count,
                    fail_count=fail_count,
                    created_at=r.created_at,
                )
            )
        return result


@app.get("/api/reports/{report_id}", response_model=ReportMetadata)
async def get_report(report_id: int):
    async with async_session() as session:
        row = await session.get(DmarcReport, report_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Report not found")

        records = (
            await session.execute(
                select(DmarcRecord).where(DmarcRecord.report_id == report_id)
            )
        ).scalars().all()
        pass_count = sum(1 for rec in records if rec.dkim_aligned or rec.spf_aligned)

        return ReportMetadata(
            id=row.id,
            xml_filename=row.xml_filename,
            org_name=row.org_name,
            report_id=row.report_id,
            date_begin=row.date_begin,
            date_end=row.date_end,
            domain=row.domain,
            adkim=row.adkim,
            aspf=row.aspf,
            p=row.p,
            sp=row.sp,
            pct=row.pct,
            record_count=len(records),
            pass_count=pass_count,
            fail_count=len(records) - pass_count,
            created_at=row.created_at,
        )


@app.get("/api/reports/{report_id}/detail")
async def get_report_detail(report_id: int):
    """Full detail for a single report — every field, every record, every auth result."""
    import json

    async with async_session() as session:
        row = await session.get(DmarcReport, report_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Report not found")

        records = (
            await session.execute(
                select(DmarcRecord).where(DmarcRecord.report_id == report_id)
            )
        ).scalars().all()

        analysis = await get_report_analysis(report_id)

        return {
            "report": {
                "id": row.id,
                "xml_filename": row.xml_filename,
                "archive_filename": row.archive_filename,
                "org_name": row.org_name,
                "org_email": row.org_email,
                "report_id": row.report_id,
                "date_begin": row.date_begin,
                "date_end": row.date_end,
                "domain": row.domain,
                "adkim": row.adkim,
                "aspf": row.aspf,
                "p": row.p,
                "sp": row.sp,
                "pct": row.pct,
                "created_at": row.created_at,
            },
            "records": [
                {
                    "id": rec.id,
                    "source_ip": rec.source_ip,
                    "count": rec.count,
                    "header_from": rec.header_from,
                    "envelope_from": rec.envelope_from,
                    "envelope_to": rec.envelope_to,
                    "disposition": rec.disposition,
                    "dkim_aligned": rec.dkim_aligned,
                    "spf_aligned": rec.spf_aligned,
                    "dkim_result": rec.dkim_result,
                    "spf_result": rec.spf_result,
                    "dkim_domain": rec.dkim_domain,
                    "spf_domain": rec.spf_domain,
                    "dkim_auth": json.loads(rec.dkim_auth_json) if rec.dkim_auth_json else [],
                    "spf_auth": json.loads(rec.spf_auth_json) if rec.spf_auth_json else [],
                }
                for rec in records
            ],
            "analysis": analysis,
        }


# ── Records endpoints ─────────────────────────────────────────────────────────


@app.get("/api/reports/{report_id}/records", response_model=list[RecordRow])
async def list_records(
    report_id: int,
    source_ip: str | None = None,
    header_from: str | None = None,
    result: str | None = Query(None, description="Filter: pass or fail"),
    limit: int = Query(200, ge=1, le=2000),
):
    async with async_session() as session:
        stmt = select(DmarcRecord).where(DmarcRecord.report_id == report_id)
        if source_ip:
            stmt = stmt.where(DmarcRecord.source_ip == source_ip)
        if header_from:
            stmt = stmt.where(DmarcRecord.header_from == header_from)
        if result == "pass":
            stmt = stmt.where(
                (DmarcRecord.dkim_aligned == True) | (DmarcRecord.spf_aligned == True)  # noqa: E712
            )
        elif result == "fail":
            stmt = stmt.where(
                (DmarcRecord.dkim_aligned == False) & (DmarcRecord.spf_aligned == False)  # noqa: E712
            )
        stmt = stmt.limit(limit)
        rows = (await session.execute(stmt)).scalars().all()
        return [RecordRow.model_validate(r) for r in rows]


# ── Statistics ────────────────────────────────────────────────────────────────


@app.get("/api/stats", response_model=StatsSummary)
async def stats(domain: str | None = None):
    async with async_session() as session:
        report_stmt = select(func.count(DmarcReport.id))
        record_stmt = select(
            func.count(DmarcRecord.id), func.coalesce(func.sum(DmarcRecord.count), 0)
        )
        if domain:
            # Join records → reports to filter by domain
            record_stmt = record_stmt.join(DmarcReport).where(
                DmarcReport.domain == domain
            )
            report_stmt = report_stmt.where(DmarcReport.domain == domain)

        total_reports = (await session.execute(report_stmt)).scalar_one()
        total_records, total_messages = (await session.execute(record_stmt)).one()

        # Pass/fail counts
        pass_stmt = select(func.count(DmarcRecord.id)).where(
            (DmarcRecord.dkim_aligned == True) | (DmarcRecord.spf_aligned == True)  # noqa: E712
        )
        fail_stmt = select(func.count(DmarcRecord.id)).where(
            (DmarcRecord.dkim_aligned == False) & (DmarcRecord.spf_aligned == False)  # noqa: E712
        )
        dkim_pass = await session.execute(
            select(func.count(DmarcRecord.id)).where(DmarcRecord.dkim_aligned == True)  # noqa: E712
        )
        spf_pass = await session.execute(
            select(func.count(DmarcRecord.id)).where(DmarcRecord.spf_aligned == True)  # noqa: E712
        )

        pass_count = (await session.execute(pass_stmt)).scalar_one()
        fail_count = (await session.execute(fail_stmt)).scalar_one()
        dkim_pass_count = dkim_pass.scalar_one()
        spf_pass_count = spf_pass.scalar_one()

        # Top source IPs
        top_ips = await session.execute(
            select(DmarcRecord.source_ip, func.sum(DmarcRecord.count).label("total"))
            .group_by(DmarcRecord.source_ip)
            .order_by(func.sum(DmarcRecord.count).desc())
            .limit(10)
        )
        top_source_ips = [
            {"ip": ip, "count": int(count)} for ip, count in top_ips.all() if ip
        ]

        # Top header_from domains
        top_from = await session.execute(
            select(DmarcRecord.header_from, func.sum(DmarcRecord.count).label("total"))
            .group_by(DmarcRecord.header_from)
            .order_by(func.sum(DmarcRecord.count).desc())
            .limit(10)
        )
        top_header_froms = [
            {"domain": d, "count": int(c)} for d, c in top_from.all() if d
        ]

        # Per-domain pass rates
        per_domain = await session.execute(
            select(
                DmarcReport.domain,
                func.count(DmarcRecord.id),
                func.coalesce(func.sum(DmarcRecord.count), 0),
            )
            .join(DmarcRecord, DmarcRecord.report_id == DmarcReport.id)
            .group_by(DmarcReport.domain)
        )
        per_domain_data = [
            {"domain": d, "records": int(r), "messages": int(m)}
            for d, r, m in per_domain.all()
            if d
        ]

        return StatsSummary(
            total_reports=total_reports,
            total_records=total_records,
            total_messages=int(total_messages),
            pass_count=pass_count,
            fail_count=fail_count,
            dkim_pass=dkim_pass_count,
            dkim_fail=total_records - dkim_pass_count,
            spf_pass=spf_pass_count,
            spf_fail=total_records - spf_pass_count,
            top_source_ips=top_source_ips,
            top_header_froms=top_header_froms,
            per_domain=per_domain_data,
        )


# ── Analysis endpoint ─────────────────────────────────────────────────────────


@app.get("/api/analysis")
async def analysis():
    """Full analysis report across all ingested DMARC data."""
    return await get_analysis()


# ── Analysis page ─────────────────────────────────────────────────────────────


@app.get("/analysis", response_class=HTMLResponse, include_in_schema=False)
async def analysis_page(request: Request):
    return templates.TemplateResponse("analysis.html", {"request": request})


# ── File detail page ──────────────────────────────────────────────────────────


@app.get("/file/{report_id}", response_class=HTMLResponse, include_in_schema=False)
async def file_detail_page(report_id: int, request: Request):
    return templates.TemplateResponse("file_detail.html", {"request": request})
