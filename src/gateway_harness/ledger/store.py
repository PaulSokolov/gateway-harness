from __future__ import annotations

from pathlib import Path

import duckdb


class LedgerStore:
    """Embedded DuckDB analytical store for telemetry events and deduplicated payloads."""

    def __init__(self, ledger_dir: Path | str, read_only: bool = False) -> None:
        self.ledger_dir = Path(ledger_dir)
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.ledger_dir / "ledger.duckdb"
        self.read_only = read_only

        self.con = duckdb.connect(str(self.db_path), read_only=read_only)
        if not read_only:
            self.apply_migrations()

    def apply_migrations(self) -> None:
        """Apply all SQL migration scripts in order."""
        migrations_dir = Path(__file__).parent.parent.parent.parent / "migrations" / "duckdb"
        if not migrations_dir.exists():
            # Try relative to package root
            migrations_dir = Path(__file__).resolve().parents[3] / "migrations" / "duckdb"

        if migrations_dir.exists():
            for sql_file in sorted(migrations_dir.glob("*.sql")):
                sql = sql_file.read_text(encoding="utf-8")
                self.con.execute(sql)

    def connect(self) -> duckdb.DuckDBPyConnection:
        """Return the DuckDB connection."""
        return self.con

    def close(self) -> None:
        """Close connection."""
        self.con.close()
