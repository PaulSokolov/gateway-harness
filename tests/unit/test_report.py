from datetime import UTC, datetime

from gateway_harness.contracts import Fingerprint, TraceEvent
from gateway_harness.funnel.report import format_report_markdown, generate_report
from gateway_harness.ingest.ingester import EVENT_COLUMNS
from gateway_harness.ledger.store import LedgerStore


def test_generate_report_end_to_end(tmp_path):
    ledger_dir = tmp_path / "ledger"
    cfg_file = tmp_path / "litellm.yaml"
    cfg_file.write_text(
        """
model_list:
  - model_name: claude-3-5-sonnet
    litellm_params:
      model: anthropic/claude-3-5-sonnet
  - model_name: gemini-2.5-flash
    litellm_params:
      model: google/gemini-2.5-flash
"""
    )

    store = LedgerStore(ledger_dir, read_only=False)
    con = store.con

    now = datetime.now(UTC)
    fp = Fingerprint(template_id="tpl_extract", workflow_sig="sig_extract", shape="one_shot_templated")

    cols_str = ", ".join(EVENT_COLUMNS)
    for i in range(250):
        ev = TraceEvent(
            event_id=f"ev_{i}",
            ts=now,
            tenant_id="tenant_alpha",
            api_key_hash="hash1",
            call_type="chat_completion",
            stream=False,
            requested_model="claude-3-5-sonnet",
            served_model="claude-3-5-sonnet",
            status="success",
            prompt_tokens=800,
            completion_tokens=300,
            cost_usd=0.015,
            latency_ms=400.0,
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

    report = generate_report(store, cfg_file)
    assert report["summary"]["total_requests"] == 250
    assert report["summary"]["total_spend_usd"] > 0
    assert "one_shot_templated" in report["spend_share_by_shape"]
    assert len(report["clusters"]) == 1

    md = format_report_markdown(report)
    assert "# LLM Traffic & Savings Opportunity Report" in md
    assert "Executive Summary" in md
    assert "one_shot_templated" in md

    store.close()
