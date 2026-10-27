"""Automated tripwire circuit breaker monitoring canary quality and production regression."""

import logging
from datetime import UTC, datetime

import asyncpg

from gateway_harness.ledger.store import LedgerStore
from gateway_harness.metrics import CANARY_TRIPWIRE_TOTAL
from gateway_harness.policy.snapshot import holder
from gateway_harness.policy.store import disable_policy
from gateway_harness.probe.stats import wilson

logger = logging.getLogger("gateway_harness.canary.monitor")


async def run_tripwire_check(
    store: LedgerStore,
    delta: float = 0.05,
    pool: asyncpg.Pool | None = None,
) -> list[str]:
    """Inspect all active policies for quality regressions, validator failures, or expiration.

    Returns list of disabled policy_ids.
    """
    snapshot = holder.current
    now = datetime.now(UTC)
    con = store.connect()
    disabled: list[str] = []

    for policy in snapshot.policies_active:
        pid = policy.policy_id

        # 1. Expiration Check
        if policy.expires_at and policy.expires_at <= now:
            logger.warning("Tripwire disabling expired policy %s", pid)
            try:
                await disable_policy(pid, actor="tripwire", reason="expired", pool=pool)
                CANARY_TRIPWIRE_TOTAL.labels(reason="expired").inc()
                disabled.append(pid)
                continue
            except Exception as e:
                logger.error("Failed to disable policy %s: %s", pid, e)

        # 2. Canary Quality Check (Last 200 verdicts)
        canary_rows = con.execute(
            """
            SELECT verdict
            FROM canary_results
            WHERE policy_id = ?
            ORDER BY evaluated_at DESC
            LIMIT 200
            """,
            [pid],
        ).fetchall()

        if len(canary_rows) >= 20:
            k = sum(1 for r in canary_rows if r[0] in ("win", "tie"))
            n = len(canary_rows)
            _, hi = wilson(k, n)
            threshold = policy.expected_nonloss - (2 * delta)

            if hi < threshold:
                logger.warning(
                    "Tripwire triggered: canary quality regression for %s (hi=%0.2f < thresh=%0.2f)",
                    pid,
                    hi,
                    threshold,
                )
                try:
                    await disable_policy(pid, actor="tripwire", reason="canary_quality", pool=pool)
                    CANARY_TRIPWIRE_TOTAL.labels(reason="canary_quality").inc()
                    disabled.append(pid)
                    continue
                except Exception as e:
                    logger.error("Failed to disable policy %s: %s", pid, e)

        # 3. Deterministic Validator Regression (Zero-LLM on production events in last hour)
        prod_stats = con.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(
                    CASE
                        WHEN finish_reason = 'length' OR error_class IS NOT NULL OR status = 'failure'
                        THEN 1
                        ELSE 0
                    END
                ) AS failures
            FROM events
            WHERE policy_id = ?
              AND ts >= NOW() - INTERVAL 1 HOUR
            """,
            [pid],
        ).fetchone()

        if prod_stats and prod_stats[0] >= 20:
            total_prod = prod_stats[0]
            failures = prod_stats[1] or 0
            fail_rate = failures / total_prod

            # If failure rate exceeds 10% and is elevated
            if fail_rate > 0.10:
                logger.warning(
                    "Tripwire triggered: validator regression for %s (rate=%0.2f > 0.10)",
                    pid,
                    fail_rate,
                )
                try:
                    await disable_policy(
                        pid,
                        actor="tripwire",
                        reason="validator_regression",
                        pool=pool,
                    )
                    CANARY_TRIPWIRE_TOTAL.labels(reason="validator_regression").inc()
                    disabled.append(pid)
                    continue
                except Exception as e:
                    logger.error("Failed to disable policy %s: %s", pid, e)

    return disabled
