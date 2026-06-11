-- Migration 010: KB article sync flag on rexus_incidents_v3
-- Idempotent: safe to re-run on every startup.
--
-- NULL = unchecked. TRUE is seeded for incidents already in rexus_kb_article_incident_mapping.
-- Other values are set by sync import or POST /kb-mappings/refresh (FALSE = checked, none found).

ALTER TABLE rexus_incidents_v3
  ADD COLUMN IF NOT EXISTS has_kb_article BOOLEAN NULL;

-- Seed TRUE for incidents that already have KB mapping rows.
UPDATE rexus_incidents_v3 i
SET has_kb_article = TRUE
FROM (
    SELECT DISTINCT UPPER(TRIM(incident_number)) AS inc_norm
    FROM rexus_kb_article_incident_mapping
    WHERE incident_number IS NOT NULL
      AND TRIM(incident_number) <> ''
) m
WHERE UPPER(TRIM(i.incident_number)) = m.inc_norm
  AND i.has_kb_article IS DISTINCT FROM TRUE;

CREATE INDEX IF NOT EXISTS idx_incidents_has_kb_article_null
  ON rexus_incidents_v3 (opened_at DESC)
  WHERE has_kb_article IS NULL;