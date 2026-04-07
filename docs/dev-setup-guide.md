# REX-US — Developer Setup Guide

Set up REX-US on any machine in 15 minutes.

## Quick Setup (One Command)

```bash
git clone <repo-url> REX-US && cd REX-US && ./setup.sh
```

This interactive script handles prerequisites check, database setup, backend/frontend install, and verification.

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

# OpenAI / Azure OpenAI (for embeddings + playbook generation)
OPENAI_API_KEY=your_openai_api_key
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

2. Apply the schema:

   ```bash
   psql $DATABASE_URL < backend/migrations/002_enriched_schema.sql
   ```

3. Verify:

   ```bash
   psql $DATABASE_URL -c "SELECT COUNT(*) FROM rexus_incidents;"
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

Verify the backend starts:

```bash
backend/.venv/bin/python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
```

You should see `Uvicorn running on http://0.0.0.0:8000`. Press Ctrl+C to stop for now.

---

## Step 5: Set Up the Frontend

```bash
cd frontend
npm install
cd ..
```

---

## Step 6: Import Incidents from ServiceNow

This fetches incidents from your ServiceNow instance, generates embeddings, and loads them into the database. We fetch incidents from **April 2024 onwards** (the latest data with good problem tagging).

### 6a: Fetch incidents

```bash
backend/.venv/bin/python backend/scripts/enrich_incidents.py --split training --batch-size 50
```

This takes ~10 minutes for 10,000-15,000 incidents. Progress is logged to the console.

### 6b: Load into database and generate embeddings

```bash
backend/.venv/bin/python backend/scripts/load_enriched_v3.py data/enriched/enriched_training.json --split training --batch-size 100
```

This takes ~5 minutes for embedding generation (OpenAI API calls).

### 6c: Sync ServiceNow problem states

```bash
backend/.venv/bin/python backend/scripts/sync_problem_states.py
```

### 6d: Verify

```bash
psql $DATABASE_URL -c "
SELECT 'Incidents' as what, COUNT(*) as count FROM rexus_incidents_v3 WHERE embedding IS NOT NULL
UNION ALL
SELECT 'Problems', COUNT(*) FROM rexus_problems
UNION ALL
SELECT 'Open Problems', COUNT(*) FROM rexus_problems WHERE state_display = 'Open';
"
```

Expected output:
```
     what      | count
---------------+-------
 Incidents     | 10000+
 Problems      |   300+
 Open Problems |   200+
```

---

## Step 7: Start the Application

```bash
./dev.sh
```

Or manually:

```bash
# Terminal 1: Backend
backend/.venv/bin/python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000

# Terminal 2: Frontend
cd frontend && npx vite --host
```

Open **http://localhost:5173** in your browser.

---

## Step 8: Verify Everything Works

1. **Dashboard** — should show incident counts and clusters
2. **Analyze** — upload a ServiceNow PDF or paste JSON → get playbook + problem suggestion
3. **SN Sync** — click "Check for New Incidents" to see delta from ServiceNow

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `SERVICENOW_INSTANCE` | Yes | ServiceNow instance URL |
| `SERVICENOW_CLIENT_ID` | Yes | OAuth 2.0 client ID |
| `SERVICENOW_CLIENT_SECRET` | Yes | OAuth 2.0 client secret |
| `OPENAI_API_KEY` | Yes | OpenAI API key for embeddings + playbooks |

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Backend won't start | Check `.env` has correct `DATABASE_URL` |
| Schema fails to apply | Ensure pgvector extension is installed: `CREATE EXTENSION vector;` |
| No incidents after import | Verify ServiceNow credentials in `.env` |
| Embeddings fail | Check `OPENAI_API_KEY` is valid |
| Frontend won't start | Run `cd frontend && npm install` |

---

*REX-US v7 | Last updated: 2026-03-30*
