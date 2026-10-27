-- Gateway Harness DuckDB Schema Initialization

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ingested_files (
    filename VARCHAR PRIMARY KEY,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_count INTEGER
);

CREATE TABLE IF NOT EXISTS payloads (
    hash VARCHAR PRIMARY KEY,
    kind VARCHAR NOT NULL,
    body JSON NOT NULL,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    event_id VARCHAR PRIMARY KEY,
    ts TIMESTAMP NOT NULL,
    tenant_id VARCHAR NOT NULL,
    api_key_hash VARCHAR NOT NULL,
    session_id VARCHAR,
    call_type VARCHAR NOT NULL,
    stream BOOLEAN NOT NULL,
    requested_model VARCHAR NOT NULL,
    served_model VARCHAR NOT NULL,
    provider VARCHAR,
    status VARCHAR NOT NULL,
    error_class VARCHAR,
    finish_reason VARCHAR,
    prompt_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    cached_tokens INTEGER NOT NULL,
    cost_usd DOUBLE NOT NULL,
    latency_ms DOUBLE NOT NULL,
    ttft_ms DOUBLE,
    optimized BOOLEAN NOT NULL,
    policy_id VARCHAR,
    canary BOOLEAN NOT NULL,
    internal BOOLEAN NOT NULL,
    has_tools BOOLEAN NOT NULL,
    has_images BOOLEAN NOT NULL,
    response_format VARCHAR,
    n_messages INTEGER NOT NULL,
    fp_version INTEGER NOT NULL,
    fp_template_id VARCHAR NOT NULL,
    fp_workflow_sig VARCHAR NOT NULL,
    fp_shape VARCHAR NOT NULL,
    request_hash VARCHAR NOT NULL,
    response_hash VARCHAR
);

CREATE INDEX IF NOT EXISTS idx_events_tenant_ts ON events(tenant_id, ts);
CREATE INDEX IF NOT EXISTS idx_events_workflow ON events(fp_workflow_sig, fp_template_id);

INSERT INTO schema_version (version) VALUES (1) ON CONFLICT DO NOTHING;
