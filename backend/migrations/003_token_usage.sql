-- REX-US Migration 003: Token usage tracking table
-- Tracks every OpenAI API call for monitoring and cost dashboards.

CREATE TABLE IF NOT EXISTS rexus_token_usage (
    id SERIAL PRIMARY KEY,
    call_type VARCHAR(20) NOT NULL,         -- 'embedding' or 'completion'
    model VARCHAR(50) NOT NULL,             -- 'text-embedding-3-small', 'gpt-5.4', etc.
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd NUMERIC(10, 6) NOT NULL DEFAULT 0,
    endpoint VARCHAR(50) DEFAULT '',        -- '/analyze', '/sync/import', '/search', etc.
    incident_number VARCHAR(20) DEFAULT '', -- optional: which incident triggered this call
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Index for dashboard queries (daily/monthly aggregation)
CREATE INDEX IF NOT EXISTS idx_token_usage_created ON rexus_token_usage (created_at);
CREATE INDEX IF NOT EXISTS idx_token_usage_model ON rexus_token_usage (model, created_at);
