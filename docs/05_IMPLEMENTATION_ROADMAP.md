# REX-US — Implementation Roadmap

## Phase 1: Foundation (Schema + Ingestion)

### Epic 1.1: Schema Design
- Design incident table with full fields (work_notes, resolution_notes, assignment_group, cmdb_ci, etc.)
- Design system knowledge table for Confluence/JIRA content
- Design cluster table with hierarchical support
- Design playbook table (store in DB, not filesystem)
- HNSW index configuration
- Migration scripts

### Epic 1.2: ServiceNow Ingestion Pipeline
- OAuth token management (auto-refresh)
- Bulk historical pull via table API (backfill 12 months)
- Real-time webhook receiver for new incidents
- Data normalization and cleaning
- Embedding generation (batch + real-time)
- Deduplication logic

### Epic 1.3: JIRA + Confluence Ingestion (when access confirmed)
- OAuth 2.0 token management for Atlassian
- Confluence page crawler (by space)
- JIRA issue puller (by project/JQL)
- Chunking strategy for Confluence pages (section-level)
- Embedding generation for knowledge articles

---

## Phase 2: Intelligence (Clustering + Playbooks)

### Epic 2.1: Clustering Engine
- Hierarchical clustering (category → sub-cluster)
- Adaptive similarity thresholds per category
- Auto-split large clusters (>100 incidents)
- Auto-merge drifting clusters
- Nightly re-clustering job
- Cluster quality metrics

### Epic 2.2: Grounded Playbook Generator
- Extract real resolution patterns from work notes
- Frequency analysis of resolution steps
- LLM synthesis grounded in evidence (RAG)
- Citation: every step references source incidents
- Confidence scoring based on cluster size + consistency
- Human review workflow (draft → reviewed → approved)

### Epic 2.3: Recency Engine
- Time-decay scoring function
- 12-month rolling window
- Monthly archival job
- HNSW index rebuild after archival

---

## Phase 3: Interface (API + UI)

### Epic 3.1: Ticket Analysis API
- POST /analyze — analyze new incident, return similar + playbook
- POST /webhook — receive ServiceNow webhooks
- GET /incidents — list with filters, pagination
- GET /clusters — list with hierarchy
- GET /playbooks/{id} — grounded playbook with citations
- GET /knowledge/search — search system knowledge bank

### Epic 3.2: Knowledge Bank Chatbot API
- POST /chat — ask questions about system architecture
- RAG over Confluence + JIRA content
- Context-aware responses with source links
- Conversation history

### Epic 3.3: Frontend
- Incident analysis page (redesigned from PoC)
- Knowledge bank explorer + chatbot
- Cluster visualization
- Playbook viewer with citations
- Analytics dashboard

---

## Phase 4: Production Hardening

### Epic 4.1: Security & Auth
- SSO / Azure AD integration (replace hardcoded login)
- RBAC roles
- API key management
- Audit logging

### Epic 4.2: Operations
- Health checks and monitoring
- Backup strategy (daily snapshots, 30-day retention)
- Error handling and retry logic
- Rate limiting for ServiceNow/Atlassian APIs

### Epic 4.3: Verification Agent (future)
- Read-only access to GKPOS/SAP ECC/Hybris
- Cross-reference incident data against live system state
- Automated verification of reported discrepancies

---

## Priority Order

```
Phase 1 → Build the data foundation (schema + ingestion)
Phase 2 → Build the intelligence (what makes REX-US valuable)
Phase 3 → Build the interface (how humans interact)
Phase 4 → Harden for production
```
