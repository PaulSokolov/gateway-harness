"""Time-compression demo mode fast-forwarding 10 days of production traffic into seconds."""

import json
import logging
from datetime import UTC, datetime, timedelta

from gateway_harness.ledger.store import LedgerStore

logger = logging.getLogger("gateway_harness.demo.fast_forward")


def seed_demo_traffic(store: LedgerStore, total_requests: int = 300) -> int:
    """Seed DuckDB ledger with realistic production traces spread across 10 simulated days."""
    con = store.connect()
    now = datetime.now(UTC)

    scenarios = [
        {
            "template_id": "tpl_doc_extract",
            "workflow_sig": "wf_finance_extract",
            "shape": "one_shot_templated",
            "model": "gpt-4o",
            "prompt": "Extract invoice line items and totals: Invoice #INV-2026-904 Total $1,250.00",
            "reply": '{"invoice": "INV-2026-904", "total": 1250.00}',
            "prompt_tokens": 350,
            "completion_tokens": 40,
            "cost": 0.0042,
        },
        {
            "template_id": "tpl_support_triage",
            "workflow_sig": "wf_support_triage",
            "shape": "one_shot_templated",
            "model": "gpt-4o",
            "prompt": "Classify ticket priority and category: My database server stopped responding.",
            "reply": '{"category": "database", "priority": "urgent"}',
            "prompt_tokens": 180,
            "completion_tokens": 25,
            "cost": 0.0022,
        },
        {
            "template_id": "tpl_meeting_summary",
            "workflow_sig": "wf_meeting_summary",
            "shape": "one_shot_templated",
            "model": "gpt-4o",
            "prompt": "Provide a bullet-point executive summary of this product roadmap review meeting.",
            "reply": "- Launch v1 appliance\n- Integrate canary guards\n- Roll out to Meta hackathon",
            "prompt_tokens": 800,
            "completion_tokens": 120,
            "cost": 0.0105,
        },
    ]

    inserted = 0
    for i in range(total_requests):
        sc = scenarios[i % len(scenarios)]
        ev_id = f"demo_ev_{i:04d}"

        # Spread timestamps over the last 10 days
        day_offset = (i * 10) // total_requests
        hour_offset = i % 24
        ts = now - timedelta(days=(10 - day_offset), hours=hour_offset)

        req_hash = f"req_{sc['template_id']}_{i}"
        resp_hash = f"resp_{sc['template_id']}_{i}"

        # Insert payloads
        req_body = json.dumps(
            {
                "messages": [
                    {"role": "system", "content": "You are an expert enterprise assistant."},
                    {"role": "user", "content": sc["prompt"]},
                ]
            }
        )
        resp_body = json.dumps({"choices": [{"message": {"content": sc["reply"]}}]})

        con.execute(
            "INSERT INTO payloads (hash, kind, body) VALUES (?, 'request', ?)",
            [req_hash, req_body],
        )
        con.execute(
            "INSERT INTO payloads (hash, kind, body) VALUES (?, 'response', ?)",
            [resp_hash, resp_body],
        )

        # Insert event
        con.execute(
            """
            INSERT INTO events (
                event_id, ts, tenant_id, api_key_hash, call_type, stream,
                requested_model, served_model, status, prompt_tokens,
                completion_tokens, cached_tokens, cost_usd, latency_ms,
                optimized, canary, internal, has_tools, has_images, n_messages,
                fp_version, fp_template_id, fp_workflow_sig, fp_shape,
                request_hash, response_hash
            ) VALUES (
                ?, ?, 'tenant_demo', 'key_demo', 'chat_completion', false,
                ?, ?, 'success', ?,
                ?, 0, ?, 180,
                false, false, false, false, false, 2,
                1, ?, ?, ?,
                ?, ?
            )
            """,
            [
                ev_id,
                ts.strftime("%Y-%m-%d %H:%M:%S"),
                sc["model"],
                sc["model"],
                sc["prompt_tokens"],
                sc["completion_tokens"],
                sc["cost"],
                sc["template_id"],
                sc["workflow_sig"],
                sc["shape"],
                req_hash,
                resp_hash,
            ],
        )
        inserted += 1

    logger.info("Successfully seeded %d simulated demo requests across 10 days", inserted)
    return inserted
