import json
from unittest.mock import AsyncMock, patch

import pytest

from gateway_harness.canary.sampler import execute_canary_evaluations
from gateway_harness.contracts import JudgeResult, Verdict
from gateway_harness.ledger.store import LedgerStore
from gateway_harness.probe.client import Budget


@pytest.mark.asyncio
async def test_execute_canary_evaluations(tmp_path):
    store = LedgerStore(tmp_path / "ledger.duckdb")
    con = store.connect()

    # Seed an unassessed canary event
    req_body = json.dumps({"messages": [{"role": "user", "content": "What is Python?"}]})
    cand_body = json.dumps({"choices": [{"message": {"content": "A programming language."}}]})

    con.execute("INSERT INTO payloads (hash, kind, body) VALUES ('h_req', 'request', ?)", [req_body])
    con.execute("INSERT INTO payloads (hash, kind, body) VALUES ('h_cand', 'response', ?)", [cand_body])

    con.execute(
        """
        INSERT INTO events (
            event_id, ts, tenant_id, api_key_hash, call_type, stream,
            requested_model, served_model, status, prompt_tokens,
            completion_tokens, cached_tokens, cost_usd, latency_ms,
            optimized, canary, internal, has_tools, has_images, n_messages,
            fp_version, fp_template_id, fp_workflow_sig, fp_shape,
            request_hash, response_hash, policy_id
        ) VALUES (
            'canary_ev_1', NOW(), 't1', 'k1', 'chat_completion', false,
            'gpt-4o', 'gpt-4o-mini', 'success', 20,
            10, 0, 0.0001, 100,
            true, true, false, false, false, 1,
            1, 'tpl_1', 'wf_1', 'one_shot_simple',
            'h_req', 'h_cand', 'pol_canary'
        )
        """
    )

    client = AsyncMock()
    client.complete.return_value = ("A popular high-level programming language.", {"cost_usd": 0.0002})

    with patch(
        "gateway_harness.canary.sampler.judge",
        return_value=JudgeResult(verdict=Verdict.WIN, reason="Clear", judge_cost_usd=0.0001),
    ):
        budget = Budget(limit_usd=10.0)
        count = await execute_canary_evaluations(store, client, judge_model="gpt-4o", budget=budget)

    assert count == 1
    # Verify result stored in DuckDB canary_results
    res = con.execute("SELECT verdict, cost FROM canary_results WHERE event_id = 'canary_ev_1'").fetchone()
    assert res is not None
    assert res[0] == "win"
    assert res[1] == pytest.approx(0.0003)
