# REX-US — Security Controls

This document describes the security measures implemented in REX-US, with implementation details for each control.

---

## 1. PII Protection

REX-US processes ServiceNow incident data that may contain PII — employee names, customer names, phone numbers, email addresses, and order numbers. A multi-layer pipeline ensures PII does not leak to OpenAI or through API responses.

### Layer 1: Regex-based stripping (runtime — every analysis)

**File:** `backend/api/routers/analyze.py` → `clean_for_embedding()`
**File:** `backend/api/routers/sync.py` → `_clean_for_embedding()`

Runs on every incident before text is sent to OpenAI for embedding:

| Pattern | Regex | Replacement |
|---------|-------|-------------|
| Order numbers (10-digit) | `\b\d{10}\b` | `[ORDER]` |
| Store/site codes (AZ 14, TX 03) | `\b[A-Z]{2,3}\s+\d{2}\b` | `[SITE]` |
| Dollar amounts ($1,234.56) | `\$\s*[\d,]+\.?\d*` | `$[AMOUNT]` |
| Incident references | `\bINC\d+\b` | `[INC]` |
| Problem references | `\bPRB\d+\b` | `[PRB]` |
| Phone numbers | `\b\d{3}[-.]?\d{3}[-.]?\d{4}\b` | removed |
| Email addresses | `\b[\w.-]+@[\w.-]+\.\w+\b` | removed |
| Timestamps | `\b\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\b` | removed |

Example:
```
Input:  "John Smith called about order 5033271058 from store AZ 14, phone 480-555-1234"
Output: "called about [ORDER] from store [SITE], phone"
```

### Layer 2: spaCy NER name detection (batch — knowledge base preparation)

**File:** `backend/scripts/load_enriched_v2.py` → `strip_pii()`
**Library:** spaCy `en_core_web_sm` model (English NLP pipeline with named entity recognition)

This runs during batch data preparation when building the knowledge base. It catches names that regex cannot — like "Spoke with Garrett" or "Per Mike Desenberg":

- **spaCy NER:** Runs the `en_core_web_sm` model on incident text, identifies `PERSON` entities, and removes them. Smart enough to skip system names that look like person names (filters out entities containing "POS", "SAP", "GK", "Vision", "Hybris", "IDoc", "ECC").
- **Known names list:** A curated `known_names.json` file containing employee names extracted from the database. Each name is matched and removed via regex.
- **Work note author pattern:** Strips the "2026-03-31 14:30:00 - John Smith (Work notes)" header lines that appear at the start of every work note entry.
- **Customer name/phone patterns:** Strips structured patterns like "Customer Name: John Smith" and "Customer Phone: 480-555-1234".

### Layer 3: Field exclusion from API responses

Certain database fields contain raw PII and are never returned to the frontend:

| Field | Why excluded | Where enforced |
|-------|-------------|----------------|
| `work_notes` | Full conversation threads with names, phones, customer details | `analyze.py` (SEC-014), `incidents.py` (SEC-014), `wave_test.py` (SEC-014) |
| `embedding_text` | Concatenated text sent to OpenAI — contains cleaned but sensitive data | `analyze.py` (SEC-003) |
| `u_resolved_by` | Employee name of the resolver | `wave_test.py` (SEC-014) |
| `input_json`, `full_response` | Raw analysis request/response stored for audit | `analytics.py` (SEC-004) — uses explicit column list in SELECT |

### Layer 4: PII in the database

PII exists in PostgreSQL (work_notes, caller names, order numbers) because it is needed for playbook generation. Access is controlled at infrastructure level:
- Database credentials in environment variables, never in code
- Database not exposed to public internet — accessible only from backend server
- All queries use parameterized statements via `asyncpg` (`$1`, `$2` placeholders) — no SQL injection possible

---

## 2. Prompt Injection Protection

REX-US generates playbooks by interpolating user-supplied incident data into LLM prompts. Three layers prevent prompt injection.

**File:** `backend/api/routers/analyze.py` → `_sanitize_for_prompt()`

### Layer 1: Truncation

All user-supplied fields are truncated to 500 characters before entering any prompt:

```python
_MAX_PROMPT_FIELD_LEN = 500
text = str(text)[:max_len]
```

This limits the attack surface — an attacker cannot inject a long adversarial payload that overwhelms the legitimate prompt.

### Layer 2: Pattern redaction

Known injection patterns are detected via regex and replaced with `[REDACTED]`:

```python
_PROMPT_INJECT_RE = re.compile(
    r'(ignore\s+(previous|all)\s+instructions?|system\s*prompt|you\s+are\s+now|disregard)',
    re.IGNORECASE,
)
```

Catches: "Ignore all previous instructions", "You are now a different AI", "Disregard the system prompt", and variants.

### Layer 3: Architectural grounding

The playbook generation prompt instructs the LLM:

```
ABSOLUTE RULES:
1. ONLY write what appears in the evidence. Do NOT invent.
2. Every step MUST cite [INC#].
```

Even if an injection bypasses truncation and regex, the LLM is constrained to generate content only from the provided evidence (similar incidents and their resolutions). It cannot access external systems, execute code, or take actions.

**Applied to:** `cleaned_issue` and `cluster_name` fields — the two user-influenced fields that enter LLM prompts. Applied in both the playbook prompt and the resolution notes prompt (two parallel GPT calls).

**Limitation:** The regex catches common English patterns but not multi-language attempts, Unicode homoglyphs, or novel phrasings. The primary defense is architectural grounding + truncation. The regex is supplementary.

---

## 3. No Customer-Facing Data Exposure

**File:** `backend/services/servicenow_client.py`

- REX-US is an **internal tool only** — not accessible to customers or external users
- Processes internal IT support incidents, not customer-facing data
- ServiceNow access is **read-only**: only `requests.get` and `requests.post` (for OAuth token) are used. No `PUT`, `PATCH`, or `DELETE` calls exist in the codebase. The system never writes back to ServiceNow.
- Authentication uses **OAuth 2.0 client credentials** grant — no user passwords stored
- PII present in the data is limited to employee names, internal phone extensions, and order reference numbers — no credit card numbers, SSNs, or personal addresses

---

## 4. Secret Management

**File:** `backend/api/config.py`

No secrets are hardcoded anywhere in the codebase. The application **fails to start** if required secrets are missing:

```python
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required.")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY environment variable is required.")
```

| Secret | Storage | Fail-fast |
|--------|---------|-----------|
| `DATABASE_URL` | Environment variable | RuntimeError on startup |
| `OPENAI_API_KEY` | Environment variable | RuntimeError on startup |
| `SERVICENOW_CLIENT_ID` | Environment variable | ValueError when sync is attempted |
| `SERVICENOW_CLIENT_SECRET` | Environment variable | ValueError when sync is attempted |
| `SERVICENOW_INSTANCE` | Environment variable | ValueError when sync is attempted |

- `.env` file excluded from version control (`.gitignore`)
- `.env.example` template provided without actual values
- ServiceNow OAuth tokens logged at `DEBUG` level only (SEC-021) — never in production logs
- `client_secret` is never logged at any level (SEC-012)

---

## 5. Error Information Containment

**File:** `backend/api/main.py`

### Global exception handler

Unhandled exceptions never leak stack traces, file paths, or database error details:

```python
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": "Internal server error"})
```

The actual exception is logged server-side for debugging. The client only sees a generic message.

### Endpoint-level errors

- `400` — invalid input (bad file type, missing fields, constraint violations)
- `404` — resource not found (incidents, analysis logs, wave test entries)
- `422` — Pydantic validation failures (automatic via FastAPI)

Error messages describe what went wrong generically, not internal details.

### API documentation suppression

**In production** (`REXUS_ENV != development`), Swagger UI and ReDoc are disabled:

```python
docs_url="/docs" if is_dev else None,
redoc_url="/redoc" if is_dev else None,
```

Prevents discovery of the full API surface by unauthorized users.

---

## 6. Input Validation

**Libraries:** Pydantic v2 (`BaseModel`, `Field`), FastAPI query parameter validation

### Request body constraints

| Endpoint | Field | Constraint | Library |
|----------|-------|-----------|---------|
| `POST /analyze` | `limit` | 1–50 | Pydantic `Field(ge=1, le=50)` |
| `POST /analyze` | `threshold` | 0.0–1.0 | Pydantic `Field(ge=0.0, le=1.0)` |
| `POST /analyze/text` | `text` | 3–5,000 chars | Pydantic `Field(min_length=3, max_length=5000)` |
| `POST /feedback` | `feedback_text` | 1–5,000 chars | Pydantic `Field(max_length=5000)` |
| `POST /feedback` | `rating` | 1–5 | Pydantic `Field(ge=1, le=5)` |
| `POST /sync/import` | `incident_numbers` | Max 50 items, each matching `^INC\d+$`, max 20 chars | Pydantic `Field(max_length=50)` + `Annotated[str, Field(pattern=...)]` |

### File upload validation

| Upload | Check | Detail |
|--------|-------|--------|
| PDF (`/parse-pdf`) | Extension | Must end in `.pdf` |
| PDF | MIME type | Must be `application/pdf` |
| PDF | Size | Min 100 bytes, max 10 MB |
| PDF | Magic bytes | First 5 bytes must be `%PDF-` |
| Audio (`/transcribe`) | MIME type | Whitelist: `audio/webm`, `audio/wav`, `audio/mp3`, `audio/mpeg`, `audio/ogg`, `audio/mp4` |
| Audio | Size | Min 100 bytes, max 25 MB |

### Query parameter validation

| Parameter | Constraint | Where |
|-----------|-----------|-------|
| `page` | >= 1 | All list endpoints |
| `page_size` | 1–100 | All list endpoints |
| `wave` identifier | Must match `^wave_[a-zA-Z0-9_]{1,40}$` | Wave test endpoints (ARCH-012) |
| `sort_by` | `Literal["incident_count", "avg_resolution_hours", "cluster_name"]` | Clusters endpoint |

### Sync controls

- `SYNC_DELTA_MAX` environment variable (default 2000) caps incidents fetched per delta check
- All ServiceNow HTTP requests have a 30-second timeout (configurable via `SERVICENOW_TIMEOUT_S`)

---

## 7. Security Headers

**File:** `backend/api/main.py` → `add_security_headers` middleware

Every HTTP response includes:

| Header | Value | Purpose |
|--------|-------|---------|
| `X-Content-Type-Options` | `nosniff` | Prevents MIME-type sniffing |
| `X-Frame-Options` | `DENY` | Prevents clickjacking via iframe |
| `X-XSS-Protection` | `1; mode=block` | Enables browser XSS filter |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Controls referrer leakage |
| `Cache-Control` | `no-store` | Prevents caching of sensitive data |

### CORS

- **No wildcard origins** — only explicitly configured frontend URLs
- Only `GET` and `POST` methods permitted
- Only `Content-Type` and `Authorization` headers allowed
- Configurable via `CORS_ORIGINS` environment variable

---

## 8. Authentication (Production Roadmap)

**Status: Not yet implemented — under consideration**

- **MVP (current):** Relies on network-level access control — server accessible only within corporate network
- **Production plan:** SSO integration (AWS IAM Identity Center or Azure AD) using Bearer token authentication via FastAPI dependency
- **Priority:** Write-capable endpoints (`/sync/import`, `/playbooks/generate`, `/feedback`) will be gated first

---

## Security Review History

Two rounds of comprehensive security review covering OWASP Top 10, input validation, authentication, secret management, PII exposure, and prompt injection:

- **Round 1:** 69 findings identified and addressed
- **Round 2:** 52 findings identified, all critical and high items addressed

All security controls in this document have been verified against the current codebase (61 automated checks, 61 passing).

---

*Document version: 1.1 | 2026-04-03 | REX-US v7*
