# REX-US — Research Analysis

## 1. Data Sources Assessment

### ServiceNow Dev Instance (dtcdev.service-now.com) — PRODUCTION REPLICA
- **Total incidents**: 877,470 (production data replicated before Dec 25, 2025)
- **Vision/GK POS/Finance (excl test data)**: 18,252 with close notes
- **CMDB CI = GK POS with close notes**: 7,885
- **All Software category with close notes**: 691,015
- **Data quality (sample of 200)**:
  - Close notes: 100% | Description: 37% | CMDB CI: 97% | Problem ID: 63%
  - Top assignment groups: Information Center (45%), Application Support (29%), POS Services - Vision (7%)
  - Top CMDB CIs: GK POS (49%), POS CSL (8%), Vision Manual Corrections (7%), Hybris 1.2 (5%)
  - Systems detected: GKPOS (89%), SAP ECC (29%), Mulesoft (25%), Hybris (11%)
  - Embedding text: avg 407 chars / ~101 tokens, max 3,215 chars / ~803 tokens
- **Verdict**: USABLE — real production data. Filter out "RANDOM TEST DATA" prefix and use pre-Christmas 2025 incidents.

### Production Incidents (60 extracted, local)
- **Total**: 60 real GK POS / SAP ECC incidents
- **Quality**: High — real Finance posting errors, payment mismatches, missing orders
- **Resolution steps**: 100% have 4-6 steps each
- **Problem IDs**: 100% mapped (PRB0016221, PRB0016251, etc.)
- **Systems involved**: GKPOS, SAP ECC tagged
- **Gap**: Work notes not fully extracted (exist in source PDFs)
- **Verdict**: USE THESE as the foundation for development and testing

### Confluence (pending access)
- OAuth 2.0 works, but v2 scopes needed
- Will contain: architecture diagrams, release notes, RCA documents, runbooks
- Purpose: Build the "how it SHOULD work" knowledge bank

### JIRA (access confirmed)
- OAuth 2.0 working, full project list accessible
- Cloud ID: 4897d307-327f-4624-8413-009ff77cda88
- Will contain: implementation details, sprint work, bug fixes

---

## 2. Embedding & Dimensions Analysis

### Current: text-embedding-3-small (1,536 dimensions)

| Metric | Value |
|--------|-------|
| Dimensions | 1,536 |
| Max input tokens | 8,191 |
| Cost per 1M tokens | $0.02 |
| Cost for 12K incidents (est.) | ~$0.50 |

### Do We Need More Dimensions?

| Model | Dims | MTEB Score | Storage per 12K | Search Speed |
|-------|------|------------|-----------------|--------------|
| text-embedding-3-small | 1,536 | 62.3% | ~73 MB | Fast |
| text-embedding-3-large | 3,072 | 64.6% | ~147 MB | 2x slower |

**Recommendation: Stay with 1,536.** The 2.3% accuracy improvement from 3,072 dims doesn't justify doubling storage and search time at our scale (12K incidents). At 100K+ incidents, revisit.

### Will Incidents Fit Without Chunking?

| Scenario | Est. Tokens | Fits in 8,191? |
|----------|-------------|----------------|
| Title only | ~30 | Yes |
| Title + description | ~100-250 | Yes |
| Title + desc + work notes (3-10 entries) | ~500-1,750 | Yes |
| Title + desc + ALL work notes + resolution | ~1,000-3,000 | Yes |
| Extreme outlier (50+ work notes) | ~5,000-7,000 | Yes |

**No chunking needed.** Every incident fits in a single embedding. This preserves full semantic context — a major advantage over systems that must chunk documents.

---

## 3. Scale Parameters

### Target: 12,000 incidents (1,000/month × 12 months rolling)

### Storage Estimates

```
Vector data:     12,000 × 1,536 dims × 4 bytes  = 73 MB
HNSW index:      ~2-3x vector size               = ~180 MB
Incident metadata: 12,000 × ~2 KB                = 24 MB
Work notes:      12,000 × ~5 KB avg              = 60 MB
Cluster data:    ~200 clusters × centroids        = 1 MB
Playbooks:       ~200 × 10 KB avg                = 2 MB
──────────────────────────────────────────────────────────
Total active:    ~340 MB
With headroom:   ~500 MB
```

### Backup Requirements

```
Daily snapshot:     ~500 MB compressed
30-day retention:   ~15 GB
Annual archive:     ~6 GB (monthly snapshots)
```

### Infrastructure

PostgreSQL with pgvector handles 12K vectors easily. Railway's 1GB RAM plan works. For production, recommend 2GB RAM to keep the HNSW index in memory for sub-10ms search.

---

## 4. Recency Weighting

Incidents from recent months should rank higher than year-old incidents because:
- Underlying architecture changes over time
- Resolution procedures evolve
- Team knowledge improves

### Approach: Time-Decayed Similarity

```
final_score = cosine_similarity × recency_weight

recency_weight = max(0.5, 1.0 - (age_in_months × 0.04))

Examples:
  This month:   1.0 × similarity
  3 months ago: 0.88 × similarity
  6 months ago: 0.76 × similarity
  12 months ago: 0.52 × similarity
  >12 months:   archived (not in active search)
```

### Rolling Window
- Active index: last 12 months (searchable, weighted)
- Archive: >12 months (queryable on demand, not in default search)
- Monthly job: archive expired incidents, rebuild HNSW index

---

## 5. Key Findings from Production Incident Analysis

### 60 Production Incidents Profile

| Field | Coverage | Notes |
|-------|----------|-------|
| Short description | 100% | "Vision Manual Correction : Finance posting errors..." |
| Resolution steps | 100% | 4-6 steps per incident |
| Problem ID | 100% | PRB0016221, PRB0016251 |
| Systems involved | 100% | GKPOS, SAP ECC |
| Category | 100% | Software (92%), Resolution (8%) |
| Priority | 100% | 2-High (98%), 3-Medium (2%) |
| Description | 0% | Not extracted in PoC — available in source PDFs |
| Work notes | 0% | Not extracted in PoC — available in source PDFs |

### Incident Types (from titles)

| Pattern | Count | Problem ID |
|---------|-------|------------|
| Finance posting errors | ~45 | PRB0016221, PRB0016251 |
| Missing Order | ~8 | Various |
| Payment mismatch | ~4 | Various |
| IDOC failures | ~3 | Various |

### Gap: Work Notes

Work notes are the most valuable field for playbook generation — they contain what engineers actually did to resolve the issue. Our PoC extracted titles and resolution steps but not the full work note history.

**Priority action**: Re-extract work notes from source PDFs, or pull from production ServiceNow when access is granted.
