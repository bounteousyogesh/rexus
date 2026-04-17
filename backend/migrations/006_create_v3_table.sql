-- Migration 006: Formally create rexus_incidents_v3
-- Previously this table was only created ad-hoc by load_enriched_v3.py.
-- It is the production table used by /analyze, /sync/import, and /health.
-- This migration ensures it exists on fresh deployments where data is
-- loaded entirely via the UI (sync tab) rather than CLI scripts.

CREATE TABLE IF NOT EXISTS rexus_incidents_v3 (LIKE rexus_incidents INCLUDING ALL);

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
