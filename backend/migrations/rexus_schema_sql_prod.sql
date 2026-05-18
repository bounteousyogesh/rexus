-- ============================================================
-- REX-US FINAL DATABASE SETUP SCRIPT (SOURCE OF TRUTH)
-- Includes: Enriched schema v2, v3 clone, functions, auth, token usage, indexes
--
-- MANUAL ONLY — do not auto-run on API startup. This file DROPs rexus_incidents_v3
-- and will erase all imported incidents. Apply via psql when rebuilding from scratch.
-- ============================================================
 
-- =====================
-- EXTENSIONS
-- =====================
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
 
-- =====================
-- DROP (SAFE FOR FULL REBUILD)
-- =====================
DROP TABLE IF EXISTS rexus_cluster_mapping CASCADE;
DROP TABLE IF EXISTS rexus_playbooks CASCADE;
DROP TABLE IF EXISTS rexus_clusters CASCADE;
DROP TABLE IF EXISTS rexus_feedback CASCADE;
DROP TABLE IF EXISTS rexus_analysis_log CASCADE;
DROP TABLE IF EXISTS rexus_wave_results CASCADE;
DROP TABLE IF EXISTS rexus_incidents_v3 CASCADE;
DROP TABLE IF EXISTS rexus_incidents CASCADE;
DROP TABLE IF EXISTS rexus_problems CASCADE;
 
-- =====================
-- CORE INCIDENT SCHEMA (ENRICHED v2)
-- =====================
CREATE TABLE rexus_incidents (
id SERIAL PRIMARY KEY,
incident_number VARCHAR(50) UNIQUE NOT NULL,
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
updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
 
-- =====================
-- INCIDENTS V3 (STRUCTURAL CLONE)
-- =====================
CREATE TABLE IF NOT EXISTS rexus_incidents_v3 (
LIKE rexus_incidents INCLUDING ALL
);
 
-- =====================
-- CLUSTERING
-- =====================
CREATE TABLE rexus_clusters (
id SERIAL PRIMARY KEY,
cluster_name VARCHAR(255),
cluster_description TEXT,
parent_cluster_id INTEGER REFERENCES rexus_clusters(id),
centroid_embedding vector(1536),
incident_count INTEGER DEFAULT 0,
problem_ids TEXT[],
jira_tickets TEXT[],
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
 
-- =====================
-- PLAYBOOKS
-- =====================
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
 
-- =====================
-- ANALYSIS / FEEDBACK / WAVES
-- =====================
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
feedback_type VARCHAR(20) DEFAULT 'general',
feedback_text TEXT NOT NULL,
input_method VARCHAR(20) DEFAULT 'text',
rating INT,
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
 
CREATE TABLE rexus_wave_results (
id SERIAL PRIMARY KEY,
wave VARCHAR(20) NOT NULL,
incident_number VARCHAR(50) NOT NULL,
input_description TEXT,
actual_problem_id VARCHAR(50),
actual_close_notes TEXT,
actual_jira VARCHAR(100),
predicted_problem_id VARCHAR(50),
confidence_score FLOAT,
predicted_playbook_summary TEXT,
match_count INT,
problem_match BOOLEAN,
problem_match_type VARCHAR(20),
analysis_id INT,
evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
 
-- =====================
-- AUTHENTICATION
-- =====================
CREATE TABLE IF NOT EXISTS rexus_users (
id SERIAL PRIMARY KEY,
username VARCHAR(50) UNIQUE NOT NULL,
email VARCHAR(100),
password_hash VARCHAR(255) NOT NULL,
role VARCHAR(20) NOT NULL DEFAULT 'analyst'
  CHECK (role IN ('admin','analyst','viewer')),
is_active BOOLEAN DEFAULT true,
must_change_password BOOLEAN DEFAULT false,
created_at TIMESTAMP DEFAULT NOW(),
last_login TIMESTAMP
);
 
-- =====================
-- TOKEN USAGE TRACKING
-- =====================
CREATE TABLE IF NOT EXISTS rexus_token_usage (
id SERIAL PRIMARY KEY,
call_type VARCHAR(20) NOT NULL,
model VARCHAR(50) NOT NULL,
input_tokens INTEGER NOT NULL DEFAULT 0,
output_tokens INTEGER NOT NULL DEFAULT 0,
estimated_cost_usd NUMERIC(10,6) NOT NULL DEFAULT 0,
endpoint VARCHAR(50) DEFAULT '',
incident_number VARCHAR(20) DEFAULT '',
created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
 
-- ── Step 1: Ensure target table exists (matches sync_problem_states.py schema) ─
 
CREATE TABLE IF NOT EXISTS rexus_problems (
    problem_id          VARCHAR(50)     PRIMARY KEY,
    short_description   TEXT,
    state               VARCHAR(50),        -- raw numeric value from SN
    state_display       VARCHAR(50),        -- human-readable label used by analyze.py
    priority            VARCHAR(50),
    assignment_group    VARCHAR(100),
    assigned_to         VARCHAR(100),
    category            VARCHAR(100),
    opened_at           TIMESTAMP,
    closed_at           TIMESTAMP,
    resolved_at         TIMESTAMP,
    last_synced         TIMESTAMP DEFAULT NOW()
);
 
CREATE INDEX IF NOT EXISTS idx_rexus_problems_state
    ON rexus_problems (state_display);
 
CREATE INDEX IF NOT EXISTS idx_rexus_problems_last_synced
    ON rexus_problems (last_synced DESC);
 
-- =====================
-- INDEXES
-- =====================
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_embedding
ON rexus_incidents USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
 
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_v3_trgm
ON rexus_incidents_v3 USING gin (short_description gin_trgm_ops);
 
 
-- Ensure the HNSW vector index exists on v3 (same as rexus_incidents)
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_v3_embedding
ON rexus_incidents_v3 USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
 
-- Query indexes on v3
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_v3_number ON rexus_incidents_v3(incident_number);
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_v3_split ON rexus_incidents_v3(split_group);
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_v3_opened ON rexus_incidents_v3(opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_v3_category ON rexus_incidents_v3(category);
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_v3_state ON rexus_incidents_v3(state);
 
 
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_number ON rexus_incidents(incident_number);
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_state ON rexus_incidents(state);
CREATE INDEX IF NOT EXISTS idx_analysis_log_incident ON rexus_analysis_log(incident_number);
CREATE INDEX IF NOT EXISTS idx_feedback_incident ON rexus_feedback(incident_number);
CREATE INDEX IF NOT EXISTS idx_rexus_users_username ON rexus_users(username);
CREATE INDEX IF NOT EXISTS idx_token_usage_created ON rexus_token_usage(created_at);
 
-- =====================
-- SIMILARITY SEARCH FUNCTION (CANONICAL)
-- =====================
-- Fix rexus_find_similar to query rexus_incidents_v3 (production table) instead of
-- rexus_incidents (v1), and drop the hardcoded vector(1536) dimension so that
-- Cohere Embed v3 (1024-dim) vectors are accepted without a cast error.
CREATE OR REPLACE FUNCTION rexus_find_similar(
    query_embedding vector,
    similarity_threshold FLOAT DEFAULT 0.40,
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
    FROM rexus_incidents_v3 ri
    LEFT JOIN rexus_cluster_mapping rcm ON ri.id = rcm.incident_id
    WHERE ri.embedding IS NOT NULL
      AND (NOT training_only OR ri.split_group = 'training')
      AND 1 - (ri.embedding <=> query_embedding) >= similarity_threshold
    ORDER BY ri.embedding <=> query_embedding
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql;