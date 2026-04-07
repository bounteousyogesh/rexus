# REX-US — The Journey

A presentation on how we built, iterated, and validated an AI-powered incident intelligence system for Discount Tire.

---

## The Problem

Discount Tire's Information Center handles thousands of ServiceNow incidents every month across 25+ systems — GK POS, Vision, Hybris, SAP, and more.

When a new incident arrives, a support engineer must:

1. Read the incident description and figure out what's actually broken
2. Search through **300+ active Problem records** to find the right one to tag it to
3. Look up past similar incidents to understand how the team resolved them before
4. Write resolution steps from scratch — often for the same issue pattern the team has solved dozens of times

**The pain:**
- This process takes 10-15 minutes per incident — sometimes longer for complex issues
- Accuracy depends entirely on the individual engineer's experience and memory
- New team members take 3-6 months to build the tribal knowledge needed to triage effectively
- When experienced engineers leave, that knowledge walks out the door
- 60% of incidents are resolved but never tagged to a Problem — recurring patterns go undetected

**The question we set out to answer:** Can AI identify the correct problem pattern and generate useful resolution guidance — instantly, consistently, and without hallucinating?

---

## How We Started

### Step 1: Build the Foundation

We built a full-stack system from scratch:
- **Backend:** Python FastAPI (async, production-grade)
- **Frontend:** React + TypeScript + Tailwind (clean, fast UI)
- **Database:** PostgreSQL with pgvector extension (vector similarity search)
- **AI:** OpenAI embeddings (text-embedding-3-small, 1536 dimensions) + GPT for playbook generation

### Step 2: Ingest the Data

We pulled incident data from ServiceNow's API and enriched it:
- Started with basic fields: short_description, category, cmdb_ci, close_notes
- Expanded to **52 fields** per incident — including work notes, resolution details, order data, JIRA references, operational metrics
- Built a custom ServiceNow API integration using OAuth 2.0 (read-only)

### Step 3: First Embeddings (v1)

Our first attempt embedded only the `short_description` field:
- Simple and fast
- Problem: many incident titles are generic — "Vision SO: 5065487426 / 1281 Incorrect" tells you nothing about the actual issue

This was the start. What followed was a series of iterations, each driven by testing, user feedback, and debate.

---

## The Iteration Journey

### v1 → v2: PII Stripping

**Problem discovered:** Incident text contains employee names, phone numbers, order numbers, and customer details. We can't send PII to OpenAI.

**What we built:**
- Regex-based pipeline to strip order numbers, phone numbers, emails, store codes, dollar amounts
- spaCy NER (en_core_web_sm) to detect and remove PERSON entities
- Known names list from the database for additional coverage
- Generic stop word removal ("issue", "error", "please", "fix") to reduce noise in embeddings

**Result:** Cleaner embeddings with no PII leakage. Every incident in the knowledge base was processed through this pipeline.

---

### v2 → v3: The Comments Breakthrough

**The moment that changed everything.**

User feedback session — the team tested with 31 real tickets. Suggestions #2 through #5 all had the same problem:

> "Playbook referred this as a Bay-out issue and provided troubleshooting steps to see POS and Finalize it. The actual issue is missing credit card information."

**Root cause analysis:** The incident title was generic — "Vision SO: 5065487426 / 1281 Incorrect". The critical detail ("Mandatory Credit card details are missing") was buried in the **additional comments** field, which our embedding didn't include.

**The debate:** Should we include all comments? Just the first one? Work notes too?

**Decision:** Include comments + IDoc text + Initial Finding + Error Category + first substantive work note in the embedding. This was v3 — a much richer signal for the vector search.

**The other critical feedback — Suggestion #6:**

> "If we have an option where it only analyzes the open problems instead of giving us closed problems, that will also be helpful."

We discovered that our top two most-suggested problems (PRB0015470 with 635 incidents, PRB0015471 with 189 incidents) were both **Cancelled**. Technically correct suggestions — but the team literally cannot tag to a cancelled problem in ServiceNow.

**What we built:** Cached all 300 problem states from ServiceNow. Added an Open problem filter that prioritizes Open problems over Cancelled/Closed.

---

### The Search Architecture Debate

**The question:** How do we find the most similar incidents?

**Vector search alone** had a problem — it's great at semantic similarity but misses exact keyword matches. An incident about "GK POS frozen on Please Wait screen" might not match "POS stuck on Please Wait" purely by vector distance.

**The suggestion:** What about keyword matching alongside vector search?

**The debate that followed:**
- Do we take the **top 15 from vector** and the **top 15 from keyword** independently?
- Do we take the **intersection** — only incidents that appear in both results?
- Do we **union** them and re-rank?
- What if one method finds something the other misses?

**Decision: Hybrid search with agreement bonus.**
- Run vector search and keyword search (PostgreSQL trigram similarity) independently
- Merge results: for each incident, take `MAX(vector_score, keyword_score)`
- If both methods found the same incident (agreement), add a small bonus: `min(vec, kw) * 0.05`
- This rewards incidents that match both semantically and lexically — they're almost certainly relevant

**Why not intersection?** Intersection would miss incidents where vector finds a great semantic match but keywords differ (e.g., "POS frozen" vs "register stuck"). Union with re-ranking was the right answer.

---

### v3 → v4: The Hard CMDB Filter (Too Aggressive)

**The problem:** Cross-system predictions. A Vision Missing Orders incident getting matched to a GK POS problem because the symptom description is similar.

**The idea:** Hard filter — only suggest problems from the same CMDB system.

**What happened:** Vision Missing Orders accuracy dropped to **0%**. Why? Because many Vision Missing Orders incidents were historically resolved using techniques from Vision Manual Corrections — a related but different CMDB CI. The hard filter blocked these valid cross-system matches.

**Lesson learned:** The CMDB system name is not a clean boundary. Related systems (Vision Manual Corrections, Vision Missing Orders, Vision Payments) share resolution patterns.

---

### v4 → v5: CMDB Family Mapping

**The fix:** Instead of hard filtering on exact CMDB CI match, we mapped related systems into families:

```
Vision Family:  Vision Manual Corrections, Vision Missing Orders,
                Vision Payments, Vision Update After Final
Hybris Family:  Hybris, Hybris 1.2, SAP Hybris
GK POS Family:  GK POS, GK Launchpad, Store POS
SAP Family:     SAP OMS, SAP Fiori, SAP ECC, SAP CAR
POS Features:   Product Browse, CVM, CSL, BOPIS
```

**v5 used a hard family filter** — only suggest problems from the same family.

**Result:** Better than v4 (no more 0% waves), but still too aggressive. Some valid cross-family matches were blocked.

---

### v5 → v6: The Training Data Experiment

**The question:** Does older data help or hurt?

We discovered that problem tagging quality changed dramatically over time:
- 2021-2023: only ~1% of incidents had problem tags
- 2024 Q3 onward: 40%+ had tags

**v6 experiment:** Drop the oldest 5,000 incidents (2021-2022), keep only the latest 10,000.

**Result:** 55 exact matches (vs 54 with full data) — marginal improvement. But the smaller training set meant less pattern coverage for rare incident types. We kept the full 15K for production.

---

### v6 → v7: The Production Candidate

**v7 combined the best of everything:**
- v3 embeddings (comments + IDoc text + work notes)
- Hybrid search (vector + keyword with agreement bonus)
- CMDB family mapping as a **soft boost** (not hard filter)
- Open problem prioritization (not hard exclusion)
- Full 15K training set

**Why soft boost instead of hard filter?**

A hard filter says: "Never suggest a problem from a different system family." This blocks rare but valid cross-family matches.

A soft boost says: "Same family? Add a scoring bonus. Different family? Still allow it if the similarity is strong enough." This preserves flexibility while rewarding system alignment.

**The verdict was driven by user testing (31 real tickets):**

| Version | Open PRB Suggested | Cancelled PRB | User Satisfaction |
|---------|-------------------|---------------|-------------------|
| v3 | 58% | 29% | ~17% |
| v4 | 74% | 19% | 74% |
| v5 | 77% | 10% | 74% |
| v6 | 81% | 6% | — |
| **v7** | **87%** | **6%** | **Best** |

**v7 was selected for production** — not because it had the highest strict accuracy (v3 actually scored higher on that), but because it had the highest practical value: 87% of suggestions pointed to Open problems that users can actually tag to.

---

## Validation

### The Testing Methodology

**Chronological train/test split** — not random. We trained on the oldest 15,000 incidents and tested on the newest 1,899 in 5 progressive waves.

**Progressive learning** — each wave's incidents are added to the knowledge base after testing, so later waves benefit from earlier ones. This mirrors how the system would work in production.

**Why 5 waves?** Each wave tests a different time period. If accuracy is consistent across waves, the system generalizes well. If it degrades, there's a time-dependent pattern we missed.

### Wave Results (1,899 incidents)

**Testable incidents (754 — had actual Problem tagged by team):**

| Wave | Testable | Exact | Top3 | Expanded (CMDB Family) | Real Misses |
|------|----------|-------|------|------------------------|-------------|
| Wave 1 | 142 | 54 | 8 | 140 = **98%** | 2 (1%) |
| Wave 2 | 134 | 25 | 11 | 130 = **97%** | 4 (3%) |
| Wave 3 | 100 | 18 | 4 | 96 = **96%** | 4 (4%) |
| Wave 4 | 171 | 19 | 7 | 168 = **98%** | 3 (2%) |
| Wave 5 | 207 | 29 | 8 | 200 = **96%** | 7 (3%) |
| **Total** | **754** | **145** | **38** | **734 = 97%** | **20 (2.6%)** |

**Why is strict accuracy only 24%?** ServiceNow has massive PRB fragmentation. The team creates multiple Problem records for the same issue pattern:

```
PRB0015735: "GK POS Stuck On Please Wait - Attempting to..."
PRB0015736: "GK POS Stuck On Please Wait - Attempting to..."
PRB0015628: "GK POS Stuck On Please Wait - Attempting to..."
```

Three different PRBs, same issue. Our system picks one; the team tagged another. Both are correct. When we expand to include same-family matches, accuracy jumps to 97%.

### GPT-5.4 Semantic Validation (Non-Testable Incidents)

For the 1,145 incidents where the team never tagged a Problem, we asked: "Were our suggestions any good?"

692 of those got a suggestion from our system. We validated each one by sending the incident and the suggested problem's evidence to **GPT-5.4** and asking it to rate the match on a 1-5 scale with an explanation.

| Rating | Meaning | Count | % |
|--------|---------|-------|---|
| **5/5** | Identical issue pattern | 151 | 21% |
| **4/5** | Strongly related | 261 | 37% |
| **3/5** | Related — helps the engineer | 94 | 13% |
| **2/5** | Weakly related | 148 | 21% |
| **1/5** | Unrelated — wrong suggestion | 38 | 5% |

**73% of suggestions on untagged incidents were useful (3-5).** Only **5% were genuinely wrong.**

Every single GPT-5.4 prompt and response is saved as an artifact — 692 records with full reasoning that can be reviewed by any stakeholder.

---

## What We Learned

### 1. The Data Matters More Than the Algorithm

The biggest accuracy jump came not from a smarter algorithm but from richer embeddings. Including comments and work notes (v3) fixed the entire class of "bay-out suggested instead of credit card" errors.

### 2. PRB Fragmentation Is the Real Enemy

63% of all "wrong" predictions are actually correct — they identify the right issue pattern but point to a sibling PRB. This is a ServiceNow data quality issue, not an algorithm failure. It also represents an opportunity: REX-US can help identify PRBs that should be consolidated.

### 3. Hard Filters Break Things; Soft Boosts Work

Hard CMDB filtering (v4) caused 0% accuracy on some system categories. Soft family boosting (v7) achieves the same goal without breaking edge cases. The lesson: in messy real-world data, flexible scoring beats rigid rules.

### 4. Users Care About Actionability, Not Accuracy

The team didn't care that v3 had higher "strict accuracy." They cared that v7 suggested Open problems they could actually tag to. We chose the production candidate based on user satisfaction (87% Open suggestions), not test metrics.

### 5. 60% of Incidents Are Untagged — That's Where AI Adds the Most Value

The team never tagged a Problem on 60% of incidents. REX-US suggested useful problems for 73% of those. This isn't just matching — it's surfacing patterns the team missed.

---

## The Final Numbers

| Metric | Result |
|--------|--------|
| Total incidents tested | 1,899 (5 progressive waves) |
| Knowledge base size | 16,892 embedded incidents |
| Testable accuracy (expanded) | **97%** |
| Testable real miss rate | **2.6%** |
| Non-testable useful suggestion rate | **73%** (GPT-5.4 validated) |
| Non-testable wrong suggestion rate | **5%** |
| Algorithm versions tested | **7** |
| User feedback sessions | **31 real tickets** |
| Code review rounds | **2** (121 findings addressed) |
| Automated test cases | **213** |

---

## What's Next

| Phase | Status |
|-------|--------|
| v7 algorithm validated | Done |
| Full 5-wave testing | Done |
| GPT-5.4 semantic validation | Done |
| Security hardening (2 rounds) | Done |
| AWS + Azure deployment architectures | Done |
| Production ServiceNow access | Waiting on DT Admin |
| Cloud infrastructure | Waiting on DT IT |
| SSO authentication | Waiting on cloud infra |
| First user pilot | Ready when infra is ready |

---

*REX-US v7 — Built by VISHKAR | 2026-04-01*
