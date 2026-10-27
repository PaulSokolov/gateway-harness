"""Continuous 5% canary evaluation worker verifying serving quality in production."""

import json
import logging
from typing import Any

from gateway_harness.contracts import ModelClient, Verdict
from gateway_harness.ledger.store import LedgerStore
from gateway_harness.probe.client import Budget, BudgetExceeded
from gateway_harness.probe.judge import judge
from gateway_harness.probe.validators import validate

logger = logging.getLogger("gateway_harness.canary.sampler")


async def execute_canary_evaluations(
    store: LedgerStore,
    client: ModelClient,
    judge_model: str,
    budget: Budget,
    limit: int = 50,
) -> int:
    """Evaluate pending canary events against the requested baseline model.

    Returns the count of evaluated events.
    """
    con = store.connect()
    # Query unassessed canary events
    query = """
        SELECT
            e.event_id,
            e.policy_id,
            e.requested_model,
            p_req.body AS req_body,
            p_resp.body AS cand_body
        FROM events e
        INNER JOIN payloads p_req ON e.request_hash = p_req.hash
        INNER JOIN payloads p_resp ON e.response_hash = p_resp.hash
        LEFT JOIN canary_results cr ON e.event_id = cr.event_id
        WHERE e.canary = true
          AND e.optimized = true
          AND cr.event_id IS NULL
        ORDER BY e.ts ASC
        LIMIT ?
    """
    rows = con.execute(query, [limit]).fetchall()
    if not rows:
        return 0

    evaluated_count = 0
    canary_budget_cap = budget.limit_usd * 0.30

    for r in rows:
        if budget.spent_usd >= canary_budget_cap:
            logger.info("Canary evaluation paused: reached 30% daily budget share")
            break

        event_id = r[0]
        policy_id = r[1]
        requested_model = r[2]
        raw_req = r[3]
        raw_cand = r[4]

        req_body: dict[str, Any] = json.loads(raw_req) if isinstance(raw_req, str) else raw_req
        cand_body: dict[str, Any] = json.loads(raw_cand) if isinstance(raw_cand, str) else raw_cand

        choices = cand_body.get("choices") or []
        cand_text = ""
        cand_finish = None
        if choices:
            cand_text = (choices[0].get("message") or {}).get("content") or ""
            cand_finish = choices[0].get("finish_reason")

        try:
            # Replay requested model
            base_text, meta = await client.complete(
                requested_model,
                req_body.get("messages", []),
            )
            replay_cost = meta.get("cost_usd") or 0.0

            # Deterministic validation
            val_errs = validate(
                request_body=req_body,
                baseline_text=base_text,
                candidate_text=cand_text,
                finish_reason=cand_finish,
            )

            if val_errs:
                verdict = Verdict.LOSS
                judge_cost = 0.0
            else:
                j_res = await judge(
                    client=client,
                    judge_model=judge_model,
                    task_messages=req_body.get("messages", []),
                    baseline_text=base_text,
                    candidate_text=cand_text,
                )
                verdict = j_res.verdict
                judge_cost = j_res.judge_cost_usd

            total_eval_cost = replay_cost + judge_cost

            # Record result in DuckDB
            con.execute(
                """
                INSERT INTO canary_results (policy_id, event_id, verdict, validator_codes, cost)
                VALUES (?, ?, ?, ?, ?)
                """,
                [policy_id, event_id, verdict.value, val_errs, total_eval_cost],
            )
            evaluated_count += 1

        except BudgetExceeded:
            logger.warning("Canary evaluation stopped: budget exceeded")
            break
        except Exception as exc:
            logger.warning("Error evaluating canary event %s: %s", event_id, exc)
            continue

    return evaluated_count
