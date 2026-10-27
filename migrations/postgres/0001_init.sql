-- Gateway-Harness Appliance: PostgreSQL Schema
-- Migration 0001: Initial Core Tables

CREATE TABLE IF NOT EXISTS gh_schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gh_settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL
);

-- Seed default settings if not exists
INSERT INTO gh_settings (key, value)
VALUES 
    ('global_kill', 'false'::jsonb),
    ('policy_version', '1'::jsonb)
ON CONFLICT (key) DO NOTHING;

CREATE TABLE IF NOT EXISTS gh_tenant_modes (
    tenant_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    updated_by TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gh_policies (
    policy_id TEXT PRIMARY KEY,
    cluster_key TEXT NOT NULL,
    requested_model TEXT NOT NULL,
    target_model TEXT NOT NULL,
    scaffold JSONB NOT NULL,
    template_ids TEXT[] NOT NULL,
    canary_rate DOUBLE PRECISION NOT NULL DEFAULT 0.05,
    expected_nonloss DOUBLE PRECISION NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    tenant_id TEXT,
    fingerprint_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_gh_policies_lookup 
ON gh_policies (requested_model, status);

CREATE TABLE IF NOT EXISTS gh_proposals (
    proposal_id TEXT PRIMARY KEY,
    policy JSONB NOT NULL,
    evidence JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_by TEXT,
    decided_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS gh_audit (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor TEXT,
    action TEXT NOT NULL,
    target TEXT,
    detail JSONB
);

CREATE TABLE IF NOT EXISTS gh_runs (
    run_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    cluster_key TEXT NOT NULL,
    budget_usd DOUBLE PRECISION NOT NULL,
    spent_usd DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    result JSONB
);

CREATE TABLE IF NOT EXISTS gh_lessons (
    id TEXT PRIMARY KEY,
    archetype TEXT NOT NULL,
    cue TEXT NOT NULL,
    lesson TEXT NOT NULL,
    evidence JSONB,
    scaffold JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gh_session_pins (
    session_id TEXT PRIMARY KEY,
    target_model TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_gh_session_pins_expiry 
ON gh_session_pins (expires_at);

INSERT INTO gh_schema_version (version, applied_at)
VALUES (1, NOW())
ON CONFLICT (version) DO NOTHING;
