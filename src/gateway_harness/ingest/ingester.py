from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from gateway_harness.contracts import Payload, TraceEvent
from gateway_harness.ledger.store import LedgerStore

logger = logging.getLogger(__name__)

EVENT_COLUMNS = [
    "event_id",
    "ts",
    "tenant_id",
    "api_key_hash",
    "session_id",
    "call_type",
    "stream",
    "requested_model",
    "served_model",
    "provider",
    "status",
    "error_class",
    "finish_reason",
    "prompt_tokens",
    "completion_tokens",
    "cached_tokens",
    "cost_usd",
    "latency_ms",
    "ttft_ms",
    "optimized",
    "policy_id",
    "canary",
    "internal",
    "has_tools",
    "has_images",
    "response_format",
    "n_messages",
    "fp_version",
    "fp_template_id",
    "fp_workflow_sig",
    "fp_shape",
    "request_hash",
    "response_hash",
]


def ingest_once(spool_dir: Path | str, ledger_dir: Path | str) -> int:
    """Ingest ready spool files into Parquet archives and DuckDB tables."""
    spool_path = Path(spool_dir)
    ledger_path = Path(ledger_dir)
    parquet_base = ledger_path / "parquet" / "events"
    errors_file = ledger_path / "errors.jsonl"

    if not spool_path.exists():
        return 0

    store = LedgerStore(ledger_path, read_only=False)
    con = store.con

    ready_files = sorted(spool_path.glob("*.jsonl.ready"))
    total_ingested = 0

    for file_path in ready_files:
        filename = file_path.name
        # Check idempotency
        already_processed = con.execute(
            "SELECT 1 FROM ingested_files WHERE filename = ?", [filename]
        ).fetchone()
        if already_processed:
            file_path.unlink(missing_ok=True)
            continue

        valid_events: list[dict[str, Any]] = []
        valid_payloads: list[dict[str, Any]] = []
        events_by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)

        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    record = json.loads(line_str)
                    raw_event = record.get("event")
                    event = TraceEvent.model_validate(raw_event)

                    ev_dict = event.model_dump()
                    fp = ev_dict.pop("fingerprint", {})
                    ev_dict["fp_version"] = fp.get("version", 1)
                    ev_dict["fp_template_id"] = fp.get("template_id", "")
                    ev_dict["fp_workflow_sig"] = fp.get("workflow_sig", "")
                    ev_dict["fp_shape"] = fp.get("shape", "")

                    valid_events.append(ev_dict)

                    date_str = event.ts.strftime("%Y-%m-%d")
                    events_by_date[date_str].append(ev_dict)

                    for raw_payload in record.get("payloads", []):
                        payload = Payload.model_validate(raw_payload)
                        valid_payloads.append(
                            {
                                "hash": payload.hash,
                                "kind": payload.kind,
                                "body": json.dumps(payload.body),
                            }
                        )

                except Exception as e:
                    logger.warning("Corrupt line in %s: %s", filename, e)
                    with open(errors_file, "a", encoding="utf-8") as ef:
                        ef.write(line_str + "\n")

        # 1. Write partitioned Parquet files
        for date_str, ev_list in events_by_date.items():
            date_dir = parquet_base / f"date={date_str}"
            date_dir.mkdir(parents=True, exist_ok=True)
            part_file = date_dir / f"{uuid.uuid4().hex}.parquet"

            table = pa.Table.from_pylist(ev_list)
            pq.write_table(table, str(part_file), compression="zstd")

        # 2. Ingest payloads into DuckDB
        if valid_payloads:
            payload_table = pa.Table.from_pylist(valid_payloads)
            con.register("temp_payloads", payload_table)
            con.execute(
                """
                INSERT OR IGNORE INTO payloads (hash, kind, body)
                SELECT hash, kind, body FROM temp_payloads
            """
            )
            con.unregister("temp_payloads")

        # 3. Ingest events into DuckDB
        if valid_events:
            cols_str = ", ".join(EVENT_COLUMNS)
            event_table = pa.Table.from_pylist(valid_events)
            con.register("temp_events", event_table)
            con.execute(
                f"""
                INSERT OR IGNORE INTO events ({cols_str})
                SELECT {cols_str} FROM temp_events
            """
            )
            con.unregister("temp_events")

        # 4. Mark file ingested
        con.execute(
            "INSERT INTO ingested_files (filename, event_count) VALUES (?, ?)",
            [filename, len(valid_events)],
        )

        total_ingested += len(valid_events)
        file_path.unlink(missing_ok=True)

    store.close()
    return total_ingested
