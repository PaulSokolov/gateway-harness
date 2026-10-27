import pytest

from gateway_harness.admin.health import check_health
from gateway_harness.settings import Settings


@pytest.mark.asyncio
async def test_health_check_local(tmp_path):
    settings = Settings(DATA_DIR=tmp_path, DATABASE_URL=None)
    health = await check_health(settings)

    assert health["status"] == "healthy"
    checks = health["checks"]
    assert checks["data_dir_writable"] is True
    assert checks["disk_space_ok"] is True
    assert checks["spool_backlog_ok"] is True
    assert checks["database_connected"] is None


@pytest.mark.asyncio
async def test_health_check_spool_backlog(tmp_path):
    spool_dir = tmp_path / "spool"
    spool_dir.mkdir(parents=True)
    # Create 1005 mock ready files to trigger degraded status
    for i in range(1005):
        (spool_dir / f"file_{i}.jsonl.ready").touch()

    settings = Settings(DATA_DIR=tmp_path, DATABASE_URL=None)
    health = await check_health(settings)

    assert health["status"] == "degraded"
    assert health["checks"]["spool_backlog"] == 1005
    assert health["checks"]["spool_backlog_ok"] is False
