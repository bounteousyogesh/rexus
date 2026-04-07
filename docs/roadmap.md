# REX-US — Product Roadmap

Based on the full NEXUS vision and current REX-US capabilities.

---

## Phase 1: Incident Intelligence (Current — Complete)

**Goal:** AI-powered incident analysis with playbook generation and problem suggestion.

| Feature | Status | Description |
|---------|--------|-------------|
| Incident analysis (PDF/JSON/text) | Done | Upload an incident, get similar matches, problem suggestion, and playbook |
| Vector similarity search (pgvector HNSW) | Done | Hybrid search — vector + keyword with agreement bonus |
| Problem tag suggestion (v7 algorithm) | Done | CMDB family-aware soft boost + open problem prioritization |
| Focused playbook generation | Done | GPT-generated from top 15 similar incidents, grounded in evidence |
| Resolution notes | Done | Detailed evidence with incident references, order IDs, JIRA tickets |
| Progressive learning | Done | Every analyzed incident added to knowledge base automatically |
| Incident browser with search/filter | Done | Browse, search, filter by category/system |
| Cluster explorer | Done | View incident groups with playbooks |
| Dashboard analytics | Done | Incident counts, categories, systems, resolution times |
| Text + voice feedback | Done | Linked to analysis, Whisper transcription for voice |
| ServiceNow sync (read-only) | Done | Delta check + batch import via OAuth 2.0 |
| PII stripping (regex + spaCy NER) | Done | Names, phones, emails, orders stripped before AI processing |
| Prompt injection protection | Done | Truncation + pattern redaction + grounding |
| Security headers + input validation | Done | All endpoints validated, security headers on every response |
| Rate limiting | Done | Per-endpoint configurable limits via slowapi |
| Token usage tracking | Done | Every OpenAI call logged with cost estimates + dashboard endpoint |
| 5-wave validation (1,899 incidents) | Done | 97% expanded accuracy, 73% useful on untagged (GPT-5.4 validated) |

---

## Phase 2: Production Deployment & Monitoring

**Goal:** Deploy to DT infrastructure with SSO, monitoring, and team onboarding.

| Feature | Priority | Description |
|---------|----------|-------------|
| SSO authentication | High | AWS IAM Identity Center or Azure AD integration. Role-based access — who can analyze, who can sync, who can admin. |
| Token usage dashboard (UI) | High | Frontend page showing daily/monthly token usage, cost by model, cost by endpoint. Data already available via `/api/v1/token-usage`. |
| Production ServiceNow access | High | Switch from dev to production/sandbox ServiceNow credentials. Validate against live incident data. |
| Non-prod / prod environment separation | High | Separate databases, separate configs, deployment pipeline for each. |
| User activity logging | Medium | Track who analyzed what, when. Tie analyses to authenticated user IDs. |
| Scheduled sync (automated) | Medium | Lambda/cron job to sync new incidents weekly without manual trigger. |
| End-user onboarding | Medium | Training sessions + user guide distribution to the support team. |
| Monitoring & alerting | Medium | CloudWatch dashboards for API response times, error rates, token spend, SN sync health. |

---

## Phase 3: Cross-System Verification (Read-Only)

**Goal:** Expand from incident analysis to real-time order verification across GKPOS, SAP ECC, and Hybris.

| Feature | Priority | Description |
|---------|----------|-------------|
| Read-only system connectors | High | API integration with GKPOS, SAP ECC, Hybris — fetch order data in real time. No write access. |
| Cross-system order comparison | High | Given an order number, pull data from all 3 systems and compare amounts, items, statuses, customer data. Surface discrepancies. |
| Verify Agent | High | AI agent that receives an incident, fetches order from all systems, identifies exactly what's inconsistent and where. Replaces manual "check POS, then check Hybris, then check SAP" process. |
| Authoritative source rules | Medium | Codified business rules: GKPOS is authority for prices/line items, SAP ECC for taxes/payments, etc. Used by Verify Agent to determine which system has the correct value. |
| CMDB-aware routing | Medium | Automatically determine which systems to check based on the incident's CMDB CI. Vision incidents → check Hybris + SAP. GK POS incidents → check GKPOS + SAP. |
| Verification audit trail | Medium | Log every cross-system check with before/after data, compliance tags, and actor tracking. |

---

## Phase 4: Automated Resolution (With Approval)

**Goal:** Generate and apply fixes across systems — with human approval before execution.

| Feature | Priority | Description |
|---------|----------|-------------|
| Execute Agent | High | Given discrepancies from Verify Agent, generate specific fix commands for each system. Present to the engineer for approval. |
| Fix proposals with preview | High | Show exactly what will change in each system before execution. "Update SAP ECC order 5033271058: tax amount $23.00 → $24.15 (source: GKPOS)." |
| Confirmation workflow | High | Engineer reviews proposed fixes, approves or rejects each one. Only approved fixes are applied. |
| System write connectors | High | Write access to GKPOS, SAP ECC, Hybris for applying approved fixes. Requires separate credentials with write permissions. |
| Rollback capability | Medium | If a fix causes issues, ability to revert to the pre-fix state using the audit trail snapshots. |
| Escalation routing | Medium | If the system can't determine the fix or confidence is low, auto-escalate to the appropriate team with full context. |
| ServiceNow write-back | Low | Update the ServiceNow incident with resolution details, close notes, and problem tag after fix is applied. |

---

## Phase 5: Proactive Monitoring & Learning

**Goal:** Shift from reactive analysis to proactive detection and continuous improvement.

| Feature | Priority | Description |
|---------|----------|-------------|
| Monitor Agent | High | Real-time event stream from GKPOS, SAP ECC, Hybris. Detect order discrepancies as they happen — before a ticket is filed. |
| Event-driven triggers | High | When a new order is finalized in GKPOS, automatically verify it against SAP and Hybris. Surface issues within minutes, not days. |
| Learn Agent | High | Analyze all resolved incidents to extract patterns. "70% of Vision Missing Orders are caused by IDoc delivery failures. Suggest: monitor IDoc queue length." |
| Pattern-based alerting | Medium | "We've seen 5 BOPIS payment errors in the last hour from store AZ-14. This matches the pattern from PRB0015575. Alerting the team." |
| SLA breach prediction | Medium | Based on similar incidents, predict how long this one will take. Alert if SLA breach is likely. |
| Knowledge base auto-enrichment | Medium | Learn Agent automatically updates CMDB family mappings, problem groupings, and playbook templates based on new data. |
| Trend detection | Low | Identify emerging issue patterns before they become widespread. "Finance posting errors increased 40% this week — new deployment?" |

---

## Phase 6: Enterprise Scale & Multi-Tenancy

**Goal:** Support multiple teams, departments, or customers on the same platform.

| Feature | Priority | Description |
|---------|----------|-------------|
| Multi-tenant architecture | High | Separate knowledge bases per tenant. Shared infrastructure, isolated data. |
| Automated onboarding | High | Give ServiceNow credentials → system auto-discovers schema, creates family mappings, builds knowledge base, runs validation. |
| Role-based access control | Medium | Admin, analyst, viewer roles. Control who can sync, who can analyze, who can approve fixes (Phase 4). |
| Tenant-specific model config | Medium | Each tenant can choose their LLM model (GPT-5.4 vs Mini vs Nano) and configure thresholds. |
| Cross-tenant learning | Low | Anonymized pattern sharing across tenants. "Tenant A discovered that adding work notes to embeddings improved accuracy — apply to Tenant B?" |
| Usage metering & billing | Low | Track token usage and compute per tenant for chargeback or billing. |

---

## Phase Summary

| Phase | Focus | Risk | Dependency |
|-------|-------|------|------------|
| **Phase 1** | Incident intelligence | None — read-only, proven | **Complete** |
| **Phase 2** | Production deployment | Low — infrastructure setup | DT IT, ServiceNow admin |
| **Phase 3** | Cross-system verification | Low — read-only system access | GKPOS, SAP, Hybris API access |
| **Phase 4** | Automated resolution | Medium — writes to production systems | Phase 3 validated + write credentials |
| **Phase 5** | Proactive monitoring | Medium — real-time infrastructure | Event streams from source systems |
| **Phase 6** | Multi-tenancy | Low — architecture change | Business decision to scale |

---

*REX-US Roadmap v1.0 | 2026-04-05*
