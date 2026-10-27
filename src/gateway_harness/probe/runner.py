"""End-to-end Contrastive Probe Runner orchestrating noise floor, validation, judging, and SPRT."""

import logging
from typing import Any, Literal

from pydantic import BaseModel

from gateway_harness.catalog import CatalogModel
from gateway_harness.contracts import ModelClient, Scaffold, Verdict
from gateway_harness.funnel.cluster import ClusterStats
from gateway_harness.ledger.store import LedgerStore
from gateway_harness.metrics import PROBE_RUNS_TOTAL
from gateway_harness.probe.client import Budget, BudgetExceeded
from gateway_harness.probe.judge import judge
from gateway_harness.probe.sampler import sample
from gateway_harness.probe.stats import decide, wilson
from gateway_harness.probe.validators import validate
from gateway_harness.routing.scaffold import apply_scaffold

logger = logging.getLogger("gateway_harness.probe.runner")


class LossExample(BaseModel):
    """Detailed evidence of a probe candidate failure for the scaffolding proposer."""

    event_id: str
    request_messages: list[dict[str, Any]]
    baseline_text: str
    candidate_text: str
    validator_codes: list[str]
    judge_reason: str | None = None


class ProbeResult(BaseModel):
    """Full empirical outcome of a contrastive candidate probe run."""

    status: Literal["accepted", "rejected", "unstable_baseline", "budget_exhausted"]
    nonloss_rate: float
    wilson_interval: tuple[float, float]
    p0: float
    samples_evaluated: int
    candidate_cost_per_request: float
    length_ratio: float
    verdicts: list[Verdict]
    losses: list[LossExample]
    total_spend_usd: float


async def run_probe(
    store: LedgerStore,
    client: ModelClient,
    cluster: ClusterStats,
    candidate: CatalogModel,
    scaffold: Scaffold,
    budget: Budget,
    judge_model: str,
    n_max: int = 60,
    batch_size: int = 10,
) -> ProbeResult:
    """Execute contrastive probe on candidate model vs production baseline."""
    initial_spend = budget.spent_usd
    cluster_key = f"{cluster.requested_model}:{cluster.workflow_sig}"

    # 1. Measure Noise Floor (p0)
    noise_samples = sample(store, cluster_key, n=12, seed=100)
    if not noise_samples:
        # Fallback if insufficient historical store
        p0 = 0.85
    else:
        p0_verdicts: list[Verdict] = []
        try:
            for s in noise_samples:
                # Replay requested model
                reply_text, _ = await client.complete(
                    cluster.requested_model,
                    s.request_body.get("messages", []),
                )
                val_errs = validate(s.request_body, s.baseline_text, reply_text)
                if val_errs:
                    p0_verdicts.append(Verdict.LOSS)
                else:
                    j_res = await judge(
                        client,
                        judge_model,
                        s.request_body.get("messages", []),
                        s.baseline_text,
                        reply_text,
                    )
                    p0_verdicts.append(j_res.verdict)
        except BudgetExceeded:
            PROBE_RUNS_TOTAL.labels(status="budget_exhausted").inc()
            return ProbeResult(
                status="budget_exhausted",
                nonloss_rate=0.0,
                wilson_interval=(0.0, 1.0),
                p0=0.0,
                samples_evaluated=0,
                candidate_cost_per_request=0.0,
                length_ratio=1.0,
                verdicts=[],
                losses=[],
                total_spend_usd=budget.spent_usd - initial_spend,
            )

        nonloss_count = sum(1 for v in p0_verdicts if v in (Verdict.WIN, Verdict.TIE))
        p0 = nonloss_count / len(p0_verdicts) if p0_verdicts else 0.85
        if p0 < 0.60:
            PROBE_RUNS_TOTAL.labels(status="unstable_baseline").inc()
            return ProbeResult(
                status="unstable_baseline",
                nonloss_rate=p0,
                wilson_interval=wilson(nonloss_count, len(p0_verdicts)),
                p0=p0,
                samples_evaluated=len(p0_verdicts),
                candidate_cost_per_request=0.0,
                length_ratio=1.0,
                verdicts=p0_verdicts,
                losses=[],
                total_spend_usd=budget.spent_usd - initial_spend,
            )

    # 2. Candidate Evaluation in Batches
    eval_samples = sample(store, cluster_key, n=n_max, seed=42)
    verdicts: list[Verdict] = []
    losses: list[LossExample] = []
    total_candidate_cost = 0.0
    cand_chars = 0
    base_chars = 0

    try:
        for i in range(0, len(eval_samples), batch_size):
            batch = eval_samples[i : i + batch_size]
            for s in batch:
                transformed_data = apply_scaffold(s.request_body, scaffold)
                cand_text, meta = await client.complete(
                    candidate.underlying_model,
                    transformed_data.get("messages", []),
                )
                total_candidate_cost += meta.get("cost_usd") or 0.0
                cand_chars += len(cand_text)
                base_chars += max(1, len(s.baseline_text))

                val_errs = validate(
                    s.request_body,
                    s.baseline_text,
                    cand_text,
                    finish_reason=meta.get("finish_reason"),
                )

                if val_errs:
                    verdicts.append(Verdict.LOSS)
                    losses.append(
                        LossExample(
                            event_id=s.event_id,
                            request_messages=s.request_body.get("messages", []),
                            baseline_text=s.baseline_text,
                            candidate_text=cand_text,
                            validator_codes=val_errs,
                        )
                    )
                else:
                    j_res = await judge(
                        client,
                        judge_model,
                        s.request_body.get("messages", []),
                        s.baseline_text,
                        cand_text,
                    )
                    verdicts.append(j_res.verdict)
                    if j_res.verdict == Verdict.LOSS:
                        losses.append(
                            LossExample(
                                event_id=s.event_id,
                                request_messages=s.request_body.get("messages", []),
                                baseline_text=s.baseline_text,
                                candidate_text=cand_text,
                                validator_codes=[],
                                judge_reason=j_res.reason,
                            )
                        )

            # Check SPRT early stopping after batch
            status = decide(verdicts, p0=p0, delta=0.05, n_min=30, n_early=10, n_max=n_max)
            if status in ("accept", "reject"):
                break

    except BudgetExceeded:
        PROBE_RUNS_TOTAL.labels(status="budget_exhausted").inc()
        k = sum(1 for v in verdicts if v in (Verdict.WIN, Verdict.TIE))
        n = max(1, len(verdicts))
        return ProbeResult(
            status="budget_exhausted",
            nonloss_rate=k / n,
            wilson_interval=wilson(k, n),
            p0=p0,
            samples_evaluated=len(verdicts),
            candidate_cost_per_request=total_candidate_cost / n if n else 0.0,
            length_ratio=cand_chars / max(1, base_chars),
            verdicts=verdicts,
            losses=losses,
            total_spend_usd=budget.spent_usd - initial_spend,
        )

    # 3. Finalize outcome
    k = sum(1 for v in verdicts if v in (Verdict.WIN, Verdict.TIE))
    n = max(1, len(verdicts))
    final_decision = decide(verdicts, p0=p0, delta=0.05, n_min=30, n_early=10, n_max=n_max)
    probe_status: Literal["accepted", "rejected"] = "accepted" if final_decision == "accept" else "rejected"

    PROBE_RUNS_TOTAL.labels(status=probe_status).inc()
    return ProbeResult(
        status=probe_status,
        nonloss_rate=round(k / n, 4),
        wilson_interval=wilson(k, n),
        p0=round(p0, 4),
        samples_evaluated=len(verdicts),
        candidate_cost_per_request=round(total_candidate_cost / n, 6),
        length_ratio=round(cand_chars / max(1, base_chars), 3),
        verdicts=verdicts,
        losses=losses,
        total_spend_usd=round(budget.spent_usd - initial_spend, 6),
    )
