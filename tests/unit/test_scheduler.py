import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway_harness.ledger.store import LedgerStore
from gateway_harness.worker.scheduler import WorkerScheduler


@pytest.mark.asyncio
async def test_scheduler_jobs_fire(tmp_path):
    store = LedgerStore(tmp_path / "ledger.duckdb")
    sched = WorkerScheduler(
        store=store,
        ingest_interval=0.01,
        canary_interval=0.01,
        monitor_interval=0.01,
        retention_interval=0.01,
    )

    with (
        patch.object(sched, "_job_ingest", new_callable=AsyncMock) as mock_ingest,
        patch.object(sched, "_job_canary", new_callable=AsyncMock) as mock_canary,
        patch.object(sched, "_job_monitor", new_callable=AsyncMock) as mock_monitor,
        patch.object(sched, "_job_retention", new_callable=AsyncMock) as mock_retention,
        patch("gateway_harness.worker.scheduler.get_pool", side_effect=RuntimeError("no pg")),
    ):
        task = asyncio.create_task(sched.start())
        await asyncio.sleep(0.04)
        sched.stop()
        await task

    assert mock_ingest.call_count >= 1
    assert mock_canary.call_count >= 1
    assert mock_monitor.call_count >= 1
    assert mock_retention.call_count >= 1


@pytest.mark.asyncio
async def test_scheduler_advisory_lock_contention(tmp_path):
    store = LedgerStore(tmp_path / "ledger.duckdb")
    sched = WorkerScheduler(store=store)

    # Mock pool returning lock=False (another worker holds lock)
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = [False]
    mock_pool.acquire = AsyncMock(return_value=mock_conn)
    mock_pool.release = AsyncMock()

    with patch("gateway_harness.worker.scheduler.get_pool", return_value=mock_pool):
        await sched.start()

    # Did not start tasks because lock was refused
    assert sched._running is False
    assert len(sched._tasks) == 0
