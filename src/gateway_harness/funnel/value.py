from __future__ import annotations

from dataclasses import dataclass

from gateway_harness.catalog import CatalogModel, Needs, candidates_for
from gateway_harness.funnel.cluster import ClusterStats
from gateway_harness.pricing import cost


@dataclass
class ScoredCluster:
    cluster: ClusterStats
    eligible: bool
    ineligible_reason: str | None
    best_candidate: CatalogModel | None
    best_candidate_name: str | None
    projected_monthly_savings: float
    projected_savings_pct: float
    current_unit_cost: float
    projected_unit_cost: float


def score(
    cluster: ClusterStats,
    catalog: list[CatalogModel],
    window_days: int = 30,
) -> ScoredCluster:
    """Evaluate cluster eligibility and compute projected monthly dollar savings."""
    current_unit_cost = cluster.total_cost / cluster.count if cluster.count > 0 else 0.0

    # 1. Eligibility Filter (v1 Scope: one_shot_templated and structured_output, no tools, no vision)
    if cluster.shape_mode not in ("one_shot_templated", "structured_output"):
        return ScoredCluster(
            cluster=cluster,
            eligible=False,
            ineligible_reason=f"Shape '{cluster.shape_mode}' out of scope for v1 optimizer",
            best_candidate=None,
            best_candidate_name=None,
            projected_monthly_savings=0.0,
            projected_savings_pct=0.0,
            current_unit_cost=current_unit_cost,
            projected_unit_cost=current_unit_cost,
        )

    if cluster.has_tools:
        return ScoredCluster(
            cluster=cluster,
            eligible=False,
            ineligible_reason="Tool-calling traffic out of scope for v1",
            best_candidate=None,
            best_candidate_name=None,
            projected_monthly_savings=0.0,
            projected_savings_pct=0.0,
            current_unit_cost=current_unit_cost,
            projected_unit_cost=current_unit_cost,
        )

    if cluster.has_images:
        return ScoredCluster(
            cluster=cluster,
            eligible=False,
            ineligible_reason="Multimodal/vision traffic out of scope for v1",
            best_candidate=None,
            best_candidate_name=None,
            projected_monthly_savings=0.0,
            projected_savings_pct=0.0,
            current_unit_cost=current_unit_cost,
            projected_unit_cost=current_unit_cost,
        )

    if cluster.error_rate >= 0.05:
        return ScoredCluster(
            cluster=cluster,
            eligible=False,
            ineligible_reason=f"High error rate ({cluster.error_rate:.1%}) indicates upstream instability",
            best_candidate=None,
            best_candidate_name=None,
            projected_monthly_savings=0.0,
            projected_savings_pct=0.0,
            current_unit_cost=current_unit_cost,
            projected_unit_cost=current_unit_cost,
        )

    needs = Needs(
        p99_prompt_tokens=cluster.p99_prompt_tokens,
        needs_tools=cluster.has_tools,
        needs_vision=cluster.has_images,
        needs_response_schema=cluster.has_response_format,
    )

    valid_candidates = candidates_for(cluster.requested_model, needs, catalog)
    if not valid_candidates:
        return ScoredCluster(
            cluster=cluster,
            eligible=False,
            ineligible_reason="No cheaper candidate model in catalog satisfies capabilities",
            best_candidate=None,
            best_candidate_name=None,
            projected_monthly_savings=0.0,
            projected_savings_pct=0.0,
            current_unit_cost=current_unit_cost,
            projected_unit_cost=current_unit_cost,
        )

    # 2. Score candidate savings
    best_candidate: CatalogModel | None = None
    best_savings: float = -1.0
    best_unit_cost: float = current_unit_cost

    # Evaluate up to 3 cheapest candidates
    for cand in valid_candidates[:3]:
        # Account for 10% prompt scaffolding allowance and 15% verbosity expansion
        est_prompt_tokens = int(cluster.p50_prompt_tokens * 1.10)
        est_comp_tokens = int(cluster.p50_completion_tokens * 1.15)

        cand_cost = cost(
            cand.underlying_model,
            prompt_tokens=est_prompt_tokens,
            completion_tokens=est_comp_tokens,
        )
        if cand_cost is None:
            # Estimate from catalog blended cost
            cand_cost = ((est_prompt_tokens * cand.in_price) + (est_comp_tokens * cand.out_price)) / 1_000_000

        unit_delta = current_unit_cost - cand_cost
        if unit_delta > 0:
            scale_factor = 30.0 / max(1, window_days)
            monthly_savings = unit_delta * cluster.count * scale_factor
            if monthly_savings > best_savings:
                best_savings = monthly_savings
                best_candidate = cand
                best_unit_cost = cand_cost

    if best_candidate is None or best_savings <= 0:
        return ScoredCluster(
            cluster=cluster,
            eligible=False,
            ineligible_reason="Negative or negligible projected savings after scaffolding allowances",
            best_candidate=None,
            best_candidate_name=None,
            projected_monthly_savings=0.0,
            projected_savings_pct=0.0,
            current_unit_cost=current_unit_cost,
            projected_unit_cost=current_unit_cost,
        )

    savings_pct = (current_unit_cost - best_unit_cost) / current_unit_cost if current_unit_cost > 0 else 0.0

    return ScoredCluster(
        cluster=cluster,
        eligible=True,
        ineligible_reason=None,
        best_candidate=best_candidate,
        best_candidate_name=best_candidate.name,
        projected_monthly_savings=round(best_savings, 2),
        projected_savings_pct=round(savings_pct, 4),
        current_unit_cost=current_unit_cost,
        projected_unit_cost=best_unit_cost,
    )
