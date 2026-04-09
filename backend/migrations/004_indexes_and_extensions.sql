-- Migration 004: Add indexes for feedback/analysis_log lookups and pg_trgm extension
-- ENH-013: Preventive indexes on incident_number columns
-- ENH-002/ENH-007: Ensure pg_trgm extension and trigram index for hybrid search

-- Ensure pg_trgm extension is available for hybrid search (ENH-002)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ENH-013: Index on rexus_feedback.incident_number for per-incident feedback lookups
CREATE INDEX IF NOT EXISTS idx_feedback_incident
  ON rexus_feedback (incident_number)
  WHERE incident_number IS NOT NULL;

-- ENH-013: Index on rexus_analysis_log.incident_number for per-incident analysis lookups
CREATE INDEX IF NOT EXISTS idx_analysis_log_incident
  ON rexus_analysis_log (incident_number)
  WHERE incident_number IS NOT NULL;

-- ENH-007: GIN trigram index on rexus_incidents_v3 for keyword hybrid search
-- This prevents full table scans during trigram similarity matching in /analyze
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_v3_trgm
  ON rexus_incidents_v3 USING gin (short_description gin_trgm_ops);
