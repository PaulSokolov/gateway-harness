from gateway_harness.funnel.savings import calculate_net_savings
from gateway_harness.ledger.store import LedgerStore


def test_calculate_net_savings(tmp_path):
    store = LedgerStore(tmp_path / "ledger.duckdb")
    con = store.connect()

    # 1. Internal optimizer spend ($0.50)
    con.execute(
        """
        INSERT INTO events (
            event_id, ts, tenant_id, api_key_hash, call_type, stream,
            requested_model, served_model, status, prompt_tokens,
            completion_tokens, cached_tokens, cost_usd, latency_ms,
            optimized, canary, internal, has_tools, has_images, n_messages,
            fp_version, fp_template_id, fp_workflow_sig, fp_shape,
            request_hash
        ) VALUES (
            'opt_1', '2026-03-01 10:00:00', 'internal', 'k', 'chat_completion', false,
            'gpt-4o', 'gpt-4o', 'success', 1000,
            200, 0, 0.50, 500,
            false, false, true, false, false, 1,
            1, 'tpl', 'wf', 'one_shot_simple',
            'h1'
        )
        """
    )

    # 2. Optimized customer event: requested gpt-4o, served gpt-4o-mini
    # Actual cost: $0.005. Counterfactual cost on gpt-4o for 2000 in, 500 out: ~$0.01
    con.execute(
        """
        INSERT INTO events (
            event_id, ts, tenant_id, api_key_hash, call_type, stream,
            requested_model, served_model, status, prompt_tokens,
            completion_tokens, cached_tokens, cost_usd, latency_ms,
            optimized, canary, internal, has_tools, has_images, n_messages,
            fp_version, fp_template_id, fp_workflow_sig, fp_shape,
            request_hash, policy_id
        ) VALUES (
            'cust_1', '2026-03-01 11:00:00', 'tenant_abc', 'k2', 'chat_completion', false,
            'gpt-4o', 'gpt-4o-mini', 'success', 2000,
            500, 0, 0.005, 150,
            true, false, false, false, false, 1,
            1, 'tpl_cust', 'wf_cust', 'one_shot_simple',
            'h2', 'pol_savings_1'
        )
        """
    )

    report = calculate_net_savings(store)

    assert report["optimizer_cost_usd"] == 0.50
    assert report["gross_savings_usd"] > 0.0
    assert len(report["by_policy"]) == 1
    assert report["by_policy"][0]["policy_id"] == "pol_savings_1"
    assert len(report["by_tenant"]) == 1
    assert report["by_tenant"][0]["tenant_id"] == "tenant_abc"
