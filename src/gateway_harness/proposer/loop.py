"""Harness² Propose-Probe-Compose recursive optimization loop."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg

from gateway_harness.catalog import CatalogModel
from gateway_harness.contracts import ModelClient, Policy, Proposal, Scaffold
from gateway_harness.funnel.cluster import ClusterStats
from gateway_harness.ledger.store import LedgerStore
from gateway_harness.policy.store import approve_proposal, create_proposal
from gateway_harness.probe.client import Budget, BudgetExceeded
from gateway_harness.probe.runner import ProbeResult, run_probe
from gateway_harness.proposer.lessons import archetype, record_lesson, top_lessons
from gateway_harness.proposer.propose import propose
from gateway_harness.settings import get_settings

logger = logging.getLogger("gateway_harness.proposer.loop")


async def optimize_cluster(
    store: LedgerStore,
    client: ModelClient,
    cluster: ClusterStats,
    candidates: list[CatalogModel],
    budget: Budget,
    judge_model: str,
    rounds: int = 2,
    k: int = 3,
    pool: asyncpg.Pool | None = None,
) -> Proposal | None:
    """Run recursive Propose-Probe-Compose optimization on cluster across candidate models."""
    settings = get_settings()

    for candidate in candidates:
        logger.info(
            "Optimizing cluster %s:%s with candidate %s",
            cluster.requested_model,
            cluster.workflow_sig,
            candidate.name,
        )

        try:
            # Round 0: Direct zero-scaffold probe
            res0 = await run_probe(
                store=store,
                client=client,
                cluster=cluster,
                candidate=candidate,
                scaffold=Scaffold(),
                budget=budget,
                judge_model=judge_model,
            )

            if res0.status == "accepted":
                logger.info("Candidate %s accepted in round 0 (direct downgrade)", candidate.name)
                return await _build_and_persist_proposal(
                    cluster=cluster,
                    candidate=candidate,
                    scaffold=Scaffold(),
                    probe_result=res0,
                    pool=pool,
                    auto_approve=settings.AUTO_APPROVE,
                )

            # If rejected, evaluate feasibility of scaffolding
            delta = 0.05
            theta_min = res0.p0 - (3 * delta)
            if res0.nonloss_rate < theta_min:
                logger.info(
                    "Candidate %s nonloss %0.2f far below parity bound %0.2f; skipping candidate",
                    candidate.name,
                    res0.nonloss_rate,
                    theta_min,
                )
                continue

            # Recursive Scaffolding Rounds
            current_losses = res0.losses
            for round_idx in range(1, rounds + 1):
                logger.info("Starting scaffolding round %d for candidate %s", round_idx, candidate.name)

                # Fetch lessons
                arch = archetype(system_prompt="", user_prompt=cluster.shape_mode)
                lessons = []
                try:
                    lessons = await top_lessons(arch, k=3, pool=pool)
                except Exception as exc:
                    logger.debug("Could not fetch historical lessons: %s", exc)

                # Propose candidate scaffolds from failures
                variants = await propose(
                    client=client,
                    model=judge_model,
                    losses=current_losses,
                    lessons=lessons,
                    k=k,
                )

                if not variants:
                    break

                # Quick-probe each variant (15 samples)
                best_variant: Scaffold | None = None
                best_score = -1.0
                for variant in variants:
                    quick_res = await run_probe(
                        store=store,
                        client=client,
                        cluster=cluster,
                        candidate=candidate,
                        scaffold=variant,
                        budget=budget,
                        judge_model=judge_model,
                        n_max=15,
                        batch_size=15,
                    )
                    if quick_res.nonloss_rate > best_score:
                        best_score = quick_res.nonloss_rate
                        best_variant = variant

                if not best_variant or best_score < res0.p0 - delta:
                    continue

                # Compose & Full Probe on Best Variant
                logger.info("Full validation probe on best scaffold variant (quick score: %0.2f)", best_score)
                full_res = await run_probe(
                    store=store,
                    client=client,
                    cluster=cluster,
                    candidate=candidate,
                    scaffold=best_variant,
                    budget=budget,
                    judge_model=judge_model,
                    n_max=60,
                    batch_size=10,
                )

                if full_res.status == "accepted":
                    logger.info(
                        "Candidate %s accepted in round %d with scaffold!",
                        candidate.name,
                        round_idx,
                    )
                    # Record lesson
                    try:
                        await record_lesson(
                            archetype_name=arch,
                            cue=f"Failures on {cluster.requested_model} -> {candidate.name}",
                            lesson_text=best_variant.system_addendum or "Parameter optimization",
                            evidence={"nonloss": full_res.nonloss_rate, "round": round_idx},
                            scaffold=best_variant,
                            pool=pool,
                        )
                    except Exception as e:
                        logger.warning("Failed to record lesson: %s", e)

                    return await _build_and_persist_proposal(
                        cluster=cluster,
                        candidate=candidate,
                        scaffold=best_variant,
                        probe_result=full_res,
                        pool=pool,
                        auto_approve=settings.AUTO_APPROVE,
                    )

                current_losses = full_res.losses

        except BudgetExceeded:
            logger.warning("Optimization budget exhausted; aborting loop")
            return None
        except Exception as exc:
            logger.exception("Error in optimization loop for candidate %s: %s", candidate.name, exc)
            continue

    return None


async def _build_and_persist_proposal(
    cluster: ClusterStats,
    candidate: CatalogModel,
    scaffold: Scaffold,
    probe_result: ProbeResult,
    pool: asyncpg.Pool | None,
    auto_approve: bool = False,
) -> Proposal:
    """Construct Proposal, record to Postgres, and optionally auto-approve."""
    now = datetime.now(UTC)
    policy_id = f"pol_{uuid.uuid4().hex[:12]}"

    unit_cost_orig = cluster.total_cost / max(1, cluster.count)
    unit_cost_cand = probe_result.candidate_cost_per_request
    savings_pct = max(0.0, 1.0 - (unit_cost_cand / unit_cost_orig)) if unit_cost_orig > 0 else 0.50

    policy = Policy(
        policy_id=policy_id,
        tenant_id=cluster.tenant_id if cluster.tenant_id != "global" else None,
        requested_model=cluster.requested_model,
        target_model=candidate.underlying_model,
        workflow_sig=cluster.workflow_sig,
        template_ids=[cluster.template_id],
        fingerprint_version=1,
        scaffold=scaffold,
        status="proposed",
        expected_nonloss=probe_result.nonloss_rate,
        expected_savings_pct=round(savings_pct, 4),
        canary_rate=0.05,
        created_at=now,
        expires_at=now + timedelta(days=30),
    )

    evidence = {
        "nonloss_rate": probe_result.nonloss_rate,
        "wilson_interval": probe_result.wilson_interval,
        "p0": probe_result.p0,
        "samples_evaluated": probe_result.samples_evaluated,
        "candidate_cost_per_request": probe_result.candidate_cost_per_request,
        "length_ratio": probe_result.length_ratio,
        "total_spend_usd": probe_result.total_spend_usd,
    }

    try:
        await create_proposal(policy=policy, evidence=evidence, actor="optimizer", pool=pool)
        if auto_approve:
            await approve_proposal(proposal_id=policy_id, actor="auto", pool=pool)
            policy.status = "active"
    except Exception as e:
        logger.warning("Could not persist proposal to Postgres: %s", e)

    return Proposal(
        proposal_id=policy_id,
        policy=policy,
        evidence=evidence,
        status="approved" if auto_approve else "proposed",
        created_at=now,
    )
