-- Migration 010b: Upsert rexus_problems from staging
-- Purpose: Promotes validated, fully-synced rows from stg_servicenow_problems
--          into the production rexus_problems table used by the analyze
--          endpoint and problem-scoring logic.
--
-- Design:
--   • Only promotes rows where state_display != 'Pending' (i.e. the Python
--     sync script has written real data from ServiceNow).
--   • ON CONFLICT DO UPDATE keeps rexus_problems current without deletes.
--   • Safe to re-run at any time; idempotent.
--   • rexus_problems is the authoritative cache read by:
--       - analyze.py  (_generate_focused_playbook → problem scoring)
--       - health.py   (problem count stats)
--       - sync_problem_states.py (also writes here directly as fallback)

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

-- ── Step 2: Upsert from staging → production ─────────────────────────────────

INSERT INTO rexus_problems (
    problem_id,
    short_description,
    state,
    state_display,
    priority,
    assignment_group,
    assigned_to,
    category,
    opened_at,
    closed_at,
    resolved_at,
    last_synced
)
SELECT
    stg.problem_id,
    stg.short_description,
    stg.state,
    stg.state_display,
    stg.priority,
    stg.assignment_group,
    stg.assigned_to,
    stg.category,
    stg.opened_at,
    stg.closed_at,
    stg.resolved_at,
    stg.synced_at           AS last_synced
FROM stg_servicenow_problems stg
WHERE stg.state_display IS DISTINCT FROM 'Pending'   -- only promote fully-synced rows
ON CONFLICT (problem_id) DO UPDATE SET
    short_description   = EXCLUDED.short_description,
    state               = EXCLUDED.state,
    state_display       = EXCLUDED.state_display,
    priority            = EXCLUDED.priority,
    assignment_group    = EXCLUDED.assignment_group,
    assigned_to         = EXCLUDED.assigned_to,
    category            = EXCLUDED.category,
    opened_at           = EXCLUDED.opened_at,
    closed_at           = EXCLUDED.closed_at,
    resolved_at         = EXCLUDED.resolved_at,
    last_synced         = EXCLUDED.last_synced;

-- ── Step 3: Summary report ────────────────────────────────────────────────────

DO $$
DECLARE
    v_total  INT;
    v_open   INT;
    v_closed INT;
BEGIN
    SELECT COUNT(*)                                          INTO v_total  FROM rexus_problems;
    SELECT COUNT(*) FILTER (WHERE state_display IN ('Open', 'New'))
                                                             INTO v_open   FROM rexus_problems;
    SELECT COUNT(*) FILTER (WHERE state_display NOT IN ('Open', 'New', 'Pending'))
                                                             INTO v_closed FROM rexus_problems;
    RAISE NOTICE 'rexus_problems: % total | % open | % closed/resolved', v_total, v_open, v_closed;
END $$;
