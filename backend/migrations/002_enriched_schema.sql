-- REX-US Schema v2 — Enriched incident data
-- Adds fields from ServiceNow API that weren't in the original export:
-- work_notes, structured JIRA/order fields, business duration, reassignment count, etc.

-- ============================================================
-- DROP old tables (full rebuild)
-- ============================================================
DROP TABLE IF EXISTS rexus_cluster_mapping CASCADE;
DROP TABLE IF EXISTS rexus_work_notes CASCADE;
DROP TABLE IF EXISTS rexus_playbooks CASCADE;
DROP TABLE IF EXISTS rexus_clusters CASCADE;
DROP TABLE IF EXISTS rexus_feedback CASCADE;
DROP TABLE IF EXISTS rexus_analysis_log CASCADE;
DROP TABLE IF EXISTS rexus_data_split CASCADE;
DROP TABLE IF EXISTS rexus_incidents CASCADE;

CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- ENRICHED INCIDENTS TABLE
-- ============================================================
CREATE TABLE rexus_incidents (
    id SERIAL PRIMARY KEY,

    -- Identity
    incident_number VARCHAR(50) UNIQUE NOT NULL,
    sys_id VARCHAR(50),

    -- Issue details
    short_description TEXT NOT NULL,
    description TEXT,                       -- Root cause / initial analysis

    -- Classification
    category VARCHAR(100),
    subcategory VARCHAR(100),
    priority VARCHAR(50),
    severity VARCHAR(50),                   -- NEW: operational severity
    impact VARCHAR(50),                     -- NEW
    urgency VARCHAR(50),                    -- NEW
    state VARCHAR(50),
    close_code VARCHAR(100),

    -- Assignment
    assignment_group VARCHAR(255),
    assigned_to VARCHAR(255),
    cmdb_ci VARCHAR(255),
    business_service VARCHAR(255),
    caller_id VARCHAR(255),                 -- NEW: store/caller
    location VARCHAR(255),                  -- NEW: store location
    company VARCHAR(255),                   -- NEW: company name
    contact_type VARCHAR(100),              -- NEW: channel (Self-service, Email, etc.)
    opened_by VARCHAR(255),                 -- NEW: who created

    -- Resolution
    close_notes TEXT,
    u_resolved_by VARCHAR(255),             -- NEW: who actually fixed it
    u_resolution_confirmed_by VARCHAR(255), -- NEW: who validated

    -- Problem & Related Records
    problem_id VARCHAR(50),
    parent_incident VARCHAR(50),
    u_jira_number VARCHAR(100),             -- NEW: structured JIRA ticket

    -- Order Data (DT custom)
    u_order_number VARCHAR(50),             -- NEW: structured order number
    u_total_order_amount VARCHAR(50),       -- NEW
    u_order_type VARCHAR(100),              -- NEW
    u_order_date DATE,                      -- NEW
    u_financial_impact VARCHAR(50),         -- NEW
    u_correction BOOLEAN DEFAULT FALSE,     -- NEW
    u_correction_type VARCHAR(100),         -- NEW
    u_error_category VARCHAR(255),          -- NEW

    -- Operational Metrics (NEW — not in PDF)
    business_duration VARCHAR(100),         -- e.g., "3 Hours 16 Minutes"
    business_stc INT,                       -- business seconds to close
    calendar_duration VARCHAR(100),
    calendar_stc INT,
    reassignment_count INT DEFAULT 0,       -- how many teams touched it
    reopen_count INT DEFAULT 0,
    made_sla BOOLEAN,
    escalation VARCHAR(50),

    -- Work Notes (NEW — full investigation trail)
    work_notes TEXT,                         -- concatenated timestamped work notes
    comments TEXT,                           -- additional comments

    -- Timing
    opened_at TIMESTAMP,
    resolved_at TIMESTAMP,
    closed_at TIMESTAMP,

    -- Data split
    split_group VARCHAR(20),                -- training, wave_1, wave_2, ..., reserve

    -- Vector embedding (1536 dims, text-embedding-3-small)
    embedding vector(1536),
    embedding_text TEXT,                     -- The text that was embedded

    -- Metadata
    source VARCHAR(50) DEFAULT 'servicenow',
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- CLUSTERING (will be rebuilt after embedding)
-- ============================================================
CREATE TABLE rexus_clusters (
    id SERIAL PRIMARY KEY,
    cluster_name VARCHAR(255),
    cluster_description TEXT,
    parent_cluster_id INTEGER REFERENCES rexus_clusters(id),
    centroid_embedding vector(1536),
    incident_count INTEGER DEFAULT 0,
    problem_ids TEXT[],
    jira_tickets TEXT[],                     -- NEW
    dominant_category VARCHAR(100),
    avg_resolution_hours FLOAT,
    avg_internal_similarity FLOAT,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE rexus_cluster_mapping (
    id SERIAL PRIMARY KEY,
    incident_id INTEGER REFERENCES rexus_incidents(id) ON DELETE CASCADE,
    cluster_id INTEGER REFERENCES rexus_clusters(id) ON DELETE CASCADE,
    similarity_to_centroid FLOAT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(incident_id, cluster_id)
);

-- ============================================================
-- PLAYBOOKS
-- ============================================================
CREATE TABLE rexus_playbooks (
    id SERIAL PRIMARY KEY,
    cluster_id INTEGER REFERENCES rexus_clusters(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    source_incident_count INTEGER,
    source_incidents TEXT[],
    grounding_score FLOAT,
    status VARCHAR(20) DEFAULT 'draft',
    reviewed_by VARCHAR(255),
    reviewed_at TIMESTAMP,
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- ANALYSIS LOG & FEEDBACK
-- ============================================================
CREATE TABLE rexus_analysis_log (
    id SERIAL PRIMARY KEY,
    incident_number VARCHAR(50),
    input_json JSONB NOT NULL,
    cleaned_issue TEXT,
    confidence_score FLOAT,
    match_count INT,
    dominant_cluster_id INT,
    dominant_cluster_name TEXT,
    focused_playbook_content TEXT,
    focused_playbook_grounding FLOAT,
    top_problem_id VARCHAR(50),
    similar_incidents JSONB,
    full_response JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE rexus_feedback (
    id SERIAL PRIMARY KEY,
    analysis_id INT REFERENCES rexus_analysis_log(id),
    incident_number VARCHAR(50),
    feedback_type VARCHAR(20) NOT NULL DEFAULT 'general',
    feedback_text TEXT NOT NULL,
    input_method VARCHAR(20) DEFAULT 'text',
    rating INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- WAVE EVALUATION TRACKING
-- ============================================================
CREATE TABLE rexus_wave_results (
    id SERIAL PRIMARY KEY,
    wave VARCHAR(20) NOT NULL,              -- wave_1, wave_2, etc.
    incident_number VARCHAR(50) NOT NULL,
    -- Input (what we gave the system)
    input_description TEXT,
    -- Expected (what the team actually did)
    actual_problem_id VARCHAR(50),
    actual_close_notes TEXT,
    actual_jira VARCHAR(100),
    -- Predicted (what our system suggested)
    predicted_problem_id VARCHAR(50),
    confidence_score FLOAT,
    predicted_playbook_summary TEXT,
    match_count INT,
    -- Scoring
    problem_match BOOLEAN,                  -- did we get the right problem?
    problem_match_type VARCHAR(20),         -- exact, partial, no_suggestion, wrong
    -- Metadata
    analysis_id INT,
    evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- INDEXES
-- ============================================================

-- HNSW for vector search
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_embedding
ON rexus_incidents USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Query indexes
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_number ON rexus_incidents(incident_number);
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_cmdb ON rexus_incidents(cmdb_ci);
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_category ON rexus_incidents(category);
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_opened ON rexus_incidents(opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_state ON rexus_incidents(state);
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_split ON rexus_incidents(split_group);
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_problem ON rexus_incidents(problem_id);
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_jira ON rexus_incidents(u_jira_number);
CREATE INDEX IF NOT EXISTS idx_rexus_cluster_mapping_cluster ON rexus_cluster_mapping(cluster_id);
CREATE INDEX IF NOT EXISTS idx_rexus_cluster_mapping_incident ON rexus_cluster_mapping(incident_id);
CREATE INDEX IF NOT EXISTS idx_analysis_log_created ON rexus_analysis_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_analysis ON rexus_feedback(analysis_id);
CREATE INDEX IF NOT EXISTS idx_wave_results_wave ON rexus_wave_results(wave);

-- ============================================================
-- SIMILARITY SEARCH FUNCTION (updated for training-only search)
-- ============================================================
CREATE OR REPLACE FUNCTION rexus_find_similar(
    query_embedding vector(1536),
    similarity_threshold FLOAT DEFAULT 0.50,
    max_results INTEGER DEFAULT 15,
    training_only BOOLEAN DEFAULT TRUE
)
RETURNS TABLE (
    incident_id INTEGER,
    incident_number VARCHAR(50),
    short_description TEXT,
    close_notes TEXT,
    similarity_score FLOAT,
    cluster_id INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ri.id,
        ri.incident_number,
        ri.short_description,
        ri.close_notes,
        (1 - (ri.embedding <=> query_embedding))::FLOAT AS similarity_score,
        rcm.cluster_id
    FROM rexus_incidents ri
    LEFT JOIN rexus_cluster_mapping rcm ON ri.id = rcm.incident_id
    WHERE ri.embedding IS NOT NULL
      AND (NOT training_only OR ri.split_group = 'training')
      AND 1 - (ri.embedding <=> query_embedding) >= similarity_threshold
    ORDER BY ri.embedding <=> query_embedding
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql;
