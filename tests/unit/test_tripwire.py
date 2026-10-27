from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from gateway_harness.canary.monitor import run_tripwire_check
from gateway_harness.contracts import Policy, Scaffold, Snapshot
from gateway_harness.ledger.store import LedgerStore
from gateway_harness.policy.snapshot import holder


@pytest.fixture
def mock_active_policy():
    return Policy(
        policy_id="pol_monitored",
        requested_model="gpt-4o",
        target_model="gpt-4o-mini",
        workflow_sig="wf",
        template_ids=["tpl"],
        scaffold=Scaffold(),
        expected_nonloss=0.85,
        expected_savings_pct=0.7,
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )


@pytest.mark.asyncio
async def test_tripwire_expiration(tmp_path, mock_active_policy):
    store = LedgerStore(tmp_path / "ledger.duckdb")
    # Expire the policy
    mock_active_policy.expires_at = datetime.now(UTC) - timedelta(hours=1)
    holder.current = Snapshot(version=1, policies_active=[mock_active_policy])

    with patch("gateway_harness.canary.monitor.disable_policy", new_callable=AsyncMock) as mock_disable:
        disabled = await run_tripwire_check(store)

    assert "pol_monitored" in disabled
    mock_disable.assert_called_once_with("pol_monitored", actor="tripwire", reason="expired", pool=None)


@pytest.mark.asyncio
async def test_tripwire_canary_quality_drop(tmp_path, mock_active_policy):
    store = LedgerStore(tmp_path / "ledger.duckdb")
    con = store.connect()
    holder.current = Snapshot(version=1, policies_active=[mock_active_policy])

    # Insert 25 LOSS verdicts into canary_results
    for i in range(25):
        con.execute(
            """
            INSERT INTO canary_results (policy_id, event_id, verdict, cost)
            VALUES ('pol_monitored', ?, 'loss', 0.001)
            """,
            [f"ev_{i}"],
        )

    with patch("gateway_harness.canary.monitor.disable_policy", new_callable=AsyncMock) as mock_disable:
        disabled = await run_tripwire_check(store)

    assert "pol_monitored" in disabled
    mock_disable.assert_called_once_with(
        "pol_monitored", actor="tripwire", reason="canary_quality", pool=None
    )


@pytest.mark.asyncio
async def test_tripwire_validator_regression(tmp_path, mock_active_policy):
    store = LedgerStore(tmp_path / "ledger.duckdb")
    con = store.connect()
    holder.current = Snapshot(version=1, policies_active=[mock_active_policy])

    # Insert 25 production events in last hour, 10 have finish_reason='length' (40% > 10%)
    for i in range(25):
        finish = "length" if i < 10 else "stop"
        con.execute(
            """
            INSERT INTO events (
                event_id, ts, tenant_id, api_key_hash, call_type, stream,
                requested_model, served_model, status, prompt_tokens,
                completion_tokens, cached_tokens, cost_usd, latency_ms,
                optimized, canary, internal, has_tools, has_images, n_messages,
                fp_version, fp_template_id, fp_workflow_sig, fp_shape,
                request_hash, policy_id, finish_reason
            ) VALUES (
                ?, NOW(), 't1', 'k1', 'chat_completion', false,
                'gpt-4o', 'gpt-4o-mini', 'success', 20,
                10, 0, 0.0001, 100,
                true, false, false, false, false, 1,
                1, 'tpl', 'wf', 'one_shot_simple',
                'h_req', 'pol_monitored', ?
            )
            """,
            [f"prod_ev_{i}", finish],
        )

    with patch("gateway_harness.canary.monitor.disable_policy", new_callable=AsyncMock) as mock_disable:
        disabled = await run_tripwire_check(store)

    assert "pol_monitored" in disabled
    mock_disable.assert_called_once_with(
        "pol_monitored", actor="tripwire", reason="validator_regression", pool=None
    )
