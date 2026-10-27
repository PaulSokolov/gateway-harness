from datetime import UTC, datetime

from gateway_harness.contracts import Fingerprint, Payload, TraceEvent
from gateway_harness.ingest.ingester import EVENT_COLUMNS
from gateway_harness.ingest.retention import purge_payloads, purge_tenant
from gateway_harness.ledger.store import LedgerStore


def test_retention_and_tenant_purge(tmp_path):
    store = LedgerStore(tmp_path, read_only=False)
    con = store.con

    now = datetime.now(UTC)
    fp = Fingerprint(template_id="tpl1", workflow_sig="sig1", shape="one_shot_simple")

    # Insert events for tenant_a and tenant_b
    ev_a = TraceEvent(
        event_id="ev_a",
        ts=now,
        tenant_id="tenant_a",
        api_key_hash="hash_a",
        call_type="chat_completion",
        stream=False,
        requested_model="gpt-4o",
        served_model="gpt-4o",
        status="success",
        prompt_tokens=10,
        completion_tokens=10,
        cost_usd=0.001,
        latency_ms=100.0,
        fingerprint=fp,
        request_hash="req_a_only",
        response_hash="resp_a_only",
    )
    ev_b = TraceEvent(
        event_id="ev_b",
        ts=now,
        tenant_id="tenant_b",
        api_key_hash="hash_b",
        call_type="chat_completion",
        stream=False,
        requested_model="gpt-4o",
        served_model="gpt-4o",
        status="success",
        prompt_tokens=10,
        completion_tokens=10,
        cost_usd=0.001,
        latency_ms=100.0,
        fingerprint=fp,
        request_hash="req_shared",
        response_hash="resp_b_only",
    )

    p_a_req = Payload(hash="req_a_only", kind="request", body={"text": "a"})
    p_a_resp = Payload(hash="resp_a_only", kind="response", body={"text": "a reply"})
    p_b_resp = Payload(hash="resp_b_only", kind="response", body={"text": "b reply"})
    p_shared = Payload(hash="req_shared", kind="request", body={"text": "shared"})

    # Populate payloads
    for p in [p_a_req, p_a_resp, p_b_resp, p_shared]:
        con.execute(
            "INSERT INTO payloads (hash, kind, body) VALUES (?, ?, ?)",
            [p.hash, p.kind, p.model_dump_json()],
        )

    # Populate events
    cols_str = ", ".join(EVENT_COLUMNS)
    for ev in [ev_a, ev_b]:
        d = ev.model_dump()
        fp_dict = d.pop("fingerprint", {})
        d["fp_version"] = fp_dict.get("version", 1)
        d["fp_template_id"] = fp_dict.get("template_id", "")
        d["fp_workflow_sig"] = fp_dict.get("workflow_sig", "")
        d["fp_shape"] = fp_dict.get("shape", "")
        vals = [d[c] for c in EVENT_COLUMNS]
        placeholders = ", ".join(["?"] * len(EVENT_COLUMNS))
        con.execute(f"INSERT INTO events ({cols_str}) VALUES ({placeholders})", vals)

    assert con.execute("SELECT count(*) FROM events").fetchone()[0] == 2
    assert con.execute("SELECT count(*) FROM payloads").fetchone()[0] == 4

    # Purge tenant_a
    purge_tenant(store, "tenant_a")

    # Only ev_b remains
    assert con.execute("SELECT count(*) FROM events").fetchone()[0] == 1
    assert con.execute("SELECT tenant_id FROM events").fetchone()[0] == "tenant_b"

    # Payloads req_a_only and resp_a_only should have been pruned; req_shared and resp_b_only remain!
    remaining_hashes = {row[0] for row in con.execute("SELECT hash FROM payloads").fetchall()}
    assert remaining_hashes == {"req_shared", "resp_b_only"}

    # Test purge_payloads
    purge_payloads(store, older_than_days=30)
    store.close()
