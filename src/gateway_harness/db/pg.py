"""PostgreSQL connection pool and schema migration runner for Gateway-Harness."""

import asyncio
import sys
from pathlib import Path
from typing import Any

import asyncpg

from gateway_harness.settings import get_settings

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


async def get_pool(dsn: str | None = None, **kwargs: Any) -> asyncpg.Pool:
    """Get or create singleton asyncpg connection pool."""
    global _pool
    if _pool is not None and not _pool._closed:
        return _pool

    async with _pool_lock:
        if _pool is not None and not _pool._closed:
            return _pool

        target_dsn = dsn or get_settings().DATABASE_URL
        if not target_dsn:
            raise ValueError("DATABASE_URL must be configured")

        _pool = await asyncpg.create_pool(
            dsn=target_dsn,
            min_size=kwargs.get("min_size", 2),
            max_size=kwargs.get("max_size", 10),
        )
        return _pool


async def close_pool() -> None:
    """Close the global pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def migrate(dsn: str | None = None, migrations_dir: Path | None = None) -> int:
    """Apply *.sql migration files in order inside a transaction.

    Returns the number of applied migrations.
    """
    target_dsn = dsn or get_settings().DATABASE_URL
    if not target_dsn:
        raise ValueError("DATABASE_URL must be configured")

    if migrations_dir is None:
        # Default to appliance/migrations/postgres
        migrations_dir = Path(__file__).resolve().parent.parent.parent.parent / "migrations" / "postgres"

    if not migrations_dir.is_dir():
        return 0

    sql_files = sorted(migrations_dir.glob("*.sql"))
    if not sql_files:
        return 0

    conn = await asyncpg.connect(target_dsn)
    applied_count = 0
    try:
        # Ensure migration table exists
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gh_schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        rows = await conn.fetch("SELECT version FROM gh_schema_version")
        applied_versions = {r["version"] for r in rows}

        for file in sql_files:
            # File format: 0001_name.sql
            version_str = file.name.split("_")[0]
            if not version_str.isdigit():
                continue
            ver = int(version_str)
            if ver in applied_versions:
                continue

            sql_content = file.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql_content)
                await conn.execute(
                    """
                    INSERT INTO gh_schema_version (version, applied_at)
                    VALUES ($1, NOW())
                    ON CONFLICT (version) DO NOTHING
                    """,
                    ver,
                )
            applied_count += 1
    finally:
        await conn.close()

    return applied_count


def run_cli() -> None:
    """CLI dispatcher for db migrations."""
    if len(sys.argv) > 1 and sys.argv[1] == "migrate":
        count = asyncio.run(migrate())
        print(f"PostgreSQL migration completed. Applied {count} migrations.")
    else:
        print("Usage: python -m gateway_harness.db.pg migrate")


if __name__ == "__main__":
    run_cli()
