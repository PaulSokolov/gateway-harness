from unittest.mock import AsyncMock, patch

import pytest

from gateway_harness.demo.chaos import inject_quality_degradation
from gateway_harness.demo.fast_forward import seed_demo_traffic
from gateway_harness.ledger.store import LedgerStore


def test_seed_demo_traffic(tmp_path):
    store = LedgerStore(tmp_path / "ledger.duckdb")
    count = seed_demo_traffic(store, total_requests=60)
    assert count == 60

    con = store.connect()
    total = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert total == 60


@pytest.mark.asyncio
async def test_inject_chaos(tmp_path):
    store = LedgerStore(tmp_path / "ledger.duckdb")

    with patch(
        "gateway_harness.demo.chaos.run_tripwire_check",
        new_callable=AsyncMock,
        return_value=["pol_target"],
    ):
        disabled = await inject_quality_degradation(store, policy_id="pol_target", failure_count=5)

    assert "pol_target" in disabled
    con = store.connect()
    canary_failures = con.execute(
        "SELECT COUNT(*) FROM canary_results WHERE policy_id = 'pol_target'"
    ).fetchone()[0]
    assert canary_failures == 5
