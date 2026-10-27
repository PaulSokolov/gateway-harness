"""Stratified prompt sampler for contrastive evaluations."""

import json
import random
from typing import Any

from pydantic import BaseModel

from gateway_harness.ledger.store import LedgerStore


class Sample(BaseModel):
    """Evaluation sample with ground-truth baseline response."""

    event_id: str
    request_body: dict[str, Any]
    baseline_text: str
    prompt_tokens: int


def sample(
    store: LedgerStore,
    cluster_key: str,
    n: int = 60,
    seed: int = 42,
) -> list[Sample]:
    """Sample requests from DuckDB stratified by token quartiles with longest outliers."""
    # cluster_key is formatted as "requested_model:workflow_sig" or "tenant:model:sig:template"
    parts = cluster_key.split(":")
    if len(parts) == 2:
        model, wf_sig = parts
        where_clause = "e.requested_model = ? AND e.fp_workflow_sig = ?"
        params = [model, wf_sig]
    elif len(parts) == 4:
        tenant, model, wf_sig, tpl = parts
        where_clause = (
            "e.tenant_id = ? AND e.requested_model = ? AND e.fp_workflow_sig = ? AND e.fp_template_id = ?"
        )
        params = [tenant, model, wf_sig, tpl]
    else:
        where_clause = "e.requested_model = ?"
        params = [parts[0]]

    query = f"""
        SELECT
            e.event_id,
            e.prompt_tokens,
            p_req.body AS req_body,
            p_resp.body AS resp_body
        FROM events e
        INNER JOIN payloads p_req ON e.request_hash = p_req.hash
        INNER JOIN payloads p_resp ON e.response_hash = p_resp.hash
        WHERE {where_clause}
          AND e.status = 'success'
          AND e.internal = false
        ORDER BY e.prompt_tokens ASC
    """

    con = store.connect()
    rows = con.execute(query, params).fetchall()

    if not rows:
        return []

    # Parse rows into raw sample candidates
    candidates: list[Sample] = []
    for r in rows:
        ev_id = r[0]
        p_toks = r[1]
        raw_req = r[2]
        raw_resp = r[3]

        req_dict = json.loads(raw_req) if isinstance(raw_req, str) else raw_req
        resp_dict = json.loads(raw_resp) if isinstance(raw_resp, str) else raw_resp

        # Extract baseline response text
        choices = resp_dict.get("choices") or []
        baseline_text = ""
        if choices:
            baseline_text = (choices[0].get("message") or {}).get("content") or ""

        candidates.append(
            Sample(
                event_id=ev_id,
                request_body=req_dict,
                baseline_text=baseline_text,
                prompt_tokens=p_toks,
            )
        )

    total = len(candidates)
    if total <= n:
        return candidates

    # Take top 3 longest prompts first
    longest = candidates[-3:]
    remaining = candidates[:-3]

    rng = random.Random(seed)
    # Stratify remaining by quartiles
    num_to_sample = n - len(longest)
    quartile_size = len(remaining) // 4
    if quartile_size == 0:
        # Small pool, just sample randomly
        chosen = rng.sample(remaining, min(len(remaining), num_to_sample))
        return longest + chosen

    q1 = remaining[:quartile_size]
    q2 = remaining[quartile_size : quartile_size * 2]
    q3 = remaining[quartile_size * 2 : quartile_size * 3]
    q4 = remaining[quartile_size * 3 :]

    per_q = num_to_sample // 4
    selected: list[Sample] = []
    for q in (q1, q2, q3, q4):
        k = min(len(q), per_q)
        selected.extend(rng.sample(q, k))

    # Fill remainder if integer division left slots open
    selected_set = {s.event_id for s in selected} | {s.event_id for s in longest}
    leftover = [c for c in remaining if c.event_id not in selected_set]
    rem_slots = n - (len(selected) + len(longest))
    if rem_slots > 0 and leftover:
        selected.extend(rng.sample(leftover, min(len(leftover), rem_slots)))

    return longest + selected
