from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from gateway_harness.ledger.store import LedgerStore


@dataclass
class ClusterStats:
    tenant_id: str
    requested_model: str
    workflow_sig: str
    template_id: str
    count: int
    distinct_days: int
    total_cost: float
    p50_prompt_tokens: int
    p99_prompt_tokens: int
    p50_completion_tokens: int
    p99_completion_tokens: int
    cached_token_share: float
    shape_mode: str
    has_tools: bool
    has_images: bool
    has_response_format: bool
    error_rate: float
    length_trunc_rate: float
    first_seen: datetime | None
    last_seen: datetime | None


def build_clusters(store: LedgerStore, window_days: int = 30) -> list[ClusterStats]:
    """Aggregate trace events from DuckDB into deterministic workload clusters."""
    con = store.con

    query = """
    WITH base_events AS (
        SELECT
            tenant_id,
            requested_model,
            fp_workflow_sig,
            fp_template_id,
            fp_shape,
            ts,
            cost_usd,
            prompt_tokens,
            completion_tokens,
            cached_tokens,
            status,
            finish_reason,
            has_tools,
            has_images,
            (response_format IS NOT NULL) AS has_fmt
        FROM events
        WHERE internal = false
          AND ts >= CURRENT_TIMESTAMP - INTERVAL (? || ' days')
    )
    SELECT
        tenant_id,
        requested_model,
        fp_workflow_sig,
        fp_template_id,
        count(*) AS total_count,
        count(DISTINCT CAST(ts AS DATE)) AS distinct_days,
        sum(cost_usd) AS total_cost,
        quantile_cont(prompt_tokens, 0.50)::INTEGER AS p50_prompt,
        quantile_cont(prompt_tokens, 0.99)::INTEGER AS p99_prompt,
        quantile_cont(completion_tokens, 0.50)::INTEGER AS p50_comp,
        quantile_cont(completion_tokens, 0.99)::INTEGER AS p99_comp,
        COALESCE(sum(cached_tokens)::DOUBLE / NULLIF(sum(prompt_tokens), 0), 0.0) AS cached_share,
        mode(fp_shape) AS shape_mode,
        bool_or(has_tools) AS any_tools,
        bool_or(has_images) AS any_images,
        bool_or(has_fmt) AS any_fmt,
        count(CASE WHEN status != 'success' THEN 1 END)::DOUBLE / count(*) AS error_rate,
        count(CASE WHEN finish_reason = 'length' THEN 1 END)::DOUBLE / count(*) AS length_trunc_rate,
        min(ts) AS first_seen,
        max(ts) AS last_seen
    FROM base_events
    GROUP BY tenant_id, requested_model, fp_workflow_sig, fp_template_id
    HAVING count(*) >= 1
    ORDER BY total_cost DESC;
    """

    rows = con.execute(query, [str(window_days)]).fetchall()
    clusters: list[ClusterStats] = []

    for r in rows:
        clusters.append(
            ClusterStats(
                tenant_id=str(r[0]),
                requested_model=str(r[1]),
                workflow_sig=str(r[2]),
                template_id=str(r[3]),
                count=int(r[4]),
                distinct_days=int(r[5]),
                total_cost=float(r[6] or 0.0),
                p50_prompt_tokens=int(r[7] or 0),
                p99_prompt_tokens=int(r[8] or 0),
                p50_completion_tokens=int(r[9] or 0),
                p99_completion_tokens=int(r[10] or 0),
                cached_token_share=float(r[11] or 0.0),
                shape_mode=str(r[12] or "other"),
                has_tools=bool(r[13]),
                has_images=bool(r[14]),
                has_response_format=bool(r[15]),
                error_rate=float(r[16] or 0.0),
                length_trunc_rate=float(r[17] or 0.0),
                first_seen=r[18],
                last_seen=r[19],
            )
        )

    return clusters
