# REX-US — Data Model

## Entity Relationship Diagram

```mermaid
erDiagram
    rexus_incidents_v3 {
        int id PK
        varchar incident_number UK "INC2061899"
        varchar sys_id "ServiceNow sys_id"
        text short_description "Issue title"
        text description "Detailed description"
        varchar category "Software, Hardware, etc."
        varchar subcategory "Error Condition, etc."
        varchar priority "1-High to 5-Low"
        varchar state "Closed Complete, etc."
        varchar cmdb_ci "GK POS, Vision, etc."
        varchar assignment_group "Application Support, etc."
        varchar problem_id "PRB0015628"
        text close_notes "Resolution details"
        text work_notes "Investigation thread (PII)"
        text comments "Additional comments"
        text embedding_text "Cleaned text for AI"
        vector embedding "1536-dim vector (pgvector)"
        varchar split_group "training, analyzed, wave_N"
        timestamp opened_at
        timestamp resolved_at
    }

    rexus_clusters {
        int id PK
        varchar cluster_name "GK POS Stuck On Please Wait"
        text cluster_description
        int parent_cluster_id FK
        vector centroid_embedding "Cluster center vector"
        int incident_count
        array problem_ids "PRB IDs in this cluster"
        array jira_tickets "JIRA refs"
        varchar dominant_category
        float avg_resolution_hours
        float avg_internal_similarity
    }

    rexus_cluster_mapping {
        int id PK
        int incident_id FK
        int cluster_id FK
        float similarity_to_centroid
    }

    rexus_playbooks {
        int id PK
        int cluster_id FK
        varchar title
        text content "Markdown playbook"
        int source_incident_count
        float grounding_score "0.4 to 0.95"
        varchar status "draft, published"
        int version
    }

    rexus_analysis_log {
        int id PK
        varchar incident_number
        jsonb input_json "Raw request (PII)"
        text cleaned_issue
        float confidence_score
        int match_count
        int dominant_cluster_id
        text focused_playbook_content
        float focused_playbook_grounding
        varchar top_problem_id
        jsonb similar_incidents
        jsonb full_response "Full result (PII)"
        timestamp created_at
    }

    rexus_feedback {
        int id PK
        int analysis_id FK
        varchar incident_number
        varchar feedback_type "general"
        text feedback_text
        varchar input_method "text, voice"
        int rating "1-5"
        timestamp created_at
    }

    rexus_problems {
        varchar problem_id PK "PRB0015628"
        text short_description
        varchar state_display "Open, Cancelled, Closed"
        varchar priority
        timestamp opened_at
        timestamp last_synced
    }

    rexus_wave_results {
        int id PK
        varchar wave "wave_1 to wave_5"
        varchar incident_number
        varchar actual_problem_id
        varchar predicted_problem_id
        float confidence_score
        varchar problem_match_type "exact_match, top3, wrong, missed"
        int analysis_id
    }

    rexus_token_usage {
        int id PK
        varchar call_type "embedding, completion"
        varchar model "claude-opus-4.6, cohere.embed-v4"
        int input_tokens
        int output_tokens
        numeric estimated_cost_usd
        varchar endpoint "/analyze, /sync/import"
        varchar incident_number
        timestamp created_at
    }

    rexus_users {
        int id PK
        varchar username UK "admin, analyst1"
        varchar email "user@org.com"
        varchar password_hash "bcrypt hash"
        varchar role "admin, analyst, viewer"
        boolean is_active "true/false"
        boolean must_change_password "force reset flag"
        timestamp created_at
        timestamp last_login
    }

    rexus_incidents_v3 ||--o{ rexus_cluster_mapping : "belongs to"
    rexus_clusters ||--o{ rexus_cluster_mapping : "contains"
    rexus_clusters ||--o| rexus_playbooks : "has playbook"
    rexus_clusters ||--o| rexus_clusters : "parent cluster"
    rexus_analysis_log ||--o{ rexus_feedback : "receives feedback"
    rexus_problems ||--o{ rexus_incidents_v3 : "tagged to"
```

## Table Summary

| Table | Rows | Purpose | Vector Column |
|-------|------|---------|---------------|
| **rexus_incidents_v3** | 16,892 | Production knowledge base — incidents with embeddings | `embedding` (vector 1536, HNSW index) |
| **rexus_clusters** | 2,379 | Incident groups (similar incidents clustered together) | `centroid_embedding` (vector 1536) |
| **rexus_cluster_mapping** | 14,992 | Many-to-many: which incident belongs to which cluster | — |
| **rexus_playbooks** | 0 | Generated resolution playbooks per cluster | — |
| **rexus_analysis_log** | 7,407 | Every analysis ever run — input, output, scores | — |
| **rexus_feedback** | 41 | User feedback (text + voice) linked to analyses | — |
| **rexus_problems** | 300 | ServiceNow Problem records with state (Open/Cancelled) | — |
| **rexus_wave_results** | 1,899 | Validation test results across 5 waves | — |
| **rexus_token_usage** | — | LLM API call tracking for cost monitoring (OpenAI or Bedrock) | — |
| **rexus_users** | — | User accounts for JWT authentication (admin, analyst, viewer roles) | — |

## Vector Search Architecture

```mermaid
flowchart LR
    subgraph Input
        A[Incident Text<br/>from INC fetch, PDF, or text]
    end

    subgraph EmbeddingModel["LLM Provider (configurable)"]
        B["OpenAI: text-embedding-3-small<br/>Bedrock: cohere.embed-v4:0<br/>(both 1536 dims)"]
    end

    subgraph PostgreSQL
        C[(rexus_incidents_v3<br/>embedding column<br/>HNSW index)]
        D[pg_trgm trigram index<br/>on short_description]
    end

    subgraph Search
        E[Vector Search<br/>cosine distance, threshold 0.35]
        F[Keyword Search<br/>trigram similarity]
        G[Hybrid Merge<br/>MAX score + agreement bonus 0.05]
    end

    A --> B
    B -->|1536-dim vector| E
    A -->|short_description text| F
    E --> C
    F --> D
    C --> G
    D --> G
    G -->|Top N results<br/>default 15, max 50| H[Analysis Engine]
```

**How it works:**
1. User logs in (JWT authentication), then provides an incident via INC number (fetched from ServiceNow), PDF upload, or plain text
2. Incident text is cleaned (PII stripped via regex) and sent to the configured embedding model for vectorization (1536 dimensions). The embedding model is configurable: `text-embedding-3-small` when `LLM_PROVIDER=openai`, or `cohere.embed-v4:0` when `LLM_PROVIDER=bedrock`. Both produce 1536-dimensional vectors.
3. Two parallel searches run against PostgreSQL on the `rexus_incidents_v3` table (only `training` and `analyzed` split groups):
   - **Vector search:** cosine distance using HNSW index on the `embedding` column, threshold = `request.threshold - 0.05` (default 0.35) — finds semantically similar incidents
   - **Keyword search:** PostgreSQL `pg_trgm` trigram similarity on `short_description`, triggered only if the query is longer than 5 characters — finds lexically similar incidents
4. Results are merged per incident: `MAX(vector_score, keyword_score)`. If both methods found the same incident (agreement), a bonus of `min(vec, kw) * 0.05` is added — but only if vector > 0.4 and keyword > 0.3
5. Results are sorted by hybrid score, top N returned (default 15, configurable 1-50 via `limit` parameter)
6. Top results go to the analysis engine for CMDB family-aware problem scoring and GPT-powered playbook generation

## Index Details

| Table | Index | Type | Purpose | Migration |
|-------|-------|------|---------|-----------|
| rexus_incidents_v3 | `embedding_idx` | HNSW (vector_cosine_ops) | Sub-second vector similarity search | 001 |
| rexus_incidents_v3 | `short_description_idx` | GIN (pg_trgm) | Keyword trigram search | 001 |
| rexus_incidents_v3 | `idx_rexus_incidents_v3_trgm` | GIN (gin_trgm_ops) | Trigram similarity for hybrid search | 004 |
| rexus_incidents_v3 | `incident_number_key` | UNIQUE | Fast lookup by INC number | 001 |
| rexus_incidents_v3 | `split_group_idx` | B-tree | Filter training vs analyzed vs wave | 001 |
| rexus_incidents_v3 | `problem_id_idx` | B-tree | Problem suggestion scoring | 001 |
| rexus_incidents_v3 | `cmdb_ci_idx` | B-tree | CMDB family filtering | 001 |
| rexus_incidents_v3 | `opened_at_idx` | B-tree | Chronological ordering | 001 |
| rexus_analysis_log | `created_idx` | B-tree | Analysis history queries | 001 |
| rexus_analysis_log | `idx_analysis_log_incident` | B-tree (partial) | Per-incident analysis lookups | 004 |
| rexus_feedback | `idx_feedback_incident` | B-tree (partial) | Per-incident feedback lookups | 004 |
| rexus_wave_results | `wave_idx` | B-tree | Wave test result queries | 001 |
| rexus_token_usage | `created_idx` | B-tree | Token usage dashboard | 003 |
| rexus_users | `idx_rexus_users_username` | B-tree | Fast username lookup for login | 005 |
| rexus_users | `idx_rexus_users_role` | B-tree | Role-based user queries | 005 |

## Data Flow

```mermaid
flowchart TB
    SN[ServiceNow API<br/>Read-Only<br/>OAuth 2.0]

    subgraph Login
        AUTH[POST /auth/login<br/>username + password]
        USERS[(rexus_users<br/>bcrypt hashes)]
        AUTH -->|Verify password| USERS
        AUTH -->|JWT token| TOKEN[Bearer Token<br/>for all API calls]
    end

    subgraph Bulk Sync
        SYNC[Sync Engine<br/>POST /sync/import]
    end

    subgraph User Input
        INC[Enter INC Number<br/>GET /fetch-incident/INC...]
        PDF[Upload PDF<br/>POST /parse-pdf]
    end

    SN -->|Batch fetch<br/>Table API + Detailed API| SYNC
    SYNC -->|PII strip + embed| V3[(rexus_incidents_v3<br/>16,892 incidents<br/>+ 1536-dim embeddings)]

    SN -->|Fetch single incident<br/>Detailed API| INC
    INC -->|ticket_json| ANALYZE[Analysis Engine<br/>POST /analyze]
    PDF -->|ticket_json| ANALYZE

    ANALYZE -->|Embed query| LLM_EMBED["LLM Provider<br/>(OpenAI or Bedrock)"]
    LLM_EMBED -->|1536-dim vector| ANALYZE
    ANALYZE -->|Hybrid search<br/>vector + trigram| V3
    V3 -->|Top N similar<br/>default 15| ANALYZE
    ANALYZE -->|Score problems<br/>CMDB family boost<br/>Open PRB priority| PROBLEMS[(rexus_problems<br/>300 PRBs)]
    ANALYZE -->|Generate playbook<br/>+ resolution notes| GPT[LLM Chat Model<br/>2 parallel calls]
    GPT --> ANALYZE
    ANALYZE -->|Log result| LOG[(rexus_analysis_log)]
    ANALYZE -->|Progressive learning<br/>insert + embed| V3
    ANALYZE -->|Track tokens| TOKENS[(rexus_token_usage)]
    ANALYZE -->|Return| RESULT[Analysis Result<br/>Confidence + Problem + Playbook<br/>+ Similar Incidents]

    USER2[User Feedback] -->|Text or voice| FB[(rexus_feedback)]
    FB -->|Linked via analysis_id| LOG
```

## Database Sizing

| Component | Current | At 25K incidents | At 100K incidents |
|-----------|---------|-----------------|-------------------|
| Incidents table | 400 MB | ~600 MB | ~2.4 GB |
| HNSW vector index | ~170 MB | ~250 MB | ~1 GB |
| Trigram index | ~50 MB | ~75 MB | ~300 MB |
| Clusters | ~100 MB | ~150 MB | ~500 MB |
| Analysis logs | ~500 MB | ~1 GB | ~5 GB |
| **Total** | **~1.2 GB** | **~2 GB** | **~9 GB** |

The HNSW index must fit in RAM for optimal performance. At 100K incidents (~1 GB index), a 32 GB RAM database instance has ample headroom.

---

*REX-US v8 | Data Model v2.0 — Auth + LLM provider abstraction*
