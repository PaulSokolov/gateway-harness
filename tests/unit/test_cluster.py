from datetime import UTC, datetime

from gateway_harness.contracts import Fingerprint, TraceEvent
from gateway_harness.funnel.cluster import build_clusters
from gateway_harness.ingest.ingester import EVENT_COLUMNS
from gateway_harness.ledger.store import LedgerStore


def test_build_clusters_aggregation(tmp_path):
    store = LedgerStore(tmp_path, read_only=False)
    con = store.con

    now = datetime.now(UTC)
    fp = Fingerprint(template_id="tpl_search", workflow_sig="sig_search", shape="one_shot_templated")

    cols_str = ", ".join(EVENT_COLUMNS)
    for i in range(15):
        ev = TraceEvent(
            event_id=f"ev_{i}",
            ts=now,
            tenant_id="tenant_1",
            api_key_hash="hash1",
            call_type="chat_completion",
            stream=False,
            requested_model="claude-3-5-sonnet",
            served_model="claude-3-5-sonnet",
            status="success",
            prompt_tokens=100 + i,
            completion_tokens=50,
            cost_usd=0.01,
            latency_ms=250.0,
            fingerprint=fp,
            request_hash="req1",
            response_hash="resp1",
        )
        d = ev.model_dump()
        fp_dict = d.pop("fingerprint", {})
        d["fp_version"] = fp_dict.get("version", 1)
        d["fp_template_id"] = fp_dict.get("template_id", "")
        d["fp_workflow_sig"] = fp_dict.get("workflow_sig", "")
        d["fp_shape"] = fp_dict.get("shape", "")
        vals = [d[c] for c in EVENT_COLUMNS]
        placeholders = ", ".join(["?"] * len(EVENT_COLUMNS))
        con.execute(f"INSERT INTO events ({cols_str}) VALUES ({placeholders})", vals)

    clusters = build_clusters(store, window_days=30)
    assert len(clusters) == 1
    c = clusters[0]
    assert c.count == 15
    assert c.tenant_id == "tenant_1"
    assert c.requested_model == "claude-3-5-sonnet"
    assert c.template_id == "tpl_search"
    assert abs(c.total_cost - 0.15) < 1e-4
    assert c.shape_mode == "one_shot_templated"
    assert c.error_rate == 0.0

    store.close()
