"""Single-worker background scheduler with Postgres advisory locking and periodic jobs."""

import asyncio
import logging
import signal
from typing import Any

from gateway_harness.canary.monitor import run_tripwire_check
from gateway_harness.canary.sampler import execute_canary_evaluations
from gateway_harness.db.pg import get_pool
from gateway_harness.ingest.ingester import ingest_once
from gateway_harness.ingest.retention import purge_payloads
from gateway_harness.ledger.store import LedgerStore
from gateway_harness.probe.client import Budget, GatewayClient
from gateway_harness.settings import get_settings

logger = logging.getLogger("gateway_harness.worker.scheduler")

ADVISORY_LOCK_ID = 987654321


class WorkerScheduler:
    """Async scheduler coordinating ingest, canary testing, tripwire, and data retention."""

    def __init__(
        self,
        store: LedgerStore | None = None,
        ingest_interval: float = 10.0,
        canary_interval: float = 60.0,
        monitor_interval: float = 300.0,
        retention_interval: float = 86400.0,
    ):
        settings = get_settings()
        self.settings = settings
        self.store = store or LedgerStore(settings.DATA_DIR / "ledger")
        self.spool_dir = settings.DATA_DIR / "spool"
        self.ledger_dir = settings.DATA_DIR / "ledger"

        self.ingest_interval = ingest_interval
        self.canary_interval = canary_interval
        self.monitor_interval = monitor_interval
        self.retention_interval = retention_interval

        self.budget = Budget(limit_usd=settings.DAILY_OPTIMIZER_BUDGET_USD)
        self.client = GatewayClient(
            base_url=settings.GATEWAY_URL,
            api_key=settings.INTERNAL_KEY,
            budget=self.budget,
        )

        self._running = False
        self._tasks: list[asyncio.Task[Any]] = []

    async def _run_job_loop(self, name: str, interval: float, coro_fn: Any) -> None:
        while self._running:
            try:
                await coro_fn()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Job %s encountered error: %s", name, exc)

            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

    async def _job_ingest(self) -> None:
        count = ingest_once(self.spool_dir, self.ledger_dir)
        if count > 0:
            logger.info("Ingested %d spool batches into DuckDB", count)

    async def _job_canary(self) -> None:
        judge_model = self.settings.JUDGE_MODEL or "gpt-4o-mini"
        count = await execute_canary_evaluations(
            store=self.store,
            client=self.client,
            judge_model=judge_model,
            budget=self.budget,
            limit=25,
        )
        if count > 0:
            logger.info("Executed %d canary evaluations", count)

    async def _job_monitor(self) -> None:
        pool = None
        try:
            pool = await get_pool()
        except Exception:
            pass
        disabled = await run_tripwire_check(store=self.store, delta=self.settings.DELTA, pool=pool)
        if disabled:
            logger.warning("Tripwire circuit breaker disabled policies: %s", disabled)

    async def _job_retention(self) -> None:
        purged = purge_payloads(self.store, older_than_days=self.settings.PAYLOAD_TTL_DAYS)
        if purged > 0:
            logger.info("Purged %d expired payloads", purged)

    async def start(self) -> None:
        """Acquire Postgres advisory lock and start worker daemon loops."""
        pool = None
        conn = None
        try:
            pool = await get_pool()
            conn = await pool.acquire()
            row = await conn.fetchrow("SELECT pg_try_advisory_lock($1)", ADVISORY_LOCK_ID)
            has_lock = row[0] if row else False
            if not has_lock:
                logger.warning(
                    "Could not acquire advisory lock %d; another worker is active. Exiting.",
                    ADVISORY_LOCK_ID,
                )
                await pool.release(conn)
                return
            logger.info("Acquired worker advisory lock %d", ADVISORY_LOCK_ID)
        except Exception as exc:
            logger.warning(
                "Postgres advisory lock skipped (standalone/test mode): %s",
                exc,
            )

        self._running = True
        self._tasks = [
            asyncio.create_task(self._run_job_loop("ingest", self.ingest_interval, self._job_ingest)),
            asyncio.create_task(self._run_job_loop("canary", self.canary_interval, self._job_canary)),
            asyncio.create_task(self._run_job_loop("monitor", self.monitor_interval, self._job_monitor)),
            asyncio.create_task(
                self._run_job_loop("retention", self.retention_interval, self._job_retention)
            ),
        ]

        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            if conn and pool:
                try:
                    await conn.execute("SELECT pg_advisory_unlock($1)", ADVISORY_LOCK_ID)
                    await pool.release(conn)
                    logger.info("Released worker advisory lock")
                except Exception:
                    pass

    def stop(self) -> None:
        """Signal all tasks to cancel and stop."""
        self._running = False
        for t in self._tasks:
            if not t.done():
                t.cancel()


def run_worker() -> None:
    """CLI dispatcher for background worker daemon."""
    scheduler = WorkerScheduler()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def handle_signal(*_: Any) -> None:
        logger.info("Termination signal received; shutting down worker")
        scheduler.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            pass

    try:
        loop.run_until_complete(scheduler.start())
    finally:
        loop.close()


if __name__ == "__main__":
    run_worker()
