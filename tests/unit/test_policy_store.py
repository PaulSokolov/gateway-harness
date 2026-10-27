from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway_harness.contracts import Policy, Scaffold
from gateway_harness.policy.store import (
    approve_proposal,
    create_proposal,
    disable_policy,
    load_snapshot,
    set_global_kill,
    set_mode,
)


def _make_dummy_policy(policy_id="pol_1"):
    return Policy(
        policy_id=policy_id,
        requested_model="gpt-4o",
        target_model="gpt-4o-mini",
        workflow_sig="wf_1234",
        template_ids=["tpl_1", "tpl_2"],
        scaffold=Scaffold(system_addendum="Be brief.", params={"temperature": 0.2}),
        expected_nonloss=0.85,
        expected_savings_pct=0.70,
        canary_rate=0.05,
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC),
    )


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = AsyncMock()
    tx = AsyncMock()
    conn.transaction = MagicMock(return_value=tx)

    # Async context manager for pool.acquire()
    acquire_ctx = AsyncMock()
    acquire_ctx.__aenter__.return_value = conn
    acquire_ctx.__aexit__.return_value = None
    pool.acquire.return_value = acquire_ctx
    return pool, conn


@pytest.mark.asyncio
async def test_create_proposal_mutates_version_and_audit(mock_pool):
    pool, conn = mock_pool
    conn.fetchrow.return_value = {"ver": 2}

    policy = _make_dummy_policy()
    res = await create_proposal(policy, evidence={"p0": 0.9}, pool=pool)
    assert res == "pol_1"

    # Verify audit executed
    assert any("INSERT INTO gh_audit" in str(call) for call in conn.execute.call_args_list)
    assert any("INSERT INTO gh_proposals" in str(call) for call in conn.execute.call_args_list)


@pytest.mark.asyncio
async def test_approve_proposal(mock_pool):
    pool, conn = mock_pool
    policy = _make_dummy_policy()
    conn.fetchrow.side_effect = [
        {"policy": policy.model_dump_json()},  # select proposal
        {"ver": 3},  # bump version
    ]

    await approve_proposal("pol_1", actor="admin", pool=pool)
    assert any("INSERT INTO gh_policies" in str(call) for call in conn.execute.call_args_list)
    assert any("UPDATE gh_proposals" in str(call) for call in conn.execute.call_args_list)


@pytest.mark.asyncio
async def test_disable_policy(mock_pool):
    pool, conn = mock_pool
    conn.fetchrow.return_value = {"ver": 4}

    await disable_policy("pol_1", actor="canary", reason="regression", pool=pool)
    assert any(
        "UPDATE gh_policies SET status = 'disabled'" in str(call) for call in conn.execute.call_args_list
    )


@pytest.mark.asyncio
async def test_set_mode_and_kill(mock_pool):
    pool, conn = mock_pool
    conn.fetchrow.return_value = {"ver": 5}

    await set_mode("t_corp", "auto", actor="admin", pool=pool)
    assert any("INSERT INTO gh_tenant_modes" in str(call) for call in conn.execute.call_args_list)

    await set_global_kill(True, actor="admin", pool=pool)
    assert any("INSERT INTO gh_settings" in str(call) for call in conn.execute.call_args_list)


@pytest.mark.asyncio
async def test_load_snapshot(mock_pool):
    pool, conn = mock_pool
    conn.fetchrow.side_effect = [
        {"ver": 10},  # policy_version
        {"value": "false"},  # global_kill
    ]
    conn.fetch.side_effect = [
        [{"tenant_id": "t1", "mode": "auto"}],  # tenant modes
        [  # policies
            {
                "policy_id": "pol_1",
                "cluster_key": "gpt-4o:wf_1234",
                "requested_model": "gpt-4o",
                "target_model": "gpt-4o-mini",
                "scaffold": '{"system_addendum": "hi", "params": {}}',
                "template_ids": ["tpl_1"],
                "canary_rate": 0.05,
                "expected_nonloss": 0.85,
                "status": "active",
                "tenant_id": "t1",
                "fingerprint_version": 1,
                "created_at": datetime.now(UTC),
                "expires_at": datetime.now(UTC),
            }
        ],
    ]

    snap = await load_snapshot(pool=pool)
    assert snap.version == 10
    assert snap.global_kill is False
    assert snap.modes["t1"] == "auto"
    assert len(snap.policies_active) == 1
    assert snap.policies_active[0].policy_id == "pol_1"
