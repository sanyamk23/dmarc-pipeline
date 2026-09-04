"""Analysis engine — aggregates DMARC data into a comprehensive report.

Accepts plain dicts (from Supabase REST API) rather than SQLAlchemy models,
so it works with any data source.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any


# ── Public API ─────────────────────────────────────────────────────────────────


def build_analysis_from_dicts(
    reports: list[dict],
    records_by_report: dict[int, list[dict]],
) -> dict[str, Any]:
    """Build full analysis from report and record dicts."""
    all_records: list[dict] = []
    for recs in records_by_report.values():
        all_records.extend(recs)

    if not reports or not all_records:
        return _empty_analysis()

    total_messages = sum(r.get("count", 0) or 0 for r in all_records)

    # ── Report-level summary ───────────────────────────────────────────────
    report_summaries = []
    for r in reports:
        recs = records_by_report.get(r.get("id", 0), [])
        passing = [rec for rec in recs if rec.get("dkim_aligned") or rec.get("spf_aligned")]
        failing = [rec for rec in recs if not rec.get("dkim_aligned") and not rec.get("spf_aligned")]
        report_summaries.append({
            "id": r.get("id"),
            "org_name": r.get("org_name"),
            "domain": r.get("domain"),
            "report_id": r.get("report_id"),
            "date_begin": r.get("date_begin"),
            "date_end": r.get("date_end"),
            "policy_p": r.get("p"),
            "policy_sp": r.get("sp"),
            "total_messages": sum(rec.get("count", 0) or 0 for rec in recs),
            "total_records": len(recs),
            "pass_count": len(passing),
            "fail_count": len(failing),
            "pass_rate": (len(passing) / len(recs) * 100) if recs else 0,
            "dkim_pass": sum(1 for rec in recs if rec.get("dkim_aligned")),
            "spf_pass": sum(1 for rec in recs if rec.get("spf_aligned")),
        })

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
        domain = rec.get("header_from") or "unknown"
        d = per_domain[domain]
        d["records"] += 1
        d["messages"] += rec.get("count", 0) or 0
        if rec.get("dkim_aligned"):
            d["dkim_pass"] += 1
        else:
            d["dkim_fail"] += 1
        if rec.get("spf_aligned"):
            d["spf_pass"] += 1
        else:
            d["spf_fail"] += 1
        if rec.get("dkim_aligned") and rec.get("spf_aligned"):
            d["both_pass"] += 1
        if not rec.get("dkim_aligned") and not rec.get("spf_aligned"):
            d["both_fail"] += 1
        if rec.get("header_from"):
            d["header_froms"].add(rec["header_from"])
        if rec.get("source_ip"):
            d["source_ips"].add(rec["source_ip"])

    domain_summaries = []
    for domain, d in per_domain.items():
        domain_summaries.append({
            "domain": domain,
            "records": d["records"],
            "messages": d["messages"],
            "dkim_pass": d["dkim_pass"],
            "dkim_fail": d["dkim_fail"],
            "spf_pass": d["spf_pass"],
            "spf_fail": d["spf_fail"],
            "both_pass": d["both_pass"],
            "both_fail": d["both_fail"],
            "dkim_pass_rate": d["dkim_pass"] / d["records"] * 100 if d["records"] else 0,
            "spf_pass_rate": d["spf_pass"] / d["records"] * 100 if d["records"] else 0,
            "overall_pass_rate": (
                (d["dkim_pass"] + d["spf_pass"]) / (2 * d["records"]) * 100
                if d["records"]
                else 0
            ),
            "header_froms": list(d["header_froms"]),
            "unique_ips": len(d["source_ips"]),
        })

    # ── Source IP analysis ─────────────────────────────────────────────────
    per_ip: dict[str, dict] = defaultdict(
        lambda: {
            "messages": 0,
            "records": 0,
            "dkim_pass": 0,
            "spf_pass": 0,
            "dispositions": defaultdict(int),
            "header_froms": set(),
        }
    )
    for rec in all_records:
        ip = rec.get("source_ip")
        if not ip:
            continue
        ip_data = per_ip[ip]
        ip_data["messages"] += rec.get("count", 0) or 0
        ip_data["records"] += 1
        if rec.get("dkim_aligned"):
            ip_data["dkim_pass"] += 1
        if rec.get("spf_aligned"):
            ip_data["spf_pass"] += 1
        disp = rec.get("disposition") or "unknown"
        ip_data["dispositions"][disp] += 1
        if rec.get("header_from"):
            ip_data["header_froms"].add(rec["header_from"])

    ip_rankings = []
    for ip, d in per_ip.items():
        ip_rankings.append({
            "ip": ip,
            "messages": d["messages"],
            "records": d["records"],
            "dkim_pass": d["dkim_pass"],
            "spf_pass": d["spf_pass"],
            "dkim_pass_rate": d["dkim_pass"] / d["records"] * 100 if d["records"] else 0,
            "spf_pass_rate": d["spf_pass"] / d["records"] * 100 if d["records"] else 0,
            "dispositions": dict(d["dispositions"]),
            "header_froms": list(d["header_froms"]),
        })
    ip_rankings.sort(key=lambda x: x["messages"], reverse=True)

    # ── Authentication summary ──────────────────────────────────────────────
    dkim_pass = sum(1 for r in all_records if r.get("dkim_aligned"))
    dkim_fail = len(all_records) - dkim_pass
    spf_pass = sum(1 for r in all_records if r.get("spf_aligned"))
    spf_fail = len(all_records) - spf_pass
    both_pass = sum(
        1 for r in all_records if r.get("dkim_aligned") and r.get("spf_aligned")
    )
    both_fail = sum(
        1 for r in all_records if not r.get("dkim_aligned") and not r.get("spf_aligned")
    )
    either_pass = sum(
        1 for r in all_records if r.get("dkim_aligned") or r.get("spf_aligned")
    )

    # ── Recommendations ────────────────────────────────────────────────────
    recommendations = _generate_recommendations(both_fail, len(all_records))

    # ── Health score ───────────────────────────────────────────────────────
    health_score = _compute_health_score(all_records)

    return {
        "generated_at": datetime.utcnow().isoformat(),
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
            "dkim_pass_rate": dkim_pass / len(all_records) * 100 if all_records else 0,
            "spf_pass": spf_pass,
            "spf_fail": spf_fail,
            "spf_pass_rate": spf_pass / len(all_records) * 100 if all_records else 0,
            "both_pass": both_pass,
            "both_fail": both_fail,
            "either_pass": either_pass,
            "overall_pass_rate": either_pass / len(all_records) * 100 if all_records else 0,
        },
        "reports": report_summaries,
        "domains": domain_summaries,
        "top_ips": ip_rankings[:20],
        "recommendations": recommendations,
    }


def _empty_analysis() -> dict[str, Any]:
    """Placeholder analysis when no data is available."""
    return {
        "generated_at": datetime.utcnow().isoformat(),
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
        "reports": [],
        "domains": [],
        "top_ips": [],
        "recommendations": [],
    }


def _generate_recommendations(both_fail: int, total: int) -> list[dict]:
    """Produce actionable recommendations based on the data."""
    recs: list[dict] = []
    fail_rate = (both_fail / total * 100) if total else 0

    if fail_rate > 10:
        recs.append({
            "severity": "critical",
            "title": f"{fail_rate:.1f}% of sources fail both DKIM and SPF",
            "detail": "These emails may be rejected by strict receivers.",
            "action": "Review failing source IPs and authenticate them.",
        })
    elif fail_rate > 0:
        recs.append({
            "severity": "warning",
            "title": f"{fail_rate:.1f}% of sources fail both checks",
            "detail": "Small number of failures detected.",
            "action": "Monitor failing sources.",
        })
    else:
        recs.append({
            "severity": "success",
            "title": "No dual-failure sources detected",
            "detail": "Every source passes at least one check.",
            "action": "Maintain current configuration.",
        })

    if fail_rate == 0 and total > 0:
        recs.append({
            "severity": "info",
            "title": "Consider upgrading DMARC policy to quarantine/reject",
            "detail": "Your domain uses p=none. With clean alignment, you can enforce.",
            "action": "Update DMARC record: v=DMARC1; p=quarantine;",
        })

    return recs


def _compute_health_score(records: list[dict]) -> int:
    """Compute a 0-100 health score based on alignment rates."""
    if not records:
        return 0
    either_rate = sum(
        1 for r in records if r.get("dkim_aligned") or r.get("spf_aligned")
    ) / len(records)
    return int(either_rate * 100)


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
