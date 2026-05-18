-- Migration 010a: Load staging table from ServiceNow problem data
-- Purpose: Bulk-loads (or incrementally refreshes) stg_servicenow_problems
--          from the problems visible in rexus_incidents_v3.
--
-- Design:
--   • Collects every distinct problem_id referenced in rexus_incidents_v3.
--   • Inserts placeholder rows into the staging table for any problem_id
--     not yet present, so the sync script knows what to fetch from ServiceNow.
--   • Does NOT call ServiceNow directly — that is done by the Python sync
--     script (sync_problem_states.py) which writes the full payload here.
--   • Safe to re-run: ON CONFLICT DO NOTHING skips existing rows.

-- ── Step 1: Ensure the staging table exists (guard against run-order issues) ──

CREATE TABLE IF NOT EXISTS stg_servicenow_problems (
    problem_id          VARCHAR(50)     PRIMARY KEY,
    short_description   TEXT,
    state               VARCHAR(50),
    state_display       VARCHAR(50),
    priority            VARCHAR(50),
    assignment_group    VARCHAR(100),
    assigned_to         VARCHAR(100),
    category            VARCHAR(100),
    opened_at           TIMESTAMP,
    closed_at           TIMESTAMP,
    resolved_at         TIMESTAMP,
    raw_json            JSONB,
    synced_at           TIMESTAMP NOT NULL DEFAULT NOW(),
    sync_batch_id       VARCHAR(50)
);

-- ── Step 2: Seed placeholder rows for every problem_id in the incidents table ──
-- These rows will be filled in by the Python sync script; until then they act
-- as a "to-do list" so nothing is missed.

INSERT INTO stg_servicenow_problems (problem_id, state_display, synced_at)
SELECT DISTINCT
    problem_id,
    'Pending'                   AS state_display,
    NOW()                       AS synced_at
FROM rexus_incidents_v3
WHERE problem_id IS NOT NULL
  AND problem_id <> ''
ON CONFLICT (problem_id) DO NOTHING;

-- ── Step 3: Report how many problems are staged ───────────────────────────────

DO $$
DECLARE
    v_total   INT;
    v_pending INT;
BEGIN
    SELECT COUNT(*)                                 INTO v_total   FROM stg_servicenow_problems;
    SELECT COUNT(*) FILTER (WHERE state_display = 'Pending')
                                                    INTO v_pending FROM stg_servicenow_problems;
    RAISE NOTICE 'stg_servicenow_problems: % total rows, % pending sync', v_total, v_pending;
END $$;
