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
