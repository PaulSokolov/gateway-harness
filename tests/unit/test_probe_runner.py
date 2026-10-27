from unittest.mock import AsyncMock, patch

import pytest

from gateway_harness.catalog import CatalogModel
from gateway_harness.contracts import JudgeResult, Scaffold, Verdict
from gateway_harness.funnel.cluster import ClusterStats
from gateway_harness.ledger.store import LedgerStore
from gateway_harness.probe.client import Budget, BudgetExceeded
from gateway_harness.probe.runner import run_probe


@pytest.fixture
def test_cluster():
    return ClusterStats(
        tenant_id="t1",
        requested_model="gpt-4o",
        workflow_sig="wf_test",
        template_id="tpl_test",
        count=100,
        distinct_days=10,
        total_cost=5.0,
        p50_prompt_tokens=200,
        p99_prompt_tokens=400,
        p50_completion_tokens=100,
        p99_completion_tokens=200,
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
def test_candidate():
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
async def test_run_probe_accepted(tmp_path, test_cluster, test_candidate):
    store = LedgerStore(tmp_path / "ledger.duckdb")
    client = AsyncMock()
    # Mock client completing requests
    client.complete.return_value = ("Candidate answer", {"cost_usd": 0.0001, "finish_reason": "stop"})

    # Noise floor: 10 TIEs and 2 LOSS -> p0 = 10/12 = 0.833, theta = 0.783
    # Candidate run: all WINs -> lo ~ 0.901 >= 0.783 -> accepted!
    judge_side_effects = (
        [JudgeResult(verdict=Verdict.TIE, reason="Equal", judge_cost_usd=0.0001) for _ in range(10)]
        + [JudgeResult(verdict=Verdict.LOSS, reason="Worse", judge_cost_usd=0.0001) for _ in range(2)]
        + [JudgeResult(verdict=Verdict.WIN, reason="Better", judge_cost_usd=0.0001) for _ in range(35)]
    )

    with (
        patch(
            "gateway_harness.probe.runner.sample",
            side_effect=lambda store, key, n, seed: [
                AsyncMock(
                    event_id=f"ev_{i}",
                    request_body={"messages": [{"role": "user", "content": f"msg {i}"}]},
                    baseline_text="Base answer",
                    prompt_tokens=100,
                )
                for i in range(min(n, 35))
            ],
        ),
        patch("gateway_harness.probe.runner.judge", side_effect=judge_side_effects),
    ):
        budget = Budget(limit_usd=10.0)
        res = await run_probe(
            store,
            client,
            test_cluster,
            test_candidate,
            Scaffold(),
            budget,
            judge_model="gpt-4o",
            batch_size=10,
        )

    assert res.status == "accepted"
    assert res.nonloss_rate == 1.0
    assert res.samples_evaluated >= 30


@pytest.mark.asyncio
async def test_run_probe_unstable_baseline(tmp_path, test_cluster, test_candidate):
    store = LedgerStore(tmp_path / "ledger.duckdb")
    client = AsyncMock()
    client.complete.return_value = ("Answer", {"cost_usd": 0.0001})

    # Noise floor returns all LOSS (unstable)
    with (
        patch(
            "gateway_harness.probe.runner.sample",
            return_value=[
                AsyncMock(
                    event_id=f"ev_{i}",
                    request_body={"messages": [{"role": "user", "content": f"msg {i}"}]},
                    baseline_text="Base answer",
                    prompt_tokens=100,
                )
                for i in range(12)
            ],
        ),
        patch(
            "gateway_harness.probe.runner.judge",
            return_value=JudgeResult(verdict=Verdict.LOSS, reason="Divergent", judge_cost_usd=0.0001),
        ),
    ):
        budget = Budget(limit_usd=10.0)
        res = await run_probe(
            store,
            client,
            test_cluster,
            test_candidate,
            Scaffold(),
            budget,
            judge_model="gpt-4o",
        )

    assert res.status == "unstable_baseline"
    assert res.p0 == 0.0


@pytest.mark.asyncio
async def test_run_probe_budget_exhausted(tmp_path, test_cluster, test_candidate):
    store = LedgerStore(tmp_path / "ledger.duckdb")
    client = AsyncMock()
    client.complete.side_effect = BudgetExceeded("Daily limit reached")

    with patch(
        "gateway_harness.probe.runner.sample",
        return_value=[
            AsyncMock(
                event_id="ev_1",
                request_body={"messages": [{"role": "user", "content": "hi"}]},
                baseline_text="Base",
                prompt_tokens=50,
            )
        ],
    ):
        budget = Budget(limit_usd=0.0001)
        res = await run_probe(
            store,
            client,
            test_cluster,
            test_candidate,
            Scaffold(),
            budget,
            judge_model="gpt-4o",
        )

    assert res.status == "budget_exhausted"
