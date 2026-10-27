import json
from datetime import UTC, datetime

from gateway_harness.contracts import Fingerprint, Payload, TraceEvent
from gateway_harness.ingest.ingester import ingest_once
from gateway_harness.ledger.store import LedgerStore


def _make_dummy_record(i: int) -> dict:
    now = datetime.now(UTC)
    fp = Fingerprint(template_id=f"tpl_{i}", workflow_sig="sig_test", shape="one_shot_templated")
    ev = TraceEvent(
        event_id=f"evt_{i}",
        ts=now,
        tenant_id="tenant_x",
        api_key_hash="hash123",
        call_type="chat_completion",
        stream=False,
        requested_model="claude-3-5-sonnet",
        served_model="gemini-2.5-flash",
        status="success",
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=0.001,
        latency_ms=300.0,
        fingerprint=fp,
        request_hash=f"req_{i % 5}",  # duplicate requests test deduplication
        response_hash=f"resp_{i}",
    )
    p1 = Payload(hash=f"req_{i % 5}", kind="request", body={"msg": f"query {i % 5}"})
    p2 = Payload(hash=f"resp_{i}", kind="response", body={"reply": f"answer {i}"})
    return {
        "event": ev.model_dump(mode="json"),
        "payloads": [p1.model_dump(mode="json"), p2.model_dump(mode="json")],
    }


def test_ingest_once_idempotency_and_corrupt_lines(tmp_path):
    spool_dir = tmp_path / "spool"
    ledger_dir = tmp_path / "ledger"
    spool_dir.mkdir(parents=True)

    # 1. Create a spool file with 20 valid lines and 2 corrupt lines
    file_path = spool_dir / "test-1.jsonl.ready"
    with open(file_path, "w", encoding="utf-8") as f:
        for i in range(10):
            f.write(json.dumps(_make_dummy_record(i)) + "\n")
        f.write("{corrupt json line\n")
        for i in range(10, 20):
            f.write(json.dumps(_make_dummy_record(i)) + "\n")
        f.write('{"event": "missing fields"}\n')

    # Run ingestion
    ingested = ingest_once(spool_dir, ledger_dir)
    assert ingested == 20

    # Spool file should have been unlinked
    assert not file_path.exists()

    # Errors file should contain 2 corrupt lines
    errors_file = ledger_dir / "errors.jsonl"
    assert errors_file.exists()
    with open(errors_file) as f:
        err_lines = f.readlines()
        assert len(err_lines) == 2

    # Check database contents
    store = LedgerStore(ledger_dir, read_only=True)
    events_count = store.con.execute("SELECT count(*) FROM events").fetchone()[0]
    payloads_count = store.con.execute("SELECT count(*) FROM payloads").fetchone()[0]
    assert events_count == 20
    # 5 unique requests + 20 responses = 25 payloads
    assert payloads_count == 25
    store.close()

    # Parquet files should exist
    parquet_files = list((ledger_dir / "parquet" / "events").glob("*/*.parquet"))
    assert len(parquet_files) >= 1
