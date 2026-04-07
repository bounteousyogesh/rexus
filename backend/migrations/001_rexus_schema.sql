-- REX-US Schema v1
-- Enhanced incident intelligence schema with full work notes support

CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- INCIDENT KNOWLEDGE BANK (ServiceNow)
-- ============================================================

CREATE TABLE IF NOT EXISTS rexus_incidents (
    id SERIAL PRIMARY KEY,

    -- Identity
    incident_number VARCHAR(50) UNIQUE NOT NULL,
    sys_id VARCHAR(50),
    problem_id VARCHAR(50),
    parent_incident VARCHAR(50),

    -- Issue details
    short_description TEXT NOT NULL,
    description TEXT,
    cleaned_text TEXT NOT NULL,          -- Normalized text used for embedding

    -- Classification
    category VARCHAR(100),
    subcategory VARCHAR(100),
    priority VARCHAR(50),
    state VARCHAR(50),
    close_code VARCHAR(100),

    -- Assignment
    assignment_group VARCHAR(255),
    assigned_to VARCHAR(255),
    cmdb_ci VARCHAR(255),               -- Configuration item (e.g., "GK POS")
    business_service VARCHAR(255),

    -- Resolution (THE GOLD)
    close_notes TEXT,                    -- Final resolution summary
    resolution_category VARCHAR(100),
    resolution_subcategory VARCHAR(100),

    -- Timing
    opened_at TIMESTAMP,
    resolved_at TIMESTAMP,
    closed_at TIMESTAMP,
    time_to_resolve_hours FLOAT,        -- Computed: resolved_at - opened_at

    -- Work notes stored separately (see rexus_work_notes table)

    -- Systems involved (extracted from text analysis)
    systems_involved TEXT[],

    -- Vector embedding (1536 dims, text-embedding-3-small)
    embedding vector(1536),
    embedding_text TEXT,                 -- The text that was embedded

    -- Metadata
    source VARCHAR(50) DEFAULT 'servicenow',  -- 'servicenow', 'manual', 'pdf'
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Recency weight (0.0 to 1.0, recomputed monthly)
    recency_weight FLOAT DEFAULT 1.0
);

-- Work notes — stored separately to preserve individual entries
CREATE TABLE IF NOT EXISTS rexus_work_notes (
    id SERIAL PRIMARY KEY,
    incident_id INTEGER REFERENCES rexus_incidents(id) ON DELETE CASCADE,
    note_type VARCHAR(20) NOT NULL,     -- 'work_note' or 'comment'
    value TEXT NOT NULL,
    created_by VARCHAR(255),
    created_on TIMESTAMP,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- CLUSTERING
-- ============================================================

CREATE TABLE IF NOT EXISTS rexus_clusters (
    id SERIAL PRIMARY KEY,
    cluster_name VARCHAR(255),
    cluster_description TEXT,
    parent_cluster_id INTEGER REFERENCES rexus_clusters(id),  -- Hierarchical

    -- Centroid
    centroid_embedding vector(1536),

    -- Stats
    incident_count INTEGER DEFAULT 0,
    problem_ids TEXT[],
    dominant_category VARCHAR(100),
    avg_resolution_hours FLOAT,

    -- Quality
    avg_internal_similarity FLOAT,      -- How tight is this cluster
    status VARCHAR(20) DEFAULT 'active', -- 'active', 'archived', 'draft'

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rexus_cluster_mapping (
    id SERIAL PRIMARY KEY,
    incident_id INTEGER REFERENCES rexus_incidents(id) ON DELETE CASCADE,
    cluster_id INTEGER REFERENCES rexus_clusters(id) ON DELETE CASCADE,
    similarity_to_centroid FLOAT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(incident_id, cluster_id)
);

-- ============================================================
-- PLAYBOOKS (grounded, stored in DB not filesystem)
-- ============================================================

CREATE TABLE IF NOT EXISTS rexus_playbooks (
    id SERIAL PRIMARY KEY,
    cluster_id INTEGER REFERENCES rexus_clusters(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,               -- Markdown playbook

    -- Grounding
    source_incident_count INTEGER,       -- How many incidents this is based on
    source_incidents TEXT[],             -- Incident numbers used as evidence
    grounding_score FLOAT,              -- 0-1: how well grounded in real data

    -- Review workflow
    status VARCHAR(20) DEFAULT 'draft', -- 'draft', 'reviewed', 'approved'
    reviewed_by VARCHAR(255),
    reviewed_at TIMESTAMP,

    -- Versioning
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- INDEXES
-- ============================================================

-- HNSW for fast similarity search (better than IVFFlat for our scale)
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_embedding
ON rexus_incidents USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_rexus_clusters_centroid
ON rexus_clusters USING hnsw (centroid_embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Query indexes
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_number ON rexus_incidents(incident_number);
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_cmdb ON rexus_incidents(cmdb_ci);
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_category ON rexus_incidents(category);
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_opened ON rexus_incidents(opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_state ON rexus_incidents(state);
CREATE INDEX IF NOT EXISTS idx_rexus_work_notes_incident ON rexus_work_notes(incident_id);
CREATE INDEX IF NOT EXISTS idx_rexus_cluster_mapping_cluster ON rexus_cluster_mapping(cluster_id);
CREATE INDEX IF NOT EXISTS idx_rexus_cluster_mapping_incident ON rexus_cluster_mapping(incident_id);

-- ============================================================
-- FUNCTIONS
-- ============================================================

-- Find similar incidents with recency weighting
CREATE OR REPLACE FUNCTION rexus_find_similar(
    query_embedding vector(1536),
    similarity_threshold FLOAT DEFAULT 0.75,
    max_results INTEGER DEFAULT 10,
    apply_recency BOOLEAN DEFAULT TRUE
)
RETURNS TABLE (
    incident_id INTEGER,
    incident_number VARCHAR(50),
    short_description TEXT,
    close_notes TEXT,
    similarity_score FLOAT,
    weighted_score FLOAT,
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
        CASE WHEN apply_recency
            THEN (1 - (ri.embedding <=> query_embedding))::FLOAT * ri.recency_weight
            ELSE (1 - (ri.embedding <=> query_embedding))::FLOAT
        END AS weighted_score,
        rcm.cluster_id
    FROM rexus_incidents ri
    LEFT JOIN rexus_cluster_mapping rcm ON ri.id = rcm.incident_id
    WHERE 1 - (ri.embedding <=> query_embedding) >= similarity_threshold
    ORDER BY
        CASE WHEN apply_recency
            THEN (1 - (ri.embedding <=> query_embedding))::FLOAT * ri.recency_weight
            ELSE (1 - (ri.embedding <=> query_embedding))::FLOAT
        END DESC
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql;
