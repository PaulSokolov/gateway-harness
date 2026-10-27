from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from gateway_harness.settings import Settings, get_settings


async def check_health(settings: Settings | None = None) -> dict[str, Any]:
    """Check system health, storage, spool backlog, and database reachability."""
    if settings is None:
        settings = get_settings()

    data_dir = Path(settings.DATA_DIR)
    spool_dir = data_dir / "spool"

    status = "healthy"
    checks: dict[str, Any] = {}

    # 1. Check data directory exists / writable
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        test_file = data_dir / ".healthcheck_write_test"
        test_file.touch()
        test_file.unlink()
        checks["data_dir_writable"] = True
    except Exception as e:
        checks["data_dir_writable"] = False
        checks["data_dir_error"] = str(e)
        status = "unhealthy"

    # 2. Check disk space (minimum 2 GB required)
    try:
        total, used, free = shutil.disk_usage(data_dir if data_dir.exists() else Path("/"))
        free_gb = free / (1024**3)
        checks["free_disk_gb"] = round(free_gb, 2)
        checks["disk_space_ok"] = free_gb >= 2.0
        if not checks["disk_space_ok"]:
            status = "unhealthy"
    except Exception as e:
        checks["disk_space_ok"] = False
        checks["disk_error"] = str(e)
        status = "unhealthy"

    # 3. Check spool backlog (< 1000 files)
    try:
        if spool_dir.exists():
            spool_files = [f for f in os.listdir(spool_dir) if f.endswith(".jsonl.ready")]
            backlog_count = len(spool_files)
        else:
            backlog_count = 0
        checks["spool_backlog"] = backlog_count
        checks["spool_backlog_ok"] = backlog_count < 1000
        if not checks["spool_backlog_ok"]:
            status = "degraded"
    except Exception as e:
        checks["spool_backlog_ok"] = False
        checks["spool_error"] = str(e)
        status = "degraded"

    # 4. Check Postgres reachability if configured
    if settings.DATABASE_URL:
        try:
            import asyncpg

            conn = await asyncpg.connect(settings.DATABASE_URL, timeout=3.0)
            await conn.execute("SELECT 1")
            await conn.close()
            checks["database_connected"] = True
        except Exception as e:
            checks["database_connected"] = False
            checks["database_error"] = str(e)
            status = "unhealthy"
    else:
        checks["database_connected"] = None
        checks["database_note"] = "DATABASE_URL not configured"

    return {
        "status": status,
        "checks": checks,
    }
