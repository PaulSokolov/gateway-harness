import json

import pytest

from gateway_harness.ledger.store import LedgerStore
from gateway_harness.probe.sampler import sample


@pytest.fixture
def seeded_store(tmp_path):
    store = LedgerStore(tmp_path / "ledger.duckdb")
    con = store.connect()

    # Insert 40 events with varying prompt_tokens (10 to 400)
    for i in range(40):
        ev_id = f"ev_{i}"
        p_toks = (i + 1) * 10
        req_hash = f"h_req_{i}"
        resp_hash = f"h_resp_{i}"

        # Insert payloads
        req_body = json.dumps({"messages": [{"role": "user", "content": f"query {i}"}]})
        resp_body = json.dumps({"choices": [{"message": {"content": f"answer {i}"}}]})

        con.execute("INSERT INTO payloads (hash, kind, body) VALUES (?, 'request', ?)", [req_hash, req_body])
        con.execute(
            "INSERT INTO payloads (hash, kind, body) VALUES (?, 'response', ?)", [resp_hash, resp_body]
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
                ?, NOW(), 't1', 'k1', 'chat_completion', false,
                'gpt-4o', 'gpt-4o', 'success', ?,
                50, 0, 0.005, 200,
                false, false, false, false, false, 1,
                1, 'tpl_test', 'wf_test', 'one_shot_templated',
                ?, ?
            )
            """,
            [ev_id, p_toks, req_hash, resp_hash],
        )
    return store


def test_sampler_stratification_and_longest(seeded_store):
    samples = sample(seeded_store, "gpt-4o:wf_test", n=15, seed=42)
    assert len(samples) == 15

    # Check that the 3 longest prompts (tokens 400, 390, 380) are included
    token_counts = {s.prompt_tokens for s in samples}
    assert 400 in token_counts
    assert 390 in token_counts
    assert 380 in token_counts

    # Check baseline text populated
    for s in samples:
        assert "answer" in s.baseline_text
        assert "query" in s.request_body["messages"][0]["content"]


def test_sampler_determinism(seeded_store):
    s1 = sample(seeded_store, "gpt-4o:wf_test", n=10, seed=123)
    s2 = sample(seeded_store, "gpt-4o:wf_test", n=10, seed=123)
    assert [s.event_id for s in s1] == [s.event_id for s in s2]
