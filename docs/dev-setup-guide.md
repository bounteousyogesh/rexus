# REX-US — Developer Setup Guide

Set up REX-US on any machine in 15 minutes.

## Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 16 with pgvector extension
- Git

---

## Step 1: Clone the Code

```bash
git clone <repo-url> REX-US
cd REX-US
```

---

## Step 2: Configure Credentials

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```properties
# Database — point to your PostgreSQL instance
DATABASE_URL=postgresql://username:password@your-host:5432/rexus

# ServiceNow (get from your admin)
SERVICENOW_INSTANCE=https://your-instance.service-now.com
SERVICENOW_CLIENT_ID=your_client_id
SERVICENOW_CLIENT_SECRET=your_client_secret

# --- LLM Provider Configuration ---
# Local development uses OpenAI directly; AWS production uses Bedrock
LLM_PROVIDER=openai                       # openai (local) or bedrock (AWS)
LLM_CHAT_MODEL=gpt-4o                     # or anthropic.claude-opus-4-6-v1 on Bedrock
LLM_EMBED_MODEL=text-embedding-3-small    # or cohere.embed-v4:0 on Bedrock (both 1536 dims)
OPENAI_API_KEY=your_openai_api_key        # only needed when LLM_PROVIDER=openai

# --- Authentication ---
REXUS_JWT_SECRET=some-random-secret-string  # JWT signing key (any strong random string)
REXUS_ADMIN_PASSWORD=RexUS@2026!            # default admin password (change in production)

# --- SSO / Okta (Optional) ---
# Set SSO_ENABLED=true to show "Sign in with SSO" button on the login page.
# When false (default), only username/password login is available.
SSO_ENABLED=false                            # true to enable SSO, false for password-only login
SSO_CLIENT_ID=                               # Okta OIDC client ID
SSO_ISSUER_URL=                              # Okta issuer URL (e.g. https://yourcompany.oktapreview.com/oauth2/xxxxx)
SSO_AUDIENCE=                                # Okta audience (e.g. "AI Agents")
SSO_DEFAULT_ROLE=analyst                     # role assigned to new users created via SSO
SSO_REDIRECT_URI=http://localhost:5173/auth/callback  # must match Okta app redirect URI
```

---

## Step 3: Set Up the Database

You need a PostgreSQL instance with the pgvector and pg_trgm extensions.

1. Create the database and enable extensions:

   ```sql
   CREATE DATABASE rexus;
   \c rexus
   CREATE EXTENSION IF NOT EXISTS vector;
   CREATE EXTENSION IF NOT EXISTS pg_trgm;
   ```

2. Apply the schema migrations in order:

   ```bash
   psql $DATABASE_URL < backend/migrations/001_rexus_schema.sql
   psql $DATABASE_URL < backend/migrations/002_enriched_schema.sql
   psql $DATABASE_URL < backend/migrations/003_token_usage.sql
   psql $DATABASE_URL < backend/migrations/004_indexes_and_extensions.sql
   psql $DATABASE_URL < backend/migrations/005_auth.sql
   ```

3. Verify:

   ```bash
   psql $DATABASE_URL -c "SELECT COUNT(*) FROM rexus_incidents_v3;"
   ```

   Should return 0 (empty — data will be imported in Step 6).

---

## Step 4: Set Up the Backend

Create a Python virtual environment and install dependencies:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
backend/.venv/bin/pip install psycopg2-binary requests spacy
backend/.venv/bin/python -m spacy download en_core_web_sm
```

Start the backend:

```bash
backend/.venv/bin/python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
```

You should see `Uvicorn running on http://0.0.0.0:8000`.

---

## Step 5: Set Up the Frontend

```bash
cd frontend
npm install
npx vite --host
```

Open **http://localhost:5173** in your browser.

---

## Step 6: Import Incidents from ServiceNow

There are two ways to populate the knowledge base. The recommended approach is using the UI — no scripts needed.

### Option A: Import from the UI (Recommended)

1. Open REX-US in your browser → navigate to the **SN Sync** tab
2. Set your filters (State = Closed, optionally filter by Category or System)
3. Click **Search ServiceNow** — the system queries ServiceNow and shows incidents not yet in your database, grouped by day
4. Click **Import** on any day group to pull those incidents in (fetches full details via DT API, generates embeddings, inserts into database)
5. Repeat for each group, or click **Import All** to import everything

Each import batch processes up to 50 incidents at a time. For each incident, the system:
- Fetches full details from ServiceNow (52 fields + work notes + comments)
- Strips PII from embedding text
- Generates a 1536-dim vector embedding via the configured LLM provider
- Inserts into the knowledge base

For the initial load of ~20,000 incidents, expect 5-6 hours. You can import in stages — start with recent months and work backwards. The system is usable as soon as the first batch is imported.

### Option B: Batch Scripts (Advanced)

If you prefer command-line batch import:

```bash
# Fetch incidents from ServiceNow and save as JSON
backend/.venv/bin/python backend/scripts/enrich_incidents.py --split all

# Load into database and generate embeddings
backend/.venv/bin/python backend/scripts/load_enriched_v3.py data/enriched/enriched_all.json --split training --batch-size 100

# Sync problem states (Open/Closed/Cancelled)
backend/.venv/bin/python backend/scripts/sync_problem_states.py
```

The enrich script uses the DT Detailed API (one incident at a time). For 20,000 incidents this takes ~8 hours. The load script generates embeddings via OpenAI in ~15 minutes.

### Verify

After importing, check the knowledge base:

```bash
psql $DATABASE_URL -c "
SELECT 'Incidents' as what, COUNT(*) as count FROM rexus_incidents_v3 WHERE embedding IS NOT NULL
UNION ALL
SELECT 'Problems', COUNT(*) FROM rexus_problems
UNION ALL
SELECT 'Open Problems', COUNT(*) FROM rexus_problems WHERE state_display = 'Open';
"
```

Or from the UI: the **Dashboard** tab shows incident counts, categories, and system breakdown.

---

## Step 7: First Login

1. Open **http://localhost:5173** in your browser. You will be redirected to the **Login** page.
2. Log in with the default admin credentials:
   - **Username:** `admin`
   - **Password:** value of `REXUS_ADMIN_PASSWORD` from `.env` (default: `RexUS@2026!`)
3. After logging in, navigate to the **Admin** page to:
   - Change the default admin password
   - Create additional users (analyst, viewer roles)

---

## Step 8: Verify Everything Works

1. **Health check** — hit `http://localhost:8000/health/detailed` in your browser. All checks should show `connected`/`ok`:
   - Database (connectivity + pool stats)
   - Knowledge base (incident/cluster/problem counts)
   - LLM provider (live embedding test)
   - ServiceNow (OAuth token test)
   - Token usage (last 24h API calls and cost)
   - Analysis activity (last 24h analyses and avg confidence)
   - Application (version, uptime, rate limits)
2. **Login** — authenticate with admin credentials, verify JWT token is returned
3. **Dashboard** — should show incident counts, categories, top systems, resolution times
4. **Analyze** — enter an INC number (e.g. INC2061899) → click Fetch → click Analyze → get playbook + problem suggestion + similar incidents
5. **Analyze (PDF)** — upload a ServiceNow incident PDF → review extracted JSON → click Analyze
6. **SN Sync** — search for new incidents, import them into the knowledge base
7. **Incidents** — browse and search all incidents in the knowledge base
8. **Search** — free-text semantic search across all incidents
9. **Admin** — create a test user, verify they can log in

### Monitoring Endpoints

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /health` | None | Simple liveness check — use for load balancer health probes |
| `GET /health/detailed` | None (or `REXUS_ADMIN_KEY`) | Full 7-check observability — database, LLM, ServiceNow, pool stats, usage, uptime |
| `GET /api/v1/token-usage?days=30` | Bearer | Token usage dashboard — cost by model, endpoint, daily trend |
| `GET /api/v1/config/llm` | Bearer | Current LLM provider configuration (provider, chat model, embed model) |

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `SERVICENOW_INSTANCE` | Yes | ServiceNow instance URL |
| `SERVICENOW_CLIENT_ID` | Yes | OAuth 2.0 client ID |
| `SERVICENOW_CLIENT_SECRET` | Yes | OAuth 2.0 client secret |
| `LLM_PROVIDER` | Yes | LLM backend: `openai` (local dev) or `bedrock` (AWS production) |
| `LLM_CHAT_MODEL` | Yes | Chat/completion model name (e.g. `gpt-4o`, `anthropic.claude-opus-4-6-v1`) |
| `LLM_EMBED_MODEL` | Yes | Embedding model name (e.g. `text-embedding-3-small`, `cohere.embed-v4:0`) |
| `OPENAI_API_KEY` | When `LLM_PROVIDER=openai` | OpenAI API key for embeddings + playbooks |
| `REXUS_JWT_SECRET` | Yes | Secret key for signing JWT authentication tokens |
| `REXUS_ADMIN_PASSWORD` | No | Default admin password on first run (default: `RexUS@2026!`) |
| `AWS_REGION` | When `LLM_PROVIDER=bedrock` | AWS region for Bedrock API calls |
| `BEDROCK_ROLE_ARN` | When `LLM_PROVIDER=bedrock` | IAM role ARN for Bedrock access (AssumeRole) |
| `REXUS_ORG_NAME` | No | Organization name used in LLM prompts (default: `Discount Tire`) |
| `REXUS_ADMIN_KEY` | No | Optional admin key for `/health/detailed` endpoint |
| `REXUS_ENV` | No | Set to `production` to disable Swagger docs (default: `development`) |
| `CORS_ORIGINS` | No | Comma-separated allowed origins (default: localhost) |
| `RATE_LIMIT_ANALYZE` | No | Rate limit for /analyze endpoints (default: `20/minute`) |
| `RATE_LIMIT_SYNC` | No | Rate limit for /sync/import (default: `5/minute`) |
| `DB_POOL_MIN` | No | Minimum database connection pool size (default: `5`) |
| `DB_POOL_MAX` | No | Maximum database connection pool size (default: `20`) |
| `SERVICENOW_TIMEOUT_S` | No | HTTP timeout for ServiceNow calls (default: `30`) |
| `SERVICENOW_SEARCH_PATH` | No | Path for DT search API (default: `/api/ditci/servicenow/incident/search`) |
| `SN_CLOSED_STATE_CODE` | No | ServiceNow closed state code for incident filtering |
| `SSO_ENABLED` | No | Set to `true` to show "Sign in with SSO" on login page (default: `false`) |
| `SSO_CLIENT_ID` | When SSO enabled | Okta OIDC client ID |
| `SSO_ISSUER_URL` | When SSO enabled | Okta issuer URL (includes authorization server path) |
| `SSO_AUDIENCE` | When SSO enabled | Okta audience value (e.g. `AI Agents`) |
| `SSO_DEFAULT_ROLE` | No | Role assigned to users created via SSO (default: `analyst`) |
| `SSO_REDIRECT_URI` | When SSO enabled | Redirect URI after Okta login (must match Okta app config) |

---

## Login Options

REX-US supports two login methods:

- **Username/Password** (always available) — default admin account `admin` / `RexUS@2026!` created on first startup. Admin can create additional users via the Admin page.
- **SSO via Okta** (when `SSO_ENABLED=true`) — users authenticate through Okta and are auto-created in REX-US on first login with the role set by `SSO_DEFAULT_ROLE`. No password needed for SSO users.

When `SSO_ENABLED=false`, only username/password login is shown. When `true`, both options appear on the login page. This allows you to test locally with password login and switch to SSO when Okta is configured.

---

## Local Development vs AWS Production

The LLM provider abstraction means the same codebase runs locally with OpenAI or in AWS with Bedrock. The key configuration differences:

| Setting | Local Development | AWS Production |
|---------|------------------|----------------|
| `LLM_PROVIDER` | `openai` | `bedrock` |
| `LLM_CHAT_MODEL` | `gpt-4o` | `anthropic.claude-opus-4-6-v1` |
| `LLM_EMBED_MODEL` | `text-embedding-3-small` | `cohere.embed-v4:0` |
| Embedding dimensions | 1536 | 1536 |
| Auth for LLM | `OPENAI_API_KEY` env var | IAM role via `BEDROCK_ROLE_ARN` (boto3 AssumeRole) |
| `REXUS_JWT_SECRET` | Any random string | Strong secret from Secrets Manager |
| `REXUS_ADMIN_PASSWORD` | `RexUS@2026!` (default) | Strong password from Secrets Manager |
| `REXUS_ENV` | `development` (Swagger enabled, PDF upload shown) | `production` (Swagger disabled, PDF upload hidden) |
| `SSO_ENABLED` | `false` (password login only) | `true` (SSO via Okta + password fallback) |

> **Important:** No OpenAI API key is needed in AWS production. All LLM and embedding calls go through Amazon Bedrock using IAM roles. Both embedding models produce 1536-dimensional vectors, so the pgvector index works identically in both environments.

---

## ServiceNow APIs Used

REX-US uses two DT custom APIs (read-only, OAuth 2.0 client credentials):

**1. Incident Search** — discover incidents by filter
```
GET /api/ditci/servicenow/incident/search?incident_state=Closed&category=Software
```

**2. Incident Detail** — fetch full incident with work notes
```
GET /api/ditci/v1/servicenow/incident/{INC_NUMBER}/detailed
```

No Table API access is required.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Backend won't start | Check `.env` has correct `DATABASE_URL`, `LLM_PROVIDER`, and `REXUS_JWT_SECRET` |
| Schema fails to apply | Ensure pgvector extension is installed: `CREATE EXTENSION vector;` |
| No incidents after import | Verify ServiceNow credentials in `.env` |
| Embeddings fail | Check `OPENAI_API_KEY` (if openai) or `BEDROCK_ROLE_ARN` (if bedrock) |
| Frontend won't start | Run `cd frontend && npm install` |
| Login fails | Verify migration 005_auth.sql was applied and `REXUS_JWT_SECRET` is set |
| Sync search returns error | Check `SERVICENOW_SEARCH_PATH` env var matches the API endpoint |
| Import slow | Normal — DT API fetches one incident at a time (~1.5s each) |

---

*REX-US v8 | Last updated: 2026-04-07*
