-- Migration 011: Daily new-incident snapshots (ServiceNow state New, opened today)
-- Full schema: all rexus_incidents_v3 columns plus sync snapshot metadata.
-- Idempotent: safe to re-run on every startup.

CREATE TABLE IF NOT EXISTS rexus_incidents_new (
    id SERIAL PRIMARY KEY,
    incident_number VARCHAR(50) NOT NULL,
    sys_id VARCHAR(50),
    short_description TEXT NOT NULL,
    description TEXT,
    category VARCHAR(100),
    subcategory VARCHAR(100),
    priority VARCHAR(50),
    severity VARCHAR(50),
    impact VARCHAR(50),
    urgency VARCHAR(50),
    state VARCHAR(50),
    close_code VARCHAR(100),
    assignment_group VARCHAR(255),
    assigned_to VARCHAR(255),
    cmdb_ci VARCHAR(255),
    business_service VARCHAR(255),
    caller_id VARCHAR(255),
    location VARCHAR(255),
    company VARCHAR(255),
    contact_type VARCHAR(100),
    opened_by VARCHAR(255),
    close_notes TEXT,
    u_resolved_by VARCHAR(255),
    u_resolution_confirmed_by VARCHAR(255),
    problem_id VARCHAR(50),
    parent_incident VARCHAR(50),
    u_jira_number VARCHAR(100),
    u_order_number VARCHAR(50),
    u_total_order_amount VARCHAR(50),
    u_order_type VARCHAR(100),
    u_order_date DATE,
    u_financial_impact VARCHAR(50),
    u_correction BOOLEAN DEFAULT FALSE,
    u_correction_type VARCHAR(100),
    u_error_category VARCHAR(255),
    business_duration VARCHAR(100),
    business_stc INT,
    calendar_duration VARCHAR(100),
    calendar_stc INT,
    reassignment_count INT DEFAULT 0,
    reopen_count INT DEFAULT 0,
    made_sla BOOLEAN,
    escalation VARCHAR(50),
    work_notes TEXT,
    comments TEXT,
    opened_at TIMESTAMP,
    resolved_at TIMESTAMP,
    closed_at TIMESTAMP,
    split_group VARCHAR(20),
    embedding vector(1536),
    embedding_text TEXT,
    source VARCHAR(50) DEFAULT 'servicenow',
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    has_kb_article BOOLEAN NULL,
    is_analyzed BOOLEAN NOT NULL DEFAULT FALSE,
    sync_date DATE NOT NULL,
    version INT NOT NULL DEFAULT 1,
    synced_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (incident_number, sync_date)
);

CREATE INDEX IF NOT EXISTS idx_rexus_incidents_new_sync_date
    ON rexus_incidents_new (sync_date DESC);

CREATE INDEX IF NOT EXISTS idx_rexus_incidents_new_trgm
    ON rexus_incidents_new USING gin (short_description gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_rexus_incidents_new_embedding
    ON rexus_incidents_new USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_rexus_incidents_new_number
    ON rexus_incidents_new (incident_number);

CREATE INDEX IF NOT EXISTS idx_rexus_incidents_new_split
    ON rexus_incidents_new (split_group);

CREATE INDEX IF NOT EXISTS idx_rexus_incidents_new_opened
    ON rexus_incidents_new (opened_at DESC);

CREATE INDEX IF NOT EXISTS idx_rexus_incidents_new_category
    ON rexus_incidents_new (category);

CREATE INDEX IF NOT EXISTS idx_rexus_incidents_new_state
    ON rexus_incidents_new (state);

CREATE INDEX IF NOT EXISTS idx_rexus_incidents_new_has_kb_article_null
    ON rexus_incidents_new (opened_at DESC)
    WHERE has_kb_article IS NULL;
