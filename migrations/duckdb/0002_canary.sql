-- DuckDB Migration 0002: Canary results table

CREATE TABLE IF NOT EXISTS canary_results (
    policy_id TEXT,
    event_id TEXT PRIMARY KEY,
    verdict TEXT,
    validator_codes TEXT[],
    cost DOUBLE,
    evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
