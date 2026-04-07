# REX-US — Architecture Decisions

## Decision Log

### AD-001: Embedding Model — text-embedding-3-small (1,536 dims)
**Decision**: Keep 1,536 dimensions. Do not upgrade to 3,072.
**Rationale**: 2.3% accuracy gain doesn't justify 2x storage/search cost at 12K scale. Revisit at 100K+.

### AD-002: Vector Index — HNSW over IVFFlat
**Decision**: Use HNSW index instead of IVFFlat.
**Rationale**: IVFFlat requires pre-defined list count and retraining after bulk inserts. HNSW is self-tuning, maintains accuracy as data grows, better recall at our scale.
```sql
-- HNSW index for 12K incidents
CREATE INDEX idx_incidents_embedding ON servicenow_incidents
USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
```

### AD-003: No Chunking Required
**Decision**: One embedding per incident, no text chunking.
**Rationale**: Even the heaviest incident (~3,000 tokens with all work notes) fits within the 8,191 token limit. Single embedding preserves full semantic context.

### AD-004: Database — PostgreSQL + pgvector (not a separate vector DB)
**Decision**: Stay with PostgreSQL + pgvector. No Pinecone/Weaviate/Qdrant.
**Rationale**: 12K vectors is trivially small for pgvector. Keeping vectors in the same DB as metadata eliminates sync issues and simplifies infrastructure. Separate vector DB adds cost and complexity with zero benefit at this scale.

### AD-005: Recency Weighting — Time-Decayed Similarity
**Decision**: Apply time decay to similarity scores. 12-month rolling window.
**Rationale**: Resolution procedures change as architecture evolves. Recent fixes are more relevant.

### AD-006: Playbook Generation — Grounded RAG, Not Open Generation
**Decision**: LLM synthesizes playbooks from ACTUAL work notes and resolution data only.
**Rationale**: PoC playbooks were LLM-generated from titles — risk of hallucination. Enterprise playbooks must be grounded in real resolution evidence. Every step must cite source incidents.

### AD-007: Two Knowledge Banks
**Decision**: Separate knowledge banks for "how it SHOULD work" vs "how it WAS FIXED".
1. **System Knowledge Bank** (Confluence + JIRA): Architecture, release notes, RCAs, runbooks
2. **Incident Knowledge Bank** (ServiceNow): Incidents, work notes, resolution patterns, playbooks

**Rationale**: Different sources, different update frequencies, different consumers. System KB is reference material; Incident KB is operational intelligence.

### AD-008: New Project, Not a Fork
**Decision**: Create REX-US as a new project. Do not extend the NEXUS PoC.
**Rationale**: NEXUS has demo data, simulators, synchronous psycopg2, mixed concerns. Starting fresh with proper architecture is faster than refactoring.

---

## Two Knowledge Banks — Detail

### Bank 1: System Knowledge (Confluence + JIRA)

```
Sources:
  Confluence → Architecture diagrams, release notes, RCA docs, runbooks
  JIRA       → Implementation details, bug fixes, sprint work

Purpose:
  "How should the system behave?"
  "What was changed in the last release?"
  "What is the RCA for this known issue?"

Consumers:
  - Chatbot (people ask questions about the system)
  - Incident analysis (cross-reference incident against known architecture)
  - Verify Agent (check if behavior matches documented design)

Update frequency: On-demand (when Confluence/JIRA changes)
Embedding strategy: Chunk pages into sections, embed each section
```

### Bank 2: Incident Intelligence (ServiceNow)

```
Sources:
  ServiceNow → Incidents, work notes, resolution notes, close codes

Purpose:
  "We've seen this before — here's how it was fixed"
  "These 50 incidents cluster into 8 patterns"
  "Here's a playbook based on 15 similar resolutions"

Consumers:
  - New incident analysis (find similar past incidents)
  - Playbook recommendation
  - Trend analysis / reporting

Update frequency: Real-time (webhook) + daily batch reconciliation
Embedding strategy: One embedding per incident (no chunking needed)
Recency: 12-month rolling window with time decay
```
