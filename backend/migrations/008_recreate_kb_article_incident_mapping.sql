-- Migration 008: Recreate KB article to incident mapping seed table
-- Generated from data/kb_article_incident_mapping.csv

DROP TABLE IF EXISTS rexus_kb_article_incident_mapping;

CREATE TABLE rexus_kb_article_incident_mapping (
    id SERIAL PRIMARY KEY,
    incident_number VARCHAR(50) NOT NULL,
    knowledge_article_number VARCHAR(50) NOT NULL,
    apcr VARCHAR(100),
    kb_description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO rexus_kb_article_incident_mapping (incident_number, knowledge_article_number, apcr, kb_description)
VALUES
    ('INC2394139', 'KB0020233', 'apcr 0', 'Mandatory Credit Card details'),
    ('INC2394138', 'KB0020233', 'apcr 0', 'Mandatory Credit Card details'),
    ('INC2394128', 'KB0020233', 'apcr 0', 'Mandatory Credit Card details'),
    ('INC2394125', 'KB0020233', 'apcr 0', 'Mandatory Credit Card details'),
    ('INC2394122', 'KB0020233', NULL, 'Mandatory Credit Card details'),
    ('INC2393338', 'KB0020299', NULL, 'Updating header promotion'),
    ('INC2393337', 'KB0020233', NULL, 'Mandatory Credit Card details'),
    ('INC2393334', 'KB0020299', NULL, 'Updating header promotion'),
    ('INC2393327', 'KB0020233', NULL, 'Mandatory Credit Card details'),
    ('INC2393315', 'KB0020234', 'apcr 0', 'Mandatory Credit Card details'),
    ('INC2393308', 'KB0020235', 'apcr 0', 'Mandatory Credit Card details'),
    ('INC2393299', 'KB0020236', 'apcr 0', 'Mandatory Credit Card details'),
    ('INC2394999', 'KB0020299', NULL, 'Updating header promotion'),
    ('INC2284476', 'KB0020379', NULL, 'Update Delivery Address '),
    ('INC2169110', 'KB0020379', NULL, 'Update Delivery Address '),
    ('INC2258834', 'KB0020379', NULL, 'Update Delivery Address '),
    ('INC2206350', 'KB0020379', NULL, 'Update Delivery Address '),
    ('INC2170421', 'KB0020379', NULL, 'Update Delivery Address '),
    ('INC2169110', 'KB0020379', NULL, 'Update Delivery Address '),
    ('INC2338651', 'KB0020379', NULL, 'Update Delivery Address '),
    ('INC2338650', 'KB0020379', NULL, 'Update Delivery Address '),
    ('INC2338647', 'KB0020379', NULL, 'Update Delivery Address '),
    ('INC2237673', 'KB0020392', NULL, 'Update an Expired Authorization to Accepted'),
    ('INC2268980', 'KB0020392', NULL, 'Update an Expired Authorization to Accepted'),
    ('INC2312494', 'KB0020392', NULL, 'Update an Expired Authorization to Accepted'),
    ('INC2068983', 'KB0020392', NULL, 'Update an Expired Authorization to Accepted'),
    ('INC2181740', 'KB0020392', NULL, 'Update an Expired Authorization to Accepted'),
    ('INC2237673', 'KB0020392', NULL, 'Update an Expired Authorization to Accepted'),
    ('INC2312494', 'KB0020300', NULL, '�Updating Env Fee in SAP'),
    ('INC2307767', 'KB0020392', NULL, 'Update an Expired Authorization to Accepted'),
    ('INC2068983', 'KB0020392', NULL, 'Update an Expired Authorization to Accepted'),
    ('INC2097733', 'KB0020368', NULL, 'No Line Items Received in iDoc'),
    ('INC2094207', 'KB0020368', NULL, 'No Line Items Received in iDoc'),
    ('INC2095074', 'KB0020368', NULL, 'No Line Items Received in iDoc'),
    ('INC2094225', 'KB0020368', NULL, 'No Line Items Received in iDoc'),
    ('INC2105167', 'KB0020368', NULL, 'No Line Items Received in iDoc'),
    ('INC2099604', 'KB0020368', NULL, 'No Line Items Received in iDoc'),
    ('INC2094208', 'KB0020368', NULL, 'No Line Items Received in iDoc'),
    ('INC2107227', 'KB0020368', NULL, 'No Line Items Received in iDoc'),
    ('INC2108162', 'KB0020368', NULL, 'No Line Items Received in iDoc'),
    ('INC2074730', 'KB0020368', NULL, 'No Line Items Received in iDoc'),
    ('INC2324123', 'KB0020298', NULL, 'Updating Tax Values in SAP Sales Order'),
    ('INC2239057', 'KB0020387', NULL, 'Export Status Returns RETRYLATER'),
    ('INC2027097', 'KB0020387', NULL, 'Export Status Returns RETRYLATER'),
    ('INC2021064', 'KB0020387', NULL, 'Export Status Returns RETRYLATER'),
    ('INC2020171', 'KB0020387', NULL, 'Export Status Returns RETRYLATER'),
    ('INC2024334', 'KB0020387', NULL, 'Export Status Returns RETRYLATER'),
    ('INC2025115', 'KB0020387', NULL, 'Export Status Returns RETRYLATER'),
    ('INC2285121', 'KB0020387', NULL, 'Export Status Returns RETRYLATER');

CREATE INDEX idx_kb_article_incident_mapping_incident
    ON rexus_kb_article_incident_mapping (incident_number);

CREATE INDEX idx_kb_article_incident_mapping_kb
    ON rexus_kb_article_incident_mapping (knowledge_article_number);