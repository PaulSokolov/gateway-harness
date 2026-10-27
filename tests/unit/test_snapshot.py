import asyncio
from unittest.mock import AsyncMock

import pytest

from gateway_harness.contracts import Policy, Scaffold, Snapshot
from gateway_harness.policy.matcher import SnapshotIndex
from gateway_harness.policy.snapshot import SnapshotHolder


@pytest.mark.asyncio
async def test_snapshot_poll_once_updates_on_version_change():
    holder = SnapshotHolder()
    assert holder.current.version == 0

    mock_v_loader = AsyncMock(return_value=1)
    mock_s_loader = AsyncMock(
        return_value=Snapshot(
            version=1,
            policies_active=[],
            modes={"tenant_a": "auto"},
            global_kill=False,
        )
    )

    updated = await holder.poll_once(mock_v_loader, mock_s_loader)
    assert updated is True
    assert holder.current.version == 1
    assert holder.current.modes["tenant_a"] == "auto"

    # Second poll with same version -> no reload
    updated2 = await holder.poll_once(mock_v_loader, mock_s_loader)
    assert updated2 is False
    assert mock_s_loader.call_count == 1


@pytest.mark.asyncio
async def test_snapshot_error_tolerance():
    holder = SnapshotHolder()
    holder.current = Snapshot(version=5, policies_active=[], modes={}, global_kill=False)

    mock_v_loader = AsyncMock(side_effect=RuntimeError("Postgres network timeout"))
    mock_s_loader = AsyncMock()

    updated = await holder.poll_once(mock_v_loader, mock_s_loader)
    assert updated is False
    assert holder.current.version == 5  # Keeps last good snapshot


@pytest.mark.asyncio
async def test_snapshot_fail_safe_timeout():
    holder = SnapshotHolder(fail_safe_timeout=60.0)
    # Give it an active policy
    pol = Policy(
        policy_id="pol_1",
        requested_model="gpt-4o",
        target_model="gpt-4o-mini",
        workflow_sig="wf",
        template_ids=["tpl"],
        scaffold=Scaffold(),
        expected_nonloss=0.8,
        expected_savings_pct=0.5,
        created_at="2026-01-01T00:00:00Z",
        expires_at="2026-01-02T00:00:00Z",
    )
    holder.current = Snapshot(version=1, policies_active=[pol], modes={}, global_kill=True)
    holder.indexed = SnapshotIndex(holder.current)

    # Within 60s -> returns active index
    assert len(holder.get_index().snapshot.policies_active) == 1

    # Simulate DB unreachable for 65 seconds
    holder.last_success_ts = holder.last_success_ts - 65.0

    # Fail-safe triggered: policies cleared to prevent misrouting, global_kill reset to False
    safe_idx = holder.get_index()
    assert len(safe_idx.snapshot.policies_active) == 0
    assert safe_idx.snapshot.global_kill is False


@pytest.mark.asyncio
async def test_snapshot_start_and_stop():
    holder = SnapshotHolder()
    mock_v_loader = AsyncMock(return_value=1)
    mock_s_loader = AsyncMock(return_value=Snapshot(version=1))

    holder.start(mock_v_loader, mock_s_loader, poll_interval=0.01)
    await asyncio.sleep(0.05)
    holder.stop()

    assert holder.current.version == 1
    assert mock_v_loader.call_count >= 1
