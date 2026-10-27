"""In-memory atomic policy snapshot holder with background polling and fail-safe cache."""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from gateway_harness.contracts import Snapshot
from gateway_harness.policy.matcher import SnapshotIndex

logger = logging.getLogger("gateway_harness.snapshot")


class SnapshotHolder:
    """Thread/coroutine safe snapshot manager."""

    def __init__(self, fail_safe_timeout: float = 60.0):
        self.fail_safe_timeout = fail_safe_timeout
        self.current: Snapshot = Snapshot(version=0, policies_active=[], modes={}, global_kill=False)
        self.indexed: SnapshotIndex = SnapshotIndex(self.current)
        self.last_success_ts: float = time.time()
        self._poller_task: asyncio.Task | None = None
        self._running = False

    def get_index(self) -> SnapshotIndex:
        """Return the active index, or fail-safe pass-through if DB has been unreachable > 60s."""
        if time.time() - self.last_success_ts > self.fail_safe_timeout:
            # Fail safe: pass-through snapshot with no active policies and no global kill
            safe_snap = Snapshot(
                version=self.current.version,
                policies_active=[],
                modes=self.current.modes,
                global_kill=False,
            )
            return SnapshotIndex(safe_snap)
        return self.indexed

    async def poll_once(
        self,
        version_loader: Callable[[], Any],
        snapshot_loader: Callable[[], Any],
    ) -> bool:
        """Poll for version updates and reload snapshot if changed.

        Returns True if snapshot was updated, False otherwise.
        """
        try:
            latest_version = await version_loader()
            self.last_success_ts = time.time()

            if latest_version != self.current.version:
                new_snapshot = await snapshot_loader()
                self.current = new_snapshot
                self.indexed = SnapshotIndex(new_snapshot)
                self.last_success_ts = time.time()
                logger.info(
                    "Reloaded policy snapshot v%s (%d active policies)",
                    new_snapshot.version,
                    len(new_snapshot.policies_active),
                )
                return True
            return False
        except Exception as exc:
            logger.warning("Failed to refresh policy snapshot: %s", exc)
            return False

    async def _poll_loop(
        self,
        poll_interval: float,
        version_loader: Callable[[], Any],
        snapshot_loader: Callable[[], Any],
    ) -> None:
        while self._running:
            await self.poll_once(version_loader, snapshot_loader)
            try:
                await asyncio.sleep(poll_interval)
            except asyncio.CancelledError:
                break

    def start(
        self,
        version_loader: Callable[[], Any],
        snapshot_loader: Callable[[], Any],
        poll_interval: float = 5.0,
    ) -> None:
        """Start poller background task once."""
        if self._poller_task is not None and not self._poller_task.done():
            return
        self._running = True
        self._poller_task = asyncio.create_task(
            self._poll_loop(poll_interval, version_loader, snapshot_loader)
        )

    def stop(self) -> None:
        """Stop poller task."""
        self._running = False
        if self._poller_task and not self._poller_task.done():
            self._poller_task.cancel()


# Global singleton instance
holder = SnapshotHolder()
