import asyncio
import json

import pytest

from gateway_harness.capture.spool import SpoolWriter


@pytest.mark.asyncio
async def test_spool_5000_records(tmp_path):
    writer = SpoolWriter(tmp_path, max_bytes=100 * 1024, max_age_s=60.0, queue_max=10000)

    for i in range(5000):
        assert writer.submit({"id": i, "data": "payload_test_data"}) is True

    await writer.close()

    ready_files = list(tmp_path.glob("*.jsonl.ready"))
    assert len(ready_files) >= 1

    total_lines = 0
    for rf in ready_files:
        with open(rf, encoding="utf-8") as f:
            lines = f.readlines()
            total_lines += len(lines)
            for line in lines:
                data = json.loads(line)
                assert "id" in data

    assert total_lines == 5000


@pytest.mark.asyncio
async def test_spool_queue_full_drops(tmp_path):
    # Queue size 2
    writer = SpoolWriter(tmp_path, queue_max=2)
    # Stop background task by not starting it, filling queue
    assert writer.submit({"id": 1}) is True
    assert writer.submit({"id": 2}) is True
    assert writer.submit({"id": 3}) is False
    assert writer.dropped_count == 1

    await writer.close()


@pytest.mark.asyncio
async def test_spool_rotation_by_age(tmp_path, monkeypatch):
    current_time = 1000.0

    def fake_time():
        nonlocal current_time
        return current_time

    monkeypatch.setattr("time.time", fake_time)

    # Max age 5.0 seconds
    writer = SpoolWriter(tmp_path, max_bytes=10 * 1024 * 1024, max_age_s=5.0)

    assert writer.submit({"msg": "batch1"}) is True
    await asyncio.sleep(0.05)

    # Advance time past max_age_s
    current_time += 6.0
    assert writer.submit({"msg": "batch2"}) is True
    await asyncio.sleep(0.05)

    await writer.close()

    ready_files = list(tmp_path.glob("*.jsonl.ready"))
    # Two batches separated by time > max_age_s should have produced at least 2 rotated files
    assert len(ready_files) >= 2
