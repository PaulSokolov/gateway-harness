from __future__ import annotations

from dataclasses import dataclass

from gateway_harness.funnel.value import ScoredCluster
from gateway_harness.pricing import cost
from gateway_harness.settings import Settings, get_settings


@dataclass
class GateResult:
    passed: bool
    reasons: list[str]
    estimated_probe_cost: float
    savings_to_probe_ratio: float


def estimate_probe_cost(
    cluster: ScoredCluster,
    judge_model: str | None = None,
) -> float:
    """Calculate the estimated USD cost of running the complete contrastive probe evaluation.

    Includes:
    - 12 baseline re-runs for the noise floor check
    - up to 60 candidate re-runs
    - 2x position-swapped judge calls (up to 72 samples total)
    """
    if not cluster.best_candidate:
        return 0.0

    p50_prompt = cluster.cluster.p50_prompt_tokens
    p50_comp = cluster.cluster.p50_completion_tokens

    # Candidate run cost (up to 60 samples)
    cand_unit = cost(cluster.best_candidate.underlying_model, p50_prompt, p50_comp) or 0.001
    cand_total = 60 * cand_unit

    # Baseline re-runs for noise floor (12 samples)
    base_unit = cost(cluster.cluster.requested_model, p50_prompt, p50_comp) or 0.005
    base_total = 12 * base_unit

    # Judge costs: prompt contains task + 2 answers (~150 tokens response)
    judge = judge_model or "claude-3-5-sonnet"
    judge_prompt_tokens = p50_prompt + (2 * p50_comp)
    judge_unit = cost(judge, prompt_tokens=judge_prompt_tokens, completion_tokens=150) or 0.003
    judge_total = 2 * (60 + 12) * judge_unit

    return round(cand_total + base_total + judge_total, 4)


def gate(
    scored: ScoredCluster,
    settings: Settings | None = None,
    observation_days: int = 10,
) -> GateResult:
    """Evaluate whether a cluster clears the economic and statistical feasibility gate."""
    if settings is None:
        settings = get_settings()

    reasons: list[str] = []

    if not scored.eligible:
        return GateResult(
            passed=False,
            reasons=[scored.ineligible_reason or "Ineligible cluster"],
            estimated_probe_cost=0.0,
            savings_to_probe_ratio=0.0,
        )

    probe_cost = estimate_probe_cost(scored, settings.JUDGE_MODEL)

    # 1. Observation Days
    if observation_days < settings.OBSERVATION_DAYS:
        reasons.append(
            f"Observation period ({observation_days}d) below required minimum ({settings.OBSERVATION_DAYS}d)"
        )

    # 2. Minimum Cluster Volume
    if scored.cluster.count < settings.MIN_CLUSTER_REQUESTS:
        reasons.append(
            f"Volume ({scored.cluster.count} reqs) below minimum threshold ({settings.MIN_CLUSTER_REQUESTS})"
        )

    # 3. Minimum Recurrence Days
    if scored.cluster.distinct_days < settings.MIN_RECURRENCE_DAYS:
        reasons.append(
            f"Active days ({scored.cluster.distinct_days}d) below recurrence "
            f"requirement ({settings.MIN_RECURRENCE_DAYS}d)"
        )

    # 4. Economic ROI: Monthly Savings vs Probe Cost
    ratio = scored.projected_monthly_savings / probe_cost if probe_cost > 0 else 0.0
    if ratio < settings.GATE_MARGIN:
        reasons.append(
            f"Projected savings ratio ({ratio:.1f}x) below economic margin "
            f"requirement ({settings.GATE_MARGIN:.1f}x)"
        )

    # 5. Minimum Percentage Savings
    if scored.projected_savings_pct < settings.MIN_SAVINGS_PCT:
        reasons.append(
            f"Projected savings ({scored.projected_savings_pct:.1%}) below "
            f"threshold ({settings.MIN_SAVINGS_PCT:.1%})"
        )

    passed = len(reasons) == 0
    return GateResult(
        passed=passed,
        reasons=reasons,
        estimated_probe_cost=probe_cost,
        savings_to_probe_ratio=round(ratio, 2),
    )
