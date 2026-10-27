from __future__ import annotations

import asyncio
import json
import os
import socket
import time
from pathlib import Path
from typing import Any


class SpoolWriter:
    """Non-blocking memory-buffered spool writer that rotates files on size or age."""

    def __init__(
        self,
        directory: Path | str,
        max_bytes: int = 32 * 1024 * 1024,  # 32 MB default
        max_age_s: float = 60.0,
        queue_max: int = 10000,
    ) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes
        self.max_age_s = max_age_s
        self.queue_max = queue_max

        self.queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=queue_max)
        self.dropped_count: int = 0
        self._worker_task: asyncio.Task[None] | None = None
        self._closed: bool = False

        self._current_file: Any = None
        self._current_tmp_path: Path | None = None
        self._current_file_bytes: int = 0
        self._file_start_time: float = 0.0

        self._hostname = socket.gethostname()
        self._pid = os.getpid()

    def submit(self, record: dict[str, Any]) -> bool:
        """Non-blocking enqueue of trace records. Returns False if queue is saturated."""
        if self._closed:
            return False

        # Lazy start background drain worker on active event loop
        if self._worker_task is None or self._worker_task.done():
            try:
                loop = asyncio.get_running_loop()
                self._worker_task = loop.create_task(self._drain_loop())
            except RuntimeError:
                pass  # No running event loop

        try:
            self.queue.put_nowait(record)
            return True
        except asyncio.QueueFull:
            self.dropped_count += 1
            return False

    def _open_new_file(self) -> None:
        """Create a new temporary segment file."""
        now = time.time()
        filename = f"{self._hostname}-{self._pid}-{int(now * 1000)}.jsonl.tmp"
        self._current_tmp_path = self.directory / filename
        self._current_file = open(self._current_tmp_path, "a", encoding="utf-8")
        self._current_file_bytes = 0
        self._file_start_time = now

    def _rotate_current_file(self) -> None:
        """Flush, fsync, close, and atomically rename temporary file to .ready."""
        if self._current_file is not None and self._current_tmp_path is not None:
            self._current_file.flush()
            os.fsync(self._current_file.fileno())
            self._current_file.close()
            self._current_file = None

            if self._current_file_bytes > 0 and self._current_tmp_path.exists():
                ready_path = self._current_tmp_path.with_name(
                    self._current_tmp_path.name.replace(".jsonl.tmp", ".jsonl.ready")
                )
                self._current_tmp_path.rename(ready_path)
            elif self._current_tmp_path.exists():
                self._current_tmp_path.unlink()

            self._current_tmp_path = None
            self._current_file_bytes = 0

    def _write_record(self, record: dict[str, Any]) -> None:
        now = time.time()
        if self._current_file is None:
            self._open_new_file()
        elif self._current_file_bytes >= self.max_bytes or (now - self._file_start_time) >= self.max_age_s:
            self._rotate_current_file()
            self._open_new_file()

        line = json.dumps(record, default=str) + "\n"
        encoded = line.encode("utf-8")
        assert self._current_file is not None
        self._current_file.write(line)
        self._current_file_bytes += len(encoded)

    async def _drain_loop(self) -> None:
        """Continuously drain queue in background."""
        while True:
            try:
                # Timeout to enforce max_age_s rotation even on low traffic
                record = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except TimeoutError:
                if self._current_file is not None and (time.time() - self._file_start_time) >= self.max_age_s:
                    await asyncio.to_thread(self._rotate_current_file)
                continue

            if record is None:
                # Shutdown sentinel
                self.queue.task_done()
                break

            await asyncio.to_thread(self._write_record, record)
            self.queue.task_done()

        # Flush remaining on shutdown
        await asyncio.to_thread(self._rotate_current_file)

    async def close(self) -> None:
        """Gracefully drain remaining records and close."""
        self._closed = True
        if self._worker_task is not None and not self._worker_task.done():
            await self.queue.put(None)
            await self._worker_task
        elif self._current_file is not None:
            await asyncio.to_thread(self._rotate_current_file)
