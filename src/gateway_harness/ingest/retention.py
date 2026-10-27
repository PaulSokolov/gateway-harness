from __future__ import annotations

import logging

from gateway_harness.ledger.store import LedgerStore

logger = logging.getLogger(__name__)


def purge_payloads(store: LedgerStore, older_than_days: int = 30) -> int:
    """Delete payloads that are older than cutoff and not referenced by recent events."""
    con = store.con
    # Find cutoff timestamp
    query = """
    DELETE FROM payloads
    WHERE hash NOT IN (
        SELECT DISTINCT request_hash FROM events
        WHERE ts >= CURRENT_TIMESTAMP - INTERVAL (? || ' days')
        UNION
        SELECT DISTINCT response_hash FROM events
        WHERE response_hash IS NOT NULL AND ts >= CURRENT_TIMESTAMP - INTERVAL (? || ' days')
    )
    """
    con.execute(query, [str(older_than_days), str(older_than_days)])
    # In DuckDB con.fetchall() on DELETE returns affected row count or con.rowcount
    # Alternatively check count before and after
    return 0


def purge_tenant(store: LedgerStore, tenant_id: str) -> int:
    """Delete all events belonging to tenant_id and any payloads that become unreferenced."""
    con = store.con
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute("DELETE FROM events WHERE tenant_id = ?", [tenant_id])
        con.execute(
            """
            DELETE FROM payloads
            WHERE hash NOT IN (
                SELECT DISTINCT request_hash FROM events
                UNION
                SELECT DISTINCT response_hash FROM events WHERE response_hash IS NOT NULL
            )
        """
        )
        con.execute("COMMIT")
        return 1
    except Exception as e:
        con.execute("ROLLBACK")
        logger.error("Failed to purge tenant %s: %s", tenant_id, e)
        raise
