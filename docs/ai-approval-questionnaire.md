# REX-US — AI Production Approval Questionnaire

## 1. Tell us a short summary about what you want your AI to do

REX-US is an AI-powered incident intelligence system for Discount Tire's IT support team. It analyzes incoming ServiceNow incidents using vector similarity search (pgvector) and GPT-based playbook generation to:

- **Suggest which Problem record** a new incident should be tagged to (from 300+ active Problems)
- **Generate a focused playbook** with step-by-step resolution guidance grounded in real historical resolutions
- **Surface similar past incidents** so the support engineer can see how the team resolved identical issues before

The system does NOT auto-resolve or auto-tag — it provides AI-assisted suggestions that the support engineer reviews and acts on.

---

## 2. Briefly describe your AI idea or use case. Share a summary of what you hope AI can achieve for your department.

**The Problem:** Discount Tire's Information Center handles thousands of ServiceNow incidents per month across 25+ systems (GK POS, Vision, Hybris, SAP, etc.). When a new incident arrives, the support engineer must:
1. Manually read the incident description
2. Search through 300+ Problem records to find the right one to tag it to
3. Look up past similar incidents to understand how they were resolved
4. Write resolution steps from scratch each time

This is time-consuming, inconsistent, and depends heavily on individual engineer experience. New team members take months to build the tribal knowledge needed to triage effectively.

**What REX-US Does:**
- **Ingests** historical closed incidents with their resolutions, work notes, and problem tags from ServiceNow
- **Embeds** each incident using OpenAI text-embedding-3-small (1536 dimensions) into a PostgreSQL pgvector database with HNSW indexing
- **When a new incident arrives**, the system:
  - Generates an embedding of the new incident
  - Performs hybrid search (vector similarity + keyword trigram matching) to find the 15 most similar historical incidents
  - Scores and ranks Problem suggestions using CMDB family-aware weighting and open/closed problem state prioritization
  - Generates a focused playbook and detailed resolution notes using GPT, grounded exclusively in evidence from similar incidents (no hallucination)
- **Progressive learning**: every analyzed incident gets added to the knowledge base, making the system smarter over time

**Expected Impact:**
- **Reduce triage time** from hours/days per incident to minutes
- **Improve Problem tagging accuracy** — validated with a sample set at 97% pattern accuracy. Once we have production access, we plan to validate against 18,000+ incidents covering the last year of operational data.
- **Accelerate onboarding** — new team members get AI-assisted guidance from day one instead of relying on tribal knowledge
- **Surface patterns** the team didn't tag — in our sample validation, 73% of AI suggestions on untagged incidents were confirmed useful by GPT-5.4 semantic analysis

---

## 3. What is the main goal or challenge you want AI to address? Be as specific as possible, including platforms/services affected.

**Primary Goal:** Reduce mean time to resolution (MTTR) for ServiceNow incidents by providing AI-powered problem identification and resolution guidance.

**Specific Challenge:** When a support engineer receives a new incident (e.g., "Vision POS: Order stuck in BAY OUT status"), they need to:
1. Identify which Problem record it belongs to (out of 300+ active PRBs)
2. Determine the correct resolution path
3. Avoid re-investigating issues that have been solved before

Today this is entirely manual and relies on individual experience.

**Platforms/Services Affected:**
- **ServiceNow** — Incident Management module (read-only API integration for data sync; no write-back in MVP)
- **OpenAI API** — text-embedding-3-small for vector embeddings, GPT for playbook generation
- **PostgreSQL** — with pgvector extension for vector similarity search
- **Systems covered by analysis:** GK POS, Vision (Manual Corrections, Missing Orders, Payments), Hybris, SAP (OMS, Fiori, ECC, CAR), Microsoft Teams, Workday, and 20+ other CMDB CIs

**What AI specifically does:**
- Vector similarity search to find the 15 most similar past incidents (not keyword search — semantic understanding)
- Weighted scoring that accounts for CMDB system families, problem record state (Open vs Cancelled), and similarity confidence
- GPT-based playbook generation that is **grounded in actual resolution evidence** — every recommendation cites real incidents
- A prompt injection protection layer and PII stripping pipeline to prevent sensitive data exposure

**What AI does NOT do:**
- Does NOT auto-resolve incidents
- Does NOT write back to ServiceNow
- Does NOT make decisions — it assists the human engineer
- Does NOT access any system outside of the ServiceNow read-only API and OpenAI API

---

## 4. How do you envision AI impacting your daily work or department? Describe any expected benefits or improvements.

### Problem Identification

- **Today:** Support engineers manually search through 300+ Problem records to find the right one to tag a new incident. This depends on individual experience and can take 10-15 minutes per ticket.
- **With REX-US:** The system instantly suggests the correct Problem record with a confidence score. In sample validation, the system identified the correct issue pattern 97% of the time. Once we have production ServiceNow access, we plan to validate this against 18,000+ incidents from the past year to confirm accuracy at scale.

### Resolution Guidance

- **Today:** Engineers either ask colleagues how they resolved a similar issue before, or manually search through old tickets — often re-investigating issues that have been solved multiple times.
- **With REX-US:** The system generates a focused playbook and detailed resolution notes grounded in actual past resolutions. Every recommendation cites specific incidents — no hallucinated or generic advice. The engineer gets step-by-step guidance within seconds of uploading the incident.

### New Engineer Onboarding

- **Today:** It takes new support team members 3-6 months to build the tribal knowledge needed to triage effectively across 25+ systems.
- **With REX-US:** New engineers get AI-assisted guidance from day one. The system acts as institutional memory — surfacing how the team has resolved similar issues before, regardless of whether the new engineer has seen that pattern.

### Knowledge Capture & Retention

- **Today:** Resolution knowledge lives in individual engineers' heads. When experienced staff leave or are unavailable, that knowledge is lost.
- **With REX-US:** Every resolution is systematically captured and searchable. The knowledge base grows with every incident analyzed, building a durable organizational asset that doesn't depend on any individual.

### Pattern Detection on Untagged Incidents

- **Today:** Pattern detection relies on manual observation. Many incidents are resolved but never tagged to a Problem record, making it hard to see recurring patterns.
- **With REX-US:** The system proactively suggests Problem records even for incidents the team didn't tag. In sample validation, 73% of these AI suggestions were confirmed useful through GPT-5.4 semantic analysis, with only 5% being genuinely unrelated. This helps the team identify recurring issues they may have missed.

### Validation Approach

We have validated the system with a representative sample set and achieved strong results:
- **97%** correct issue pattern identification on incidents where we could verify against actual Problem tags
- **73%** useful suggestion rate on incidents where the team hadn't tagged a Problem (validated by GPT-5.4)
- Only **5%** genuinely wrong suggestions
- **Average confidence score of 87%**

As a next step, once we have production ServiceNow access, we plan to validate against 18,000+ incidents covering the last year of operational data. This will confirm that the accuracy holds at production scale and across the full range of incident types.

### How It Fits Into Daily Workflow

1. Support engineer receives a new ServiceNow incident
2. They upload the incident PDF or paste the JSON into REX-US
3. REX-US returns in ~15 seconds:
   - **Problem suggestion** with confidence score
   - **Playbook** (concise action steps)
   - **Resolution notes** (detailed evidence from similar cases)
   - **Similar incidents** (for reference)
4. Engineer reviews the suggestion, applies it, and provides feedback
5. The analyzed incident is added to the knowledge base (progressive learning)

### Data Privacy & Security Measures

**Implemented:**
- PII stripping pipeline (regex-based) removes order numbers, phone numbers, email addresses, store codes, dollar amounts, and timestamps before any text is sent to OpenAI for embedding or playbook generation
- spaCy NER-based name detection used during batch data preparation to strip employee and customer names from the knowledge base
- Prompt injection protection — all user-supplied text is truncated and scanned for injection patterns before entering LLM prompts. Playbook generation is architecturally grounded in evidence, limiting LLM output scope.
- Work notes excluded from all API responses (contains PII — employee names, phone numbers, customer details)
- No customer-facing data exposed — internal tool only, processes IT support incidents
- ServiceNow access is read-only (OAuth 2.0 client credentials). The system never writes back to ServiceNow.
- All secrets (API keys, database credentials, OAuth secrets) stored in environment variables, never in code. Application fails to start if required secrets are missing.
- Security headers enforced on all HTTP responses (X-Content-Type-Options, X-Frame-Options, XSS-Protection, Referrer-Policy, Cache-Control)
- Input validation on all API endpoints — text length limits, numeric bounds, file type/size validation, regex pattern enforcement on incident numbers
- Global exception handler prevents internal error details from reaching the client
- Two rounds of security review completed — all critical and high findings addressed

**Under consideration / yet to be implemented:**
- SSO authentication (AWS IAM Identity Center or Azure AD) — currently relies on network-level access control
- Per-endpoint rate limiting to prevent API abuse (architecture is in place, awaiting production deployment)
- Content Security Policy (CSP) header for additional browser-side protection
- Automated security scanning in CI/CD pipeline

### Future Vision (Post-MVP)

- **Auto-tagging**: Suggest problem tag directly in ServiceNow when incidents are created
- **Predictive analytics**: SLA breach prediction, resolution time estimation
- **Trend detection**: Emerging issue patterns before they become widespread
- **Continuous learning**: Automated feedback loop from engineer corrections

---

*Document prepared: 2026-04-01 | REX-US v7 — Production Candidate*
