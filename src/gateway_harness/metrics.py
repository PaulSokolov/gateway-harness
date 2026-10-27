"""Prometheus metrics exporter for Gateway-Harness telemetry and observability."""

from prometheus_client import Counter, Gauge

# Request and Routing Metrics
REQUESTS_TOTAL = Counter(
    "gh_requests_total",
    "Total requests processed by the gateway",
    ["status", "model", "optimized"],
)

DECISIONS_TOTAL = Counter(
    "gh_decisions_total",
    "Total routing decisions made by the policy matcher",
    ["reason"],
)

# Capture Pipeline Metrics
CAPTURE_DROPPED_TOTAL = Counter(
    "gh_capture_dropped_total",
    "Total telemetry events dropped due to spool buffer overflow",
)

CAPTURE_ERRORS_TOTAL = Counter(
    "gh_capture_errors_total",
    "Total exceptions encountered during telemetry capture",
)

# Policy & Proposal Gauges / Counters
POLICIES_ACTIVE = Gauge(
    "gh_policies_active",
    "Current number of active routing policies",
)

PROPOSALS_TOTAL = Counter(
    "gh_proposals_total",
    "Total proposals created or resolved",
    ["status"],
)

# Probe Engine Metrics
PROBE_RUNS_TOTAL = Counter(
    "gh_probe_runs_total",
    "Total contrastive probe runs executed",
    ["status"],
)

JUDGE_VERDICTS_TOTAL = Counter(
    "gh_judge_verdicts_total",
    "Pairwise judge verdicts recorded",
    ["verdict"],
)

# Canary & Circuit Breaker
CANARY_TRIPWIRE_TOTAL = Counter(
    "gh_canary_tripwire_total",
    "Total automated policy disablements by tripwire circuit breaker",
    ["reason"],
)

# Financial Accounting
SAVINGS_USD_TOTAL = Counter(
    "gh_savings_usd_total",
    "Estimated cumulative net savings in USD achieved by routing",
)


def reset_metrics_for_testing() -> None:
    """Clear or reinitialize metrics state for test isolation."""
    pass
