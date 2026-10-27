from __future__ import annotations

from pathlib import Path
from typing import Any

from gateway_harness.catalog import load_catalog
from gateway_harness.funnel.cluster import build_clusters
from gateway_harness.funnel.gate import gate
from gateway_harness.funnel.value import score
from gateway_harness.ledger.store import LedgerStore
from gateway_harness.settings import Settings, get_settings


def generate_savings_report(
    store: LedgerStore,
    catalog_path: Path | str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Convenience wrapper for report generation with default catalog path."""
    if catalog_path is None:
        catalog_path = Path(__file__).resolve().parents[3] / "config" / "litellm.yaml"
    return generate_report(store, catalog_path=catalog_path, settings=settings)


def generate_report(
    store: LedgerStore,
    catalog_path: Path | str,
    settings: Settings | None = None,
    window_days: int = 30,
) -> dict[str, Any]:
    """Analyze current telemetry ledger and generate Savings Opportunity Report without calling any LLM."""
    if settings is None:
        settings = get_settings()

    catalog = load_catalog(catalog_path)
    clusters = build_clusters(store, window_days=window_days)

    total_spend = sum(c.total_cost for c in clusters)
    total_requests = sum(c.count for c in clusters)

    # Days observed
    first_dates = [c.first_seen for c in clusters if c.first_seen]
    last_dates = [c.last_seen for c in clusters if c.last_seen]
    if first_dates and last_dates:
        earliest = min(first_dates)
        latest = max(last_dates)
        days_observed = max(1, (latest - earliest).days + 1)
    else:
        days_observed = 0

    # Spend share by shape
    spend_by_shape: dict[str, float] = {}
    for c in clusters:
        spend_by_shape[c.shape_mode] = spend_by_shape.get(c.shape_mode, 0.0) + c.total_cost

    scored_items: list[dict[str, Any]] = []
    total_addressable_monthly_savings = 0.0

    for c in clusters:
        sc = score(c, catalog, window_days=window_days)
        g = gate(sc, settings, observation_days=days_observed)

        if g.passed:
            total_addressable_monthly_savings += sc.projected_monthly_savings

        scored_items.append(
            {
                "tenant_id": c.tenant_id,
                "requested_model": c.requested_model,
                "workflow_sig": c.workflow_sig,
                "template_id": c.template_id,
                "shape": c.shape_mode,
                "count": c.count,
                "total_spend_usd": round(c.total_cost, 2),
                "eligible": sc.eligible,
                "ineligible_reason": sc.ineligible_reason,
                "best_candidate": sc.best_candidate_name,
                "projected_monthly_savings_usd": sc.projected_monthly_savings,
                "projected_savings_pct": sc.projected_savings_pct,
                "gate_passed": g.passed,
                "gate_reasons": g.reasons,
                "estimated_probe_cost_usd": g.estimated_probe_cost,
                "savings_to_probe_ratio": g.savings_to_probe_ratio,
            }
        )

    return {
        "summary": {
            "total_requests": total_requests,
            "total_spend_usd": round(total_spend, 2),
            "days_observed": days_observed,
            "total_clusters": len(clusters),
            "addressable_monthly_savings_usd": round(total_addressable_monthly_savings, 2),
            "potential_savings_pct": round(
                (total_addressable_monthly_savings / (total_spend * 30 / max(1, window_days)))
                if total_spend > 0
                else 0.0,
                4,
            ),
        },
        "spend_share_by_shape": {k: round(v, 2) for k, v in spend_by_shape.items()},
        "clusters": scored_items,
    }


def format_report_markdown(report: dict[str, Any]) -> str:
    """Format report into human-readable executive Markdown."""
    s = report["summary"]
    total_spend = s["total_spend_usd"]
    total_reqs = s["total_requests"]
    days = s["days_observed"]
    clusters_count = s["total_clusters"]
    mo_savings = s["addressable_monthly_savings_usd"]
    sav_pct = s["potential_savings_pct"]

    lines = [
        "# LLM Traffic & Savings Opportunity Report",
        "",
        "## Executive Summary",
        f"- **Total Spend (Observed):** ${total_spend:,.2f} USD across {total_reqs:,} requests",
        f"- **Observation Window:** {days} days ({clusters_count} workload clusters identified)",
        f"- **Projected Addressable Monthly Savings:** **${mo_savings:,.2f} USD** ({sav_pct:.1%} reduction)",
        "",
        "## Spend Share by Interaction Shape",
    ]

    for shape_name, spend in report["spend_share_by_shape"].items():
        pct = (spend / s["total_spend_usd"]) * 100 if s["total_spend_usd"] > 0 else 0
        lines.append(f"- **`{shape_name}`:** ${spend:,.2f} ({pct:.1f}%)")

    lines.extend(
        [
            "",
            "## Top Workload Clusters & Feasibility",
            "| Cluster (Tpl / Sig) | Model | Requests | Spend | Candidate | Est. Mo. Savings | Gate Status |",
            "|:---|:---|---:|---:|:---|---:|:---|",
        ]
    )

    for item in report["clusters"][:20]:
        reason = item["gate_reasons"][0] if item["gate_reasons"] else item["ineligible_reason"]
        gate_badge = "✅ READY" if item["gate_passed"] else f"⏳ PENDING ({reason})"
        cand = item["best_candidate"] or "N/A"
        if item["eligible"]:
            mo_sav = item["projected_monthly_savings_usd"]
            sav_ratio = item["projected_savings_pct"]
            savings_str = f"${mo_sav:,.2f} ({sav_ratio:.0%})"
        else:
            savings_str = "N/A"
        tpl_sig = f"`{item['template_id'][:8]}..` / `{item['workflow_sig'][:8]}..`"
        lines.append(
            f"| {tpl_sig} | `{item['requested_model']}` | {item['count']:,} | "
            f"${item['total_spend_usd']:,.2f} | `{cand}` | {savings_str} | {gate_badge} |"
        )

    return "\n".join(lines)
