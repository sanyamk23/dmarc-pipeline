"""Analysis engine — aggregates DMARC data into a comprehensive report.

Produces a structured analysis across every dimension: overall health,
per-domain breakdown, source IP reputation, authentication alignment,
sending services, recommendations, and a plain-English summary.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from models import DmarcRecord, DmarcReport, async_session


# ── Public API ─────────────────────────────────────────────────────────────────


async def get_analysis() -> dict[str, Any]:
    """Generate the full analysis report from current DB state."""
    async with async_session() as session:
        from sqlalchemy import select

        reports = (await session.execute(select(DmarcReport))).scalars().all()
        records = (await session.execute(select(DmarcRecord))).scalars().all()

        # Attach records to their reports for convenience
        records_by_report: dict[int, list[DmarcRecord]] = defaultdict(list)
        for rec in records:
            records_by_report[rec.report_id].append(rec)

        return _build_analysis(reports, records_by_report)


async def get_report_analysis(report_id: int) -> dict[str, Any]:
    """Generate analysis for a single report by ID."""
    async with async_session() as session:
        from sqlalchemy import select

        report = await session.get(DmarcReport, report_id)
        if report is None:
            return empty_analysis()

        records = (
            await session.execute(
                select(DmarcRecord).where(DmarcRecord.report_id == report_id)
            )
        ).scalars().all()

        return _build_analysis(report, records)


# ── Analysis builder ───────────────────────────────────────────────────────────


def _build_analysis(
    reports: DmarcReport | list[DmarcReport],
    records: list[DmarcRecord] | dict[int, list[DmarcRecord]],
) -> dict[str, Any]:
    """Compose the full analysis dict from loaded ORM objects.

    Accepts either a single report or a list, and records either as a flat list
    or a dict keyed by report_id. Normalizes to the internal list+dict shape.
    """
    # Normalize to list
    if isinstance(reports, DmarcReport):
        reports = [reports]
    # Normalize records to dict
    if isinstance(records, list):
        records_by_report: dict[int, list[DmarcRecord]] = defaultdict(list)
        for rec in records:
            records_by_report[rec.report_id].append(rec)
    else:
        records_by_report = records

    all_records: list[DmarcRecord] = []
    for recs in records_by_report.values():
        all_records.extend(recs)

    if not reports or not all_records:
        return empty_analysis()

    total_messages = sum(r.count for r in all_records)

    # ── Report-level summary ───────────────────────────────────────────────
    report_summaries = []
    for r in reports:
        recs = records_by_report.get(r.id, [])
        messages = sum(rec.count for rec in recs)
        passing = [rec for rec in recs if rec.dkim_aligned or rec.spf_aligned]
        failing = [rec for rec in recs if not rec.dkim_aligned and not rec.spf_aligned]
        report_summaries.append(
            {
                "id": r.id,
                "org_name": r.org_name,
                "domain": r.domain,
                "report_id": r.report_id,
                "date_begin": r.date_begin,
                "date_end": r.date_end,
                "policy_p": r.p,
                "policy_sp": r.sp,
                "total_messages": messages,
                "total_records": len(recs),
                "pass_count": len(passing),
                "fail_count": len(failing),
                "pass_rate": (len(passing) / len(recs) * 100) if recs else 0,
                "dkim_pass": sum(1 for rec in recs if rec.dkim_aligned),
                "spf_pass": sum(1 for rec in recs if rec.spf_aligned),
            }
        )

    # ── Per-domain analysis ────────────────────────────────────────────────
    per_domain: dict[str, dict] = defaultdict(
        lambda: {
            "records": 0,
            "messages": 0,
            "dkim_pass": 0,
            "dkim_fail": 0,
            "spf_pass": 0,
            "spf_fail": 0,
            "both_pass": 0,
            "both_fail": 0,
            "header_froms": set(),
            "source_ips": set(),
        }
    )
    for rec in all_records:
        domain = rec.header_from or "unknown"
        d = per_domain[domain]
        d["records"] += 1
        d["messages"] += rec.count or 0
        if rec.dkim_aligned:
            d["dkim_pass"] += 1
        else:
            d["dkim_fail"] += 1
        if rec.spf_aligned:
            d["spf_pass"] += 1
        else:
            d["spf_fail"] += 1
        if rec.dkim_aligned and rec.spf_aligned:
            d["both_pass"] += 1
        if not rec.dkim_aligned and not rec.spf_aligned:
            d["both_fail"] += 1
        if rec.header_from:
            d["header_froms"].add(rec.header_from)
        if rec.source_ip:
            d["source_ips"].add(rec.source_ip)

    domain_summaries = []
    for domain, d in per_domain.items():
        domain_summaries.append(
            {
                "domain": domain,
                "records": d["records"],
                "messages": d["messages"],
                "dkim_pass": d["dkim_pass"],
                "dkim_fail": d["dkim_fail"],
                "spf_pass": d["spf_pass"],
                "spf_fail": d["spf_fail"],
                "both_pass": d["both_pass"],
                "both_fail": d["both_fail"],
                "dkim_pass_rate": (
                    d["dkim_pass"] / d["records"] * 100 if d["records"] else 0
                ),
                "spf_pass_rate": (
                    d["spf_pass"] / d["records"] * 100 if d["records"] else 0
                ),
                "overall_pass_rate": (
                    (d["dkim_pass"] + d["spf_pass"])
                    / (2 * d["records"])
                    * 100
                    if d["records"]
                    else 0
                ),
                "header_froms": list(d["header_froms"]),
                "unique_ips": len(d["source_ips"]),
            }
        )

    # ── Source IP analysis ─────────────────────────────────────────────────
    per_ip: dict[str, dict] = defaultdict(
        lambda: {
            "messages": 0,
            "records": 0,
            "dkim_pass": 0,
            "spf_pass": 0,
            "dispositions": defaultdict(int),
            "header_froms": set(),
            "dkim_domains": set(),
            "spf_domains": set(),
        }
    )
    for rec in all_records:
        if not rec.source_ip:
            continue
        ip = per_ip[rec.source_ip]
        ip["messages"] += rec.count or 0
        ip["records"] += 1
        if rec.dkim_aligned:
            ip["dkim_pass"] += 1
        if rec.spf_aligned:
            ip["spf_pass"] += 1
        if rec.disposition:
            ip["dispositions"][rec.disposition] += 1
        if rec.header_from:
            ip["header_froms"].add(rec.header_from)
        if rec.dkim_domain:
            ip["dkim_domains"].add(rec.dkim_domain)
        if rec.spf_domain:
            ip["spf_domains"].add(rec.spf_domain)

    ip_rankings = []
    for ip, d in per_ip.items():
        ip_rankings.append(
            {
                "ip": ip,
                "messages": d["messages"],
                "records": d["records"],
                "dkim_pass": d["dkim_pass"],
                "spf_pass": d["spf_pass"],
                "dkim_pass_rate": (
                    d["dkim_pass"] / d["records"] * 100 if d["records"] else 0
                ),
                "spf_pass_rate": (
                    d["spf_pass"] / d["records"] * 100 if d["records"] else 0
                ),
                "dispositions": dict(d["dispositions"]),
                "header_froms": list(d["header_froms"]),
                "dkim_domains": list(d["dkim_domains"]),
                "spf_domains": list(d["spf_domains"]),
            }
        )
    ip_rankings.sort(key=lambda x: x["messages"], reverse=True)

    # ── Authentication alignment summary ───────────────────────────────────
    dkim_pass = sum(1 for r in all_records if r.dkim_aligned)
    dkim_fail = len(all_records) - dkim_pass
    spf_pass = sum(1 for r in all_records if r.spf_aligned)
    spf_fail = len(all_records) - spf_pass
    both_pass = sum(1 for r in all_records if r.dkim_aligned and r.spf_aligned)
    both_fail = sum(
        1 for r in all_records if not r.dkim_aligned and not r.spf_aligned
    )
    either_pass = sum(
        1 for r in all_records if r.dkim_aligned or r.spf_aligned
    )

    # ── Disposition breakdown ──────────────────────────────────────────────
    dispositions: dict[str, int] = defaultdict(int)
    for rec in all_records:
        dispositions[rec.disposition or "unknown"] += rec.count or 0

    # ── DKIM selector usage ────────────────────────────────────────────────
    selectors: dict[str, int] = defaultdict(int)
    # Pull from raw XML for selector data not stored in records
    for rec in all_records:
        if rec.dkim_domain == rec.header_from:
            selectors[rec.dkim_domain] += 1

    # ── Sending services (identify by IP ranges) ──────────────────────────
    sending_services = _identify_services(per_ip)

    # ── Recommendations ────────────────────────────────────────────────────
    recommendations = _generate_recommendations(
        all_records, domain_summaries, ip_rankings, both_fail, total_messages
    )

    # ── Overall score ──────────────────────────────────────────────────────
    health_score = _compute_health_score(all_records)

    return {
        "generated_at": datetime.utcnow(),
        "overall": {
            "total_reports": len(reports),
            "total_records": len(all_records),
            "total_messages": total_messages,
            "unique_domains": len(per_domain),
            "unique_ips": len(per_ip),
            "health_score": health_score,
            "health_label": _health_label(health_score),
        },
        "alignment": {
            "dkim_pass": dkim_pass,
            "dkim_fail": dkim_fail,
            "dkim_pass_rate": (
                dkim_pass / len(all_records) * 100 if all_records else 0
            ),
            "spf_pass": spf_pass,
            "spf_fail": spf_fail,
            "spf_pass_rate": (
                spf_pass / len(all_records) * 100 if all_records else 0
            ),
            "both_pass": both_pass,
            "both_fail": both_fail,
            "either_pass": either_pass,
            "overall_pass_rate": (
                either_pass / len(all_records) * 100 if all_records else 0
            ),
        },
        "dispositions": dict(dispositions),
        "reports": report_summaries,
        "domains": domain_summaries,
        "top_ips": ip_rankings[:20],
        "sending_services": sending_services,
        "recommendations": recommendations,
        "summary_text": _write_summary(
            health_score, domain_summaries, all_records, both_fail
        ),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────


def empty_analysis() -> dict[str, Any]:
    """Placeholder analysis when no data is available."""
    return {
        "generated_at": datetime.utcnow(),
        "overall": {
            "total_reports": 0,
            "total_records": 0,
            "total_messages": 0,
            "unique_domains": 0,
            "unique_ips": 0,
            "health_score": 0,
            "health_label": "no data",
        },
        "alignment": {},
        "dispositions": {},
        "reports": [],
        "domains": [],
        "top_ips": [],
        "sending_services": [],
        "recommendations": [],
        "summary_text": "No DMARC reports ingested yet.",
    }


def _identify_services(per_ip: dict[str, dict]) -> list[dict]:
    """Heuristically group source IPs into sending services."""
    # Known service IP ranges (simplified — production would use ASN lookups)
    service_hints = {
        "google": ["google", "gmail"],
        "microsoft": ["outlook", "microsoft", "hotmail"],
        "amazon": ["amazon", "ses"],
    }

    services: dict[str, dict] = defaultdict(
        lambda: {"messages": 0, "ips": set(), "dkim_pass": 0, "spf_pass": 0}
    )

    for ip, d in per_ip.items():
        matched = "other"
        ip_lower = ip.lower()
        for service, hints in service_hints.items():
            if any(h in ip_lower for h in hints):
                matched = service
                break
        # Heuristic: known Google/Microsoft ranges
        if ip.startswith("209.85.") or ip.startswith("108.177."):
            matched = "google"
        elif ip.startswith("2607:f8b0"):
            matched = "google/ipv6"
        elif ip.startswith("2a00:1450"):
            matched = "google/ipv6"

        s = services[matched]
        s["messages"] += d["messages"]
        s["ips"].add(ip)
        s["dkim_pass"] += d["dkim_pass"]
        s["spf_pass"] += d["spf_pass"]

    result = []
    for name, s in services.items():
        total = len(s["ips"])
        result.append(
            {
                "service": name,
                "messages": s["messages"],
                "ip_count": len(s["ips"]),
                "ips": list(s["ips"]),
            }
        )
    result.sort(key=lambda x: x["messages"], reverse=True)
    return result


def _generate_recommendations(
    records: list[DmarcRecord],
    domains: list[dict],
    ips: list[dict],
    both_fail: int,
    total_messages: int,
) -> list[dict]:
    """Produce actionable recommendations based on the data."""
    recs: list[dict] = []

    # High failure rate
    fail_rate = (both_fail / len(records) * 100) if records else 0
    if fail_rate > 10:
        recs.append(
            {
                "severity": "critical",
                "title": f"{fail_rate:.1f}% of sources fail both DKIM and spf",
                "detail": "These emails may be rejected by receivers with strict DMARC policies. Investigate the failing source IPs.",
                "action": "Review the 'Failed Sources' section and authenticate these senders.",
            }
        )
    elif fail_rate > 0:
        recs.append(
            {
                "severity": "warning",
                "title": f"{fail_rate:.1f}% of sources fail both checks",
                "detail": "Small number of failures detected. Monitor for growth.",
                "action": "Review failing sources in the report.",
            }
        )
    else:
        recs.append(
            {
                "severity": "success",
                "title": "No dual-failure sources detected",
                "detail": "Every source passes at least one authentication check.",
                "action": "Maintain current configuration.",
            }
        )

    # SPF-only failures (DKIM passes)
    spf_fail_only = sum(
        1 for r in records if r.dkim_aligned and not r.spf_aligned
    )
    if spf_fail_only > 0:
        recs.append(
            {
                "severity": "info",
                "title": f"{spf_fail_only} source(s) pass DKIM but fail SPF",
                "detail": "Common with mail forwarding. SPF breaks when mail is forwarded, but DKIM survives.",
                "action": "If these are trusted forwarders, no action needed. Otherwise add their IPs to your SPF record.",
            }
        )

    # Strict policy recommendation
    if fail_rate == 0 and len(records) > 0:
        recs.append(
            {
                "severity": "info",
                "title": "Consider upgrading DMARC policy to quarantine/reject",
                "detail": "Your domain currently uses p=none (monitoring). With clean alignment, you can safely enforce.",
                "action": "Update your DMARC record: v=DMARC1; p=quarantine; (or p=reject once confident).",
            }
        )

    return recs


def _compute_health_score(records: list[DmarcRecord]) -> int:
    """Compute a 0-100 health score based on alignment rates."""
    if not records:
        return 0
    dkim_rate = sum(1 for r in records if r.dkim_aligned) / len(records)
    spf_rate = sum(1 for r in records if r.spf_aligned) / len(records)
    either_rate = sum(
        1 for r in records if r.dkim_aligned or r.spf_aligned
    ) / len(records)
    # Weighted: either-pass matters most (DMARC passes if EITHER passes)
    score = int((either_rate * 0.7 + dkim_rate * 0.15 + spf_rate * 0.15) * 100)
    return min(100, max(0, score))


def _health_label(score: int) -> str:
    if score >= 90:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 50:
        return "fair"
    if score >= 25:
        return "poor"
    return "critical"


def _write_summary(
    score: int,
    domains: list[dict],
    records: list[DmarcRecord],
    both_fail: int,
) -> str:
    """Write a one-paragraph plain-English summary."""
    domain_names = ", ".join(d["domain"] for d in domains[:3])
    total = len(records)
    return (
        f"Across {total} evaluated sources, your domain{'s' if len(domains) > 1 else ''} "
        f"{domain_names} {'have' if len(domains) > 1 else 'has'} a health score of {score}/100. "
        f"{'All sources pass at least one authentication check.' if both_fail == 0 else f'{both_fail} source(s) fail both DKIM and SPF.'} "
        f"DKIM alignment is {'strong' if score > 70 else 'moderate'}; "
        f"SPF alignment is {'strong' if score > 70 else 'needs attention'}."
    )


# Alias for backward compat
generate_analysis = get_analysis
