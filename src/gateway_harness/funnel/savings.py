"""Realized net savings accounting tracking counterfactual gross savings minus optimizer spend."""

from typing import Any

from gateway_harness.ledger.store import LedgerStore
from gateway_harness.pricing import cost


def calculate_net_savings(
    store: LedgerStore,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict[str, Any]:
    """Calculate realized gross and net savings across optimized production traces."""
    con = store.connect()

    time_filter = ""
    params: list[Any] = []
    if from_date:
        time_filter += " AND ts >= ?"
        params.append(from_date)
    if to_date:
        time_filter += " AND ts <= ?"
        params.append(to_date)

    # 1. Total Optimizer Internal Spend
    opt_spend_row = con.execute(
        f"SELECT COALESCE(SUM(cost_usd), 0.0) FROM events WHERE internal = true {time_filter}",
        params,
    ).fetchone()
    optimizer_cost = float(opt_spend_row[0]) if opt_spend_row else 0.0

    # 2. Optimized Production Requests
    opt_query = f"""
        SELECT
            event_id,
            strftime(ts, '%Y-%m-%d') AS day,
            tenant_id,
            policy_id,
            requested_model,
            served_model,
            prompt_tokens,
            completion_tokens,
            cached_tokens,
            cost_usd
        FROM events
        WHERE optimized = true
          AND internal = false
          AND status = 'success'
          {time_filter}
    """
    rows = con.execute(opt_query, params).fetchall()

    gross_savings = 0.0
    by_policy_map: dict[str, dict[str, Any]] = {}
    by_tenant_map: dict[str, float] = {}
    by_day_map: dict[str, float] = {}

    for r in rows:
        day = r[1]
        tenant = r[2]
        policy_id = r[3] or "unknown"
        requested_model = r[4]
        prompt_tokens = r[6]
        completion_tokens = r[7]
        cached_tokens = r[8]
        actual_cost = float(r[9])

        # Counterfactual: what would it have cost on requested model?
        base_cost = cost(
            model=requested_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
        )
        if base_cost is None:
            # Fallback multiplier if pricing not available
            base_cost = actual_cost * 2.5

        savings = max(0.0, base_cost - actual_cost)
        gross_savings += savings

        # Policy breakdown
        if policy_id not in by_policy_map:
            by_policy_map[policy_id] = {
                "policy_id": policy_id,
                "requested_model": requested_model,
                "count": 0,
                "savings_usd": 0.0,
            }
        by_policy_map[policy_id]["count"] += 1
        by_policy_map[policy_id]["savings_usd"] += savings

        # Tenant breakdown
        by_tenant_map[tenant] = by_tenant_map.get(tenant, 0.0) + savings

        # Daily breakdown
        by_day_map[day] = by_day_map.get(day, 0.0) + savings

    net_savings = max(0.0, gross_savings - optimizer_cost)

    return {
        "gross_savings_usd": round(gross_savings, 2),
        "optimizer_cost_usd": round(optimizer_cost, 2),
        "net_savings_usd": round(net_savings, 2),
        "by_policy": [
            {
                "policy_id": p["policy_id"],
                "requested_model": p["requested_model"],
                "count": p["count"],
                "savings_usd": round(p["savings_usd"], 2),
            }
            for p in by_policy_map.values()
        ],
        "by_tenant": [{"tenant_id": t, "savings_usd": round(s, 2)} for t, s in by_tenant_map.items()],
        "by_day": [{"date": d, "savings_usd": round(s, 2)} for d, s in sorted(by_day_map.items())],
    }
