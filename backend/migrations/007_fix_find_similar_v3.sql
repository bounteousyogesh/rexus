-- Migration 007: Fix rexus_find_similar to target rexus_incidents_v3
--               and drop the hardcoded vector(1536) dimension so that
--               Cohere (1024-dim) or any other embed model works without error.
--
-- Background:
--   - Production data lives in rexus_incidents_v3 (see migration 006).
--   - The previous function queried rexus_incidents (v1) which is empty in prod.
--   - The vector(1536) parameter type rejects Cohere Embed v3 vectors (1024-dim).
--   - Removing the explicit dimension makes the function accept any vector size,
--     consistent with how pgvector handles dimensionless vector columns.

CREATE OR REPLACE FUNCTION rexus_find_similar(
    query_embedding vector,          -- dimensionless: accepts 1024, 1536, etc.
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
