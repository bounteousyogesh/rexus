-- Migration 010: Create staging table for raw ServiceNow problem data
-- Purpose: Receives raw problem records synced directly from ServiceNow
--          before they are validated and upserted into rexus_problems.
--          Acts as a safe landing zone — rexus_problems is never written
--          directly from external data without passing through here first.

-- ── Staging table ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS stg_servicenow_problems (
    -- Natural key from ServiceNow
    problem_id          VARCHAR(50)     PRIMARY KEY,

    -- Core fields mirroring ServiceNow problem record
    short_description   TEXT,
    state               VARCHAR(50),        -- raw numeric state value  (e.g. "1")
    state_display       VARCHAR(50),        -- human-readable label      (e.g. "Open")
    priority            VARCHAR(50),        -- display value             (e.g. "2 - High")
    assignment_group    VARCHAR(100),
    assigned_to         VARCHAR(100),
    category            VARCHAR(100),
    opened_at           TIMESTAMP,
    closed_at           TIMESTAMP,
    resolved_at         TIMESTAMP,

    -- Sync bookkeeping
    raw_json            JSONB,              -- full SN response for debugging / reprocessing
    synced_at           TIMESTAMP NOT NULL DEFAULT NOW(),
    sync_batch_id       VARCHAR(50)         -- optional batch tag (e.g. ISO date "2026-04-24")
);

-- ── Indexes ───────────────────────────────────────────────────────────────────

-- Fast lookup by state for incremental upserts
CREATE INDEX IF NOT EXISTS idx_stg_sn_problems_state
    ON stg_servicenow_problems (state_display);

-- Batch processing — find all records from a given sync run
CREATE INDEX IF NOT EXISTS idx_stg_sn_problems_batch
    ON stg_servicenow_problems (sync_batch_id);

-- Most recent sync time — useful for monitoring lag
CREATE INDEX IF NOT EXISTS idx_stg_sn_problems_synced_at
    ON stg_servicenow_problems (synced_at DESC);
