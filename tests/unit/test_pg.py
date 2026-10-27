from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway_harness.db.pg import migrate


@pytest.mark.asyncio
async def test_migrate_logic(tmp_path):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    f1 = migrations_dir / "0001_init.sql"
    f1.write_text("CREATE TABLE gh_test1 (id INT);", encoding="utf-8")
    f2 = migrations_dir / "0002_add_col.sql"
    f2.write_text("ALTER TABLE gh_test1 ADD COLUMN name TEXT;", encoding="utf-8")

    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = [{"version": 1}]  # 1 already applied
    mock_tx = AsyncMock()
    mock_conn.transaction = MagicMock(return_value=mock_tx)

    with patch("asyncpg.connect", return_value=mock_conn):
        applied = await migrate(dsn="postgresql://user:pass@localhost:5432/db", migrations_dir=migrations_dir)

    assert applied == 1
    # Verify execute was called for 0002
    assert any("ALTER TABLE gh_test1" in str(call) for call in mock_conn.execute.call_args_list)
