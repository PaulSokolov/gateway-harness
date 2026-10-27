from unittest.mock import AsyncMock, patch

import pytest

from gateway_harness.catalog import CatalogModel
from gateway_harness.contracts import Scaffold, Verdict
from gateway_harness.funnel.cluster import ClusterStats
from gateway_harness.ledger.store import LedgerStore
from gateway_harness.probe.client import Budget
from gateway_harness.probe.runner import ProbeResult
from gateway_harness.proposer.loop import optimize_cluster


@pytest.fixture
def cluster():
    return ClusterStats(
        tenant_id="t1",
        requested_model="gpt-4o",
        workflow_sig="wf_loop",
        template_id="tpl_loop",
        count=200,
        distinct_days=5,
        total_cost=10.0,
        p50_prompt_tokens=200,
        p99_prompt_tokens=300,
        p50_completion_tokens=100,
        p99_completion_tokens=150,
        cached_token_share=0.0,
        shape_mode="one_shot_templated",
        has_tools=False,
        has_images=False,
        has_response_format=False,
        error_rate=0.0,
        length_trunc_rate=0.0,
        first_seen=None,
        last_seen=None,
    )


@pytest.fixture
def candidate():
    return CatalogModel(
        name="gpt-4o-mini",
        underlying_model="openai/gpt-4o-mini",
        in_price=0.15,
        out_price=0.60,
        max_input_tokens=128000,
        supports_tools=True,
        supports_vision=True,
        supports_response_schema=True,
    )


@pytest.mark.asyncio
async def test_optimize_cluster_round_0_direct_accept(tmp_path, cluster, candidate):
    store = LedgerStore(tmp_path / "ledger.duckdb")
    client = AsyncMock()
    budget = Budget(limit_usd=10.0)

    # Round 0 succeeds immediately
    mock_res0 = ProbeResult(
        status="accepted",
        nonloss_rate=0.92,
        wilson_interval=(0.85, 0.96),
        p0=0.85,
        samples_evaluated=30,
        candidate_cost_per_request=0.0005,
        length_ratio=0.95,
        verdicts=[Verdict.WIN] * 30,
        losses=[],
        total_spend_usd=0.02,
    )

    with (
        patch("gateway_harness.proposer.loop.run_probe", return_value=mock_res0),
        patch("gateway_harness.proposer.loop.create_proposal", return_value="pol_1"),
    ):
        proposal = await optimize_cluster(
            store=store,
            client=client,
            cluster=cluster,
            candidates=[candidate],
            budget=budget,
            judge_model="gpt-4o",
            rounds=2,
        )

    assert proposal is not None
    assert proposal.policy.target_model == "openai/gpt-4o-mini"
    assert proposal.policy.scaffold.system_addendum is None
    assert proposal.policy.expected_nonloss == 0.92


@pytest.mark.asyncio
async def test_optimize_cluster_round_1_scaffold_accept(tmp_path, cluster, candidate):
    store = LedgerStore(tmp_path / "ledger.duckdb")
    client = AsyncMock()
    budget = Budget(limit_usd=10.0)

    # Round 0 rejected with close parity (nonloss 0.75 >= p0 - 3*delta = 0.85 - 0.15 = 0.70)
    mock_res0 = ProbeResult(
        status="rejected",
        nonloss_rate=0.75,
        wilson_interval=(0.60, 0.85),
        p0=0.85,
        samples_evaluated=30,
        candidate_cost_per_request=0.0005,
        length_ratio=0.95,
        verdicts=[Verdict.WIN] * 22 + [Verdict.LOSS] * 8,
        losses=[],
        total_spend_usd=0.02,
    )

    # Quick probe on variant scores 0.88
    mock_quick = ProbeResult(
        status="rejected",
        nonloss_rate=0.88,
        wilson_interval=(0.70, 0.95),
        p0=0.85,
        samples_evaluated=15,
        candidate_cost_per_request=0.0005,
        length_ratio=0.95,
        verdicts=[Verdict.WIN] * 13,
        losses=[],
        total_spend_usd=0.01,
    )

    # Full probe on composed variant passes
    mock_full = ProbeResult(
        status="accepted",
        nonloss_rate=0.90,
        wilson_interval=(0.82, 0.95),
        p0=0.85,
        samples_evaluated=35,
        candidate_cost_per_request=0.0005,
        length_ratio=0.98,
        verdicts=[Verdict.WIN] * 32,
        losses=[],
        total_spend_usd=0.03,
    )

    with (
        patch(
            "gateway_harness.proposer.loop.run_probe",
            side_effect=[mock_res0, mock_quick, mock_full],
        ),
        patch(
            "gateway_harness.proposer.loop.propose",
            return_value=[Scaffold(system_addendum="Follow format strictly.", params={"temperature": 0.1})],
        ),
        patch("gateway_harness.proposer.loop.create_proposal", return_value="pol_scaffold"),
        patch("gateway_harness.proposer.loop.record_lesson", return_value="les_1"),
    ):
        proposal = await optimize_cluster(
            store=store,
            client=client,
            cluster=cluster,
            candidates=[candidate],
            budget=budget,
            judge_model="gpt-4o",
            rounds=1,
        )

    assert proposal is not None
    assert proposal.policy.scaffold.system_addendum == "Follow format strictly."
    assert proposal.policy.scaffold.params["temperature"] == 0.1
    assert proposal.policy.expected_nonloss == 0.90
