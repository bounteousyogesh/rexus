-- Migration 012: Sync job configuration (schedule + last-run status)
-- Idempotent: safe to re-run on every startup.

CREATE TABLE IF NOT EXISTS rexus_sync_config (
    job_name TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    interval_hours INT NOT NULL DEFAULT 24,
    last_run_at TIMESTAMP,
    last_status TEXT,
    last_result JSONB,
    next_run_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO rexus_sync_config (job_name, enabled, interval_hours)
VALUES ('closed_incident_sync', TRUE, 24)
ON CONFLICT (job_name) DO NOTHING;

INSERT INTO rexus_sync_config (job_name, enabled, interval_hours)
VALUES ('new_incident_sync', TRUE, 24)
ON CONFLICT (job_name) DO NOTHING;
