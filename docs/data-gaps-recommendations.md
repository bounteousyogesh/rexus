# REX-US: Data Gaps & Recommendations

## Problems We Intend to Solve

### 1. Problem Identification for New Incidents
**Gap:** Only 22% of training incidents have a structured `problem_id`. When a new incident comes in, the team spends time figuring out which existing Problem record to link it to.

**Recommendation:** Use vector similarity to find matching incidents that DO have `problem_id`, then recommend that problem. When no similar incident has a problem link and similarity is below 50%, explicitly tell the user "No existing problem matches — consider creating a new one."

**Data needed:** `problem_id` (structured, 22%), `u_jira_number` (11%), `work_notes` mentions of PRB/OPOS IDs.

**Risk:** 78% of training data has no problem_id. The system can only suggest problems when similar incidents with problems exist. This coverage will improve as more incidents get tagged over time.

---

### 2. Resolution Guidance (Playbook)
**Gap:** The current system only uses `close_notes` for playbooks. Close notes are often a 1-line summary ("order finalized"). The real investigation trail — who checked what system, what they found, what they escalated — lives in `work_notes`.

**Recommendation:** Build focused playbooks from the full investigation chain: `work_notes` (97% fill rate, avg 1,500 chars) + `close_notes` + `description`. Include structured fields: `u_order_number`, `u_jira_number`, `business_duration`, `reassignment_count`, `u_resolved_by`.

**Data gained:** work_notes adds the step-by-step investigation trail. For example, INC2128324's close notes say "alternate order created, original cancelled in ECC." But the work notes show a 70-day investigation across 4 people, 3 systems (GK, Hybris, ECC), with specific IDoc numbers and POS event states.

---

### 3. Better Similarity Matching
**Gap:** Current embeddings use only `short_description` (cleaned/templated). For Finance Posting incidents, this produces identical embeddings — all "Vision Manual Correction : Finance posting errors--Order:[ORDER] site:[SITE]-[Error]". The system can't distinguish "IDoc out-of-sequence" from "credit block" from "order cancelled".

**Recommendation:** Enrich embedding text with `description` (28% fill — but it's the ROOT CAUSE fingerprint when present), first `work_note`, `cmdb_ci`, `subcategory`, and `close_notes[:200]`. This separates incidents by their actual sub-pattern, not just their title template.

**Impact:** The description field contains markers like `#OOS - Finalized POS status not received in ECC` and `#Order creation idoc not received` that are highly discriminative. Even at 28% fill rate, these significantly improve sub-pattern separation.

---

## Data Quality Observations

### Fields with High Value but Low Fill Rate

| Field | Fill Rate | Value | Action |
|-------|-----------|-------|--------|
| `description` | 28% | Root cause fingerprint | Use when available; fallback to short_description |
| `problem_id` | 22% | Problem linkage | Core of problem recommendation; accept limitation |
| `u_jira_number` | 11% | JIRA ticket | Show when available; don't require it |
| `u_error_category` | 2% | Most precise classification | Use when available; huge discriminator |
| `u_order_type` | 2% | Order classification | Minimal value at current fill rate |
| `u_total_order_amount` | 0% | Financial impact | Not populated in dev instance |

### Fields with High Value and High Fill Rate

| Field | Fill Rate | Value |
|-------|-----------|-------|
| `work_notes` | 97% | Investigation trail — the gold mine |
| `business_duration` | 100% | Resolution time in business hours |
| `close_notes` | 100% | Final resolution summary |
| `cmdb_ci` | 100% | System identification |
| `reassignment_count` | 58% | Complexity indicator |
| `u_resolved_by` | 80% | Who actually fixed it |
| `u_resolution_confirmed_by` | 80% | Who validated the fix |

### Fields Available in API but NOT in PDF

These are operational metrics the team never sees in the PDF export but are available via the ServiceNow API:

| Field | Value for REX-US |
|-------|-----------------|
| `business_duration` | Compare predicted vs actual resolution time |
| `calendar_duration` | Total wall-clock time |
| `reassignment_count` | Complexity signal — more reassignments = harder problem |
| `made_sla` | SLA compliance tracking |
| `escalation` | Escalation level |
| `u_resolved_by` | Track which engineers handle which pattern types |
| `u_resolution_confirmed_by` | Validation chain |

---

## Confidence Thresholds

| Similarity | Action |
|-----------|--------|
| > 70% | Strong match — recommend problem, generate full playbook |
| 50-70% | Partial match — suggest problem with "review needed" flag |
| < 50% | Weak/no match — do NOT suggest problem, do NOT generate playbook |

---

## Progressive Validation Plan

| Wave | Size | Date Range | Purpose |
|------|------|-----------|---------|
| Training | 15,000 | 2021-01 → 2025-03 | Knowledge base |
| Wave 1 | 500 | 2025-03-04 → 2025-03-12 | Baseline measurement |
| Wave 2 | 300 | 2025-03-12 → 2025-03-18 | Validate improvements |
| Wave 3 | 300 | 2025-03-18 → 2025-03-23 | Further tuning |
| Wave 4 | 300 | 2025-03-23 → 2025-03-28 | Stability check |
| Wave 5 | 500 | 2025-03-28 → 2025-04-04 | Larger validation |
| Reserve | 1,336 | 2025-04-04 → 2025-10-28 | Final acceptance (never touch until ready) |

Each wave produces a scorecard with:
- Problem match accuracy (exact match, wrong suggestion, correct "no match")
- Top failure patterns
- Changes made
- Impact on next wave

---

*Generated: 2026-03-27 | REX-US v2 — Enriched Data*
