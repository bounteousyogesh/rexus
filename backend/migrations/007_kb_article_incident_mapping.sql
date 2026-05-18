-- Migration 007: KB article to incident mapping seed table
-- Stores curated relationships between ServiceNow incidents and KB articles.
-- Seed rows are loaded from data/kb_article_incident_mapping.csv by backend startup.

CREATE TABLE IF NOT EXISTS rexus_kb_article_incident_mapping (
    id SERIAL PRIMARY KEY,
    incident_number VARCHAR(50) NOT NULL,
    knowledge_article_number VARCHAR(50) NOT NULL,
  apcr VARCHAR(100),
  kb_description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (incident_number, knowledge_article_number)
);

ALTER TABLE rexus_kb_article_incident_mapping
  ADD COLUMN IF NOT EXISTS apcr VARCHAR(100);

ALTER TABLE rexus_kb_article_incident_mapping
  ADD COLUMN IF NOT EXISTS kb_description TEXT;

CREATE INDEX IF NOT EXISTS idx_kb_article_incident_mapping_incident
  ON rexus_kb_article_incident_mapping (incident_number);

CREATE INDEX IF NOT EXISTS idx_kb_article_incident_mapping_kb
  ON rexus_kb_article_incident_mapping (knowledge_article_number);
