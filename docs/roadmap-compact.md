# REX-US — Product Roadmap

### Phase 1: Incident Intelligence (Complete)

AI-powered incident analysis that finds similar past incidents, suggests the correct Problem record, and generates evidence-grounded playbooks. Support engineers upload an incident (PDF, JSON, or plain text) and get a confidence-scored recommendation with step-by-step resolution guidance in under 15 seconds. The knowledge base of 16,900+ embedded incidents grows automatically with every analysis through progressive learning. Validated across 1,899 incidents with 97% pattern accuracy and 73% useful suggestions on untagged incidents (GPT-5.4 verified). Includes PII stripping, prompt injection protection, rate limiting, token usage tracking, and full security hardening across two review rounds.

### Phase 2: Production Deployment

Deploy to DT infrastructure with SSO authentication, environment separation (non-prod/prod), and operational monitoring. Add a token usage dashboard in the UI so the team can track API costs. Connect to production ServiceNow for live incident data. Set up automated weekly sync so the knowledge base stays current without manual imports. Onboard the support team with training sessions and the user guide. Stand up CloudWatch dashboards for API health, error rates, and cost alerts.

### Phase 3: Cross-System Verification (Read-Only)

Expand from incident analysis to real-time order verification. Connect read-only to GKPOS, SAP ECC, and Hybris so that when an incident comes in, the system can automatically fetch the order from all three systems and compare amounts, items, statuses, and customer data. A Verify Agent identifies exactly what's inconsistent and where — replacing the manual process of checking each system one by one. Business rules codify which system is the authority for each data type: GKPOS for prices and line items, SAP ECC for taxes and payments, Hybris for order status. Every cross-system check is logged in a compliance-grade audit trail.

### Phase 4: Automated Resolution (With Approval)

Move from recommending fixes to generating and applying them — with human approval before any change is made. An Execute Agent takes the discrepancies found by the Verify Agent and proposes specific fixes for each system: "Update SAP ECC order tax from $23.00 to $24.15 (source: GKPOS)." The engineer previews exactly what will change, approves or rejects each fix, and only approved changes are applied. Includes rollback capability using audit trail snapshots. Optionally writes resolution details back to ServiceNow to close the loop.

### Phase 5: Proactive Monitoring & Learning

Shift from reactive (engineer uploads a ticket) to proactive (system detects issues before a ticket exists). A Monitor Agent watches real-time event streams from GKPOS, SAP ECC, and Hybris. When a new order is finalized, it automatically verifies across systems and surfaces discrepancies within minutes — not days. A Learn Agent analyzes all resolved incidents to extract patterns, predict SLA breaches based on similar past cases, and detect emerging trends before they become widespread. The knowledge base self-enriches: family mappings, problem groupings, and playbook templates update automatically as new patterns emerge.

### Phase 6: Enterprise Scale & Multi-Tenancy

Support multiple teams, departments, or customers on the same platform with isolated knowledge bases and shared infrastructure. Automated onboarding: provide ServiceNow credentials, and the system auto-discovers the schema, creates family mappings, builds the knowledge base, and runs validation. Each tenant configures their own LLM model, thresholds, and CMDB families. Role-based access controls who can analyze, sync, or approve fixes. Cross-tenant learning allows anonymized pattern sharing — when one tenant discovers an improvement, others can benefit.

---

*REX-US Roadmap v1.0 | 2026-04-05*
