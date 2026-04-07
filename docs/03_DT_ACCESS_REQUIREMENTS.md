# REX-US — DT Enterprise Access Requirements

REX-US has **two independent tracks**. Each can go live independently.

```
Track A: Ticket Analysis         → ServiceNow + JIRA + Confluence
Track B: Order Reconciliation    → Needs GKPOS + SAP ECC + Hybris (or any subset)
```

---

## Track A: Ticket Analysis (ServiceNow + JIRA + Confluence)

This is the fastest path to production. We already have 60 incidents embedded, 7 clusters, and playbooks generated. With API access to ServiceNow, JIRA, and Confluence, this goes live immediately.

### What It Does Today (Demo)
- Upload a ServiceNow incident JSON → generates embedding → finds similar incidents via pgvector → recommends playbook
- Clusters incidents by root cause pattern
- Knowledge bank with resolution playbooks

### What It Needs to Go Enterprise

#### ServiceNow

| # | Requirement | What REX-US Does With It | Details |
|---|-------------|------------------------|---------|
| A.1 | **ServiceNow REST API — Read** | Pull incidents automatically instead of manual JSON upload | OAuth 2.0 or Basic Auth for `/api/now/table/incident` |
| A.2 | **ServiceNow Webhook (Outbound REST Message)** | Real-time: new incident created → REX-US instantly analyzes it | DT configures a Business Rule: `on insert` on `incident` table → POST to REX-US `/api/servicenow/webhook` |
| A.3 | **ServiceNow Read Scopes** | Pull full incident context (related CIs, assignment groups) | `read` on: `incident`, `problem`, `cmdb_ci`, `sys_user_group` |
| A.4 | **ServiceNow Write (Phase 2)** | Push AI resolution notes back to the incident | `write` on `incident.work_notes` and `incident.close_notes` |
| A.5 | **ServiceNow Integration User** | Dedicated service account | API-only, no MFA, scoped to above tables |

#### JIRA

| # | Requirement | What REX-US Does With It | Details |
|---|-------------|------------------------|---------|
| A.6 | **JIRA REST API — Read** | Learn proven solution steps from historical tickets | API Token with read-only permissions |
| A.7 | **JIRA Read Scopes** | Extract resolution details, comments, root cause notes | Read access to: issues, comments, descriptions, resolution fields |
| A.8 | **JIRA JQL Search** | Query tickets by project, component, date range | Search via JQL to pull relevant incident-related tickets |

#### Confluence

| # | Requirement | What REX-US Does With It | Details |
|---|-------------|------------------------|---------|
| A.9 | **Confluence REST API — Read** | Enrich knowledge base with product docs, runbooks, release notes | API Token with read-only permissions |
| A.10 | **Confluence Space Access** | Read technical guides and process documentation | Read access to relevant documentation spaces |

### Flow: How It Works Enterprise

```
ServiceNow / JIRA / Confluence              REX-US
──────────────────────────────              ──────
Historical incidents (ServiceNow)  ──API──►  Embed & build knowledge base
Historical tickets (JIRA)          ──API──►  Extract proven solutions
Documentation (Confluence)         ──API──►  Enrich with runbooks & guides
                                             │
New incident created (ServiceNow)  ─webhook─►│
                                             ├─ Extract & clean text
                                             ├─ Generate embedding (OpenAI text-embedding-3-small)
                                             ├─ pgvector similarity search against knowledge base
                                             ├─ Cross-reference with JIRA solutions & Confluence docs
                                             ├─ Match to cluster → retrieve playbook
                                             ├─ LLM generates resolution recommendation
                                             │
                                             ▼
                               ◄──REST API──  POST work_notes back to incident
                                             "AI Recommendation: [playbook steps]"
```

**No access needed to GKPOS, SAP, or Hybris for this track.**

---

## Track B: Order Reconciliation (Monitor → Verify → Execute → Learn)

This is the cross-system agent pipeline. Currently runs on simulators. Here's what each agent actually needs:

### How the Agent Pipeline Works

```
User edits an order on Systems page
        │
        ▼
   Audit Trail created (AuditService)
        │
        ▼
   ┌─────────────────────────────────────────────────┐
   │  MONITOR AGENT                                   │
   │  Input:  Order ID + which system changed          │
   │  Action: Fetch same order from ALL 3 systems      │
   │          Compare total_amount, tax, status, etc.   │
   │  Output: List of discrepancies found               │
   │  Needs:  READ access to GKPOS, SAP ECC, Hybris    │
   └─────────────────┬───────────────────────────────┘
                     │
                     ▼
   ┌─────────────────────────────────────────────────┐
   │  VERIFY AGENT                                     │
   │  Input:  Discrepancies from Monitor               │
   │  Action: Fetch fresh data from each system         │
   │          Field-by-field comparison                 │
   │          Determine which system is authoritative   │
   │  Output: Confirmed discrepancies + root cause      │
   │  Needs:  READ access to GKPOS, SAP ECC, Hybris    │
   └─────────────────┬───────────────────────────────┘
                     │
                     ▼
   ┌─────────────────────────────────────────────────┐
   │  EXECUTE AGENT                                    │
   │  Input:  Verified discrepancies + auth source      │
   │  Action: Generate fix commands (API calls)         │
   │          User reviews → Approve or Reject          │
   │          Apply fix to non-authoritative systems    │
   │  Output: Fix applied or rejected with feedback     │
   │  Needs:  WRITE access to target systems            │
   │          (e.g., update SAP price from GKPOS)       │
   └─────────────────┬───────────────────────────────┘
                     │
                     ▼
   ┌─────────────────────────────────────────────────┐
   │  LEARN AGENT                                      │
   │  Input:  Workflow results + user feedback          │
   │  Action: Record patterns in knowledge bank         │
   │          Update authoritative source rules         │
   │  Output: Improved future detection                 │
   │  Needs:  No external access (internal DB only)     │
   └─────────────────────────────────────────────────┘
```

### What Each Agent Needs From DT

#### Monitor Agent — READ access only

| # | Requirement | Why | Details |
|---|-------------|-----|---------|
| B.1 | **GKPOS Order API — Read** | Fetch order by ID to compare pricing | `GET /orders/{order_id}` — total_amount, line_items, customer |
| B.2 | **SAP ECC Order API — Read** | Fetch same order for tax, payment, inventory | OData or RFC: sales order, billing doc, payment status |
| B.3 | **Hybris Order API — Read** | Fetch e-commerce view of same order | OCC API: `GET /orders/{order_id}` |
| B.4 | **Event trigger (any of these):** | Know WHEN to check an order | Option 1: Webhook from each system on order change |
| | | | Option 2: Polling interval (every N minutes) |
| | | | Option 3: ServiceNow incident triggers reconciliation |

#### Verify Agent — READ access only (same as Monitor)

No additional access needed. Verify re-fetches the same data to confirm discrepancies are real (not stale cache).

#### Execute Agent — WRITE access (human-approved)

| # | Requirement | Why | Details |
|---|-------------|-----|---------|
| B.5 | **GKPOS Order API — Write** | Update order when GKPOS is the target of correction | `PUT /orders/{order_id}` — only when SAP/Hybris is authoritative |
| B.6 | **SAP ECC Order API — Write** | Update sales order, trigger reposting | BAPI or OData write — only when GKPOS is authoritative |
| B.7 | **Hybris Order API — Write** | Sync e-commerce order data | OCC admin API or direct DB update endpoint |

**Important:** Execute Agent never auto-applies. A human reviews the proposed fix in the REX-US UI and clicks "Apply Fix" or "Reject Fix". Every fix is logged in the audit trail.

#### Learn Agent — No external access

Operates entirely on REX-US internal database. Reads workflow results, user feedback from rejected fixes, and updates the knowledge bank.

### Authoritative Source Rules (Already Implemented)

```
┌──────────────────┬────────────────────┬─────────────────────────────┐
│ Data Field        │ Authoritative Src  │ Why                         │
├──────────────────┼────────────────────┼─────────────────────────────┤
│ Prices / Totals   │ GKPOS              │ POS captures actual sale    │
│ Line Items        │ GKPOS              │ POS scans physical items    │
│ Tax Amounts       │ SAP ECC            │ SAP runs tax engine (Vertex)│
│ Payment Status    │ SAP ECC            │ SAP processes FI postings   │
│ Inventory         │ SAP ECC            │ SAP MM is inventory master  │
│ Customer Data     │ GKPOS              │ POS captures at point of sale│
│ Status (pre-ship) │ GKPOS / Hybris     │ Origin system owns status   │
│ Status (post-ship)│ SAP ECC            │ SAP owns fulfillment status │
└──────────────────┴────────────────────┴─────────────────────────────┘
```

When the Execute Agent detects a price mismatch, it knows GKPOS is authoritative for prices, so it generates API calls to update SAP ECC and Hybris to match GKPOS — not the other way around.

---

## Minimum Viable Enterprise Deployment

### Option 1: Ticket Analysis Only (Fastest — ServiceNow + JIRA + Confluence)

```
Need from DT:
  ✅ ServiceNow integration user + REST API read access (A.1, A.3, A.5)
  ✅ ServiceNow webhook configuration (A.2)
  ✅ JIRA read-only API access (A.6, A.7, A.8)
  ✅ Confluence read-only API access (A.9, A.10)

Timeline: Can go live in 1-2 weeks after access granted
```

### Option 2: Read-Only Reconciliation (Monitor + Verify, no auto-fix)

```
Need from DT:
  ✅ Everything from Option 1
  ✅ GKPOS read API (B.1)
  ✅ SAP ECC read API (B.2)
  ✅ Hybris read API (B.3)
  ✅ Some trigger mechanism (B.4)

What you get: Agents detect and report discrepancies, but don't fix them.
             Humans see the report and fix manually.

Timeline: 2-4 weeks after API access
```

### Option 3: Full Pipeline (Monitor + Verify + Execute + Learn)

```
Need from DT:
  ✅ Everything from Option 2
  ✅ Write access to non-authoritative systems (B.5, B.6, B.7)
  ✅ Security review and approval for automated writes

What you get: Full AI-powered detection → verification → human-approved fix → learning loop

Timeline: 4-8 weeks (includes security review for write access)
```

---

## Infrastructure & Compliance (All Options)

| # | Requirement | When Needed |
|---|-------------|-------------|
| C.1 | **VPN or IP Whitelisting** | Before any API access — DT systems are behind firewall |
| C.2 | **SSO / Azure AD Integration** | Before user-facing production (replace hardcoded login) |
| C.3 | **LLM Data Agreement** | Before production — DT legal approves sending order data to OpenAI/Anthropic |
| C.4 | **Data Retention Policy** | Before production — align audit trail retention with DT policy |
| C.5 | **PCI DSS Scope Confirmation** | Before production — confirm REX-US doesn't store card numbers |
| C.6 | **DT-Hosted Database (optional)** | If data residency is required — move from Railway to DT infra |
| C.7 | **Monitoring Integration** | Production readiness — push health metrics to DT Splunk/Datadog |
