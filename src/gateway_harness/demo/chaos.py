"""Chaos injection utilities demonstrating automated tripwire circuit breaker response."""

import logging

from gateway_harness.canary.monitor import run_tripwire_check
from gateway_harness.ledger.store import LedgerStore

logger = logging.getLogger("gateway_harness.demo.chaos")


async def inject_quality_degradation(
    store: LedgerStore,
    policy_id: str,
    failure_count: int = 25,
) -> list[str]:
    """Inject failure traces into canary and production logs and trigger tripwire check.

    Returns the list of policies disabled by the circuit breaker.
    """
    con = store.connect()

    # 1. Insert failing canary results
    for i in range(failure_count):
        con.execute(
            """
            INSERT INTO canary_results (policy_id, event_id, verdict, validator_codes, cost)
            VALUES (?, ?, 'loss', ['refusal', 'truncated'], 0.001)
            """,
            [policy_id, f"chaos_canary_{i}"],
        )

    # 2. Insert failing production events in last hour
    for i in range(failure_count):
        con.execute(
            """
            INSERT INTO events (
                event_id, ts, tenant_id, api_key_hash, call_type, stream,
                requested_model, served_model, status, prompt_tokens,
                completion_tokens, cached_tokens, cost_usd, latency_ms,
                optimized, canary, internal, has_tools, has_images, n_messages,
                fp_version, fp_template_id, fp_workflow_sig, fp_shape,
                request_hash, policy_id, finish_reason
            ) VALUES (
                ?, NOW(), 'tenant_demo', 'key_demo', 'chat_completion', false,
                'gpt-4o', 'gpt-4o-mini', 'success', 20,
                10, 0, 0.0001, 100,
                true, false, false, false, false, 1,
                1, 'tpl', 'wf', 'one_shot_simple',
                'h_chaos', ?, 'length'
            )
            """,
            [f"chaos_prod_{i}", policy_id],
        )

    logger.warning("Injected %d chaos failures for policy %s", failure_count, policy_id)

    # 3. Trigger immediate circuit breaker check
    disabled = await run_tripwire_check(store=store)
    return disabled
