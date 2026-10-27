import json
from pathlib import Path

import pytest

from gateway_harness.capture.hook import CaptureMixin
from gateway_harness.capture.spool import SpoolWriter
from gateway_harness.contracts import TraceEvent


class DummyLogger(CaptureMixin):
    pass


@pytest.mark.asyncio
async def test_capture_hook_success_fixtures(tmp_path, monkeypatch):
    writer = SpoolWriter(tmp_path)
    monkeypatch.setattr("gateway_harness.capture.hook.get_spool_writer", lambda: writer)

    fixtures_dir = Path(__file__).parent.parent / "fixtures"
    with open(fixtures_dir / "slo_success.json") as f:
        slo_success = json.load(f)

    with open(fixtures_dir / "slo_stream.json") as f:
        slo_stream = json.load(f)

    handler = DummyLogger()

    # 1. Non-streaming event
    await handler.async_log_success_event(
        {"standard_logging_object": slo_success},
        response_obj=None,
        start_time=1.0,
        end_time=1.5,
    )

    # 2. Streaming event
    await handler.async_log_success_event(
        {"standard_logging_object": slo_stream},
        response_obj=None,
        start_time=2.0,
        end_time=2.5,
    )

    await writer.close()

    ready_files = list(tmp_path.glob("*.jsonl.ready"))
    assert len(ready_files) >= 1

    records = []
    for rf in ready_files:
        with open(rf, encoding="utf-8") as f:
            for line in f:
                records.append(json.loads(line))

    assert len(records) == 2

    ev0 = TraceEvent.model_validate(records[0]["event"])
    assert ev0.requested_model == "spike-dst"
    assert ev0.optimized is True
    assert ev0.policy_id == "pol_test"
    assert ev0.stream is False
    assert len(records[0]["payloads"]) == 2  # request + response

    ev1 = TraceEvent.model_validate(records[1]["event"])
    assert ev1.optimized is True
    assert ev1.stream is True
    assert len(records[1]["payloads"]) == 2
