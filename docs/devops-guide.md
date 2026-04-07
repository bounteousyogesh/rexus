# REX-US — DevOps & Monitoring Guide

## Architecture Overview

```
Browser → ALB (HTTPS/SSO) → App Runner Container → PostgreSQL (RDS + pgvector)
                                    ↓
                              OpenAI API (embeddings + completions)
                                    ↓
                              ServiceNow API (read-only sync)
```

Single container runs both the React frontend (static files) and the FastAPI backend.

---

## Environment Variables

All configuration is via environment variables. The application fails to start if required variables are missing.

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://rexus:pass@host:5432/rexus` |
| `OPENAI_API_KEY` | OpenAI API key for embeddings and completions | `sk-...` |

### Required for ServiceNow Sync

| Variable | Description |
|----------|-------------|
| `SERVICENOW_INSTANCE` | ServiceNow instance URL (e.g., `https://dt.service-now.com`) |
| `SERVICENOW_CLIENT_ID` | OAuth 2.0 client ID |
| `SERVICENOW_CLIENT_SECRET` | OAuth 2.0 client secret |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `REXUS_ENV` | `development` | Set to `production` to disable Swagger docs |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173` | Comma-separated allowed origins |
| `SYNC_DELTA_MAX` | `2000` | Max incidents fetched per delta check |
| `SERVICENOW_TIMEOUT_S` | `30` | HTTP timeout for ServiceNow calls (seconds) |
| `RATE_LIMIT_ANALYZE` | `20/minute` | Rate limit for /analyze endpoints |
| `RATE_LIMIT_SYNC` | `5/minute` | Rate limit for /sync/import |
| `RATE_LIMIT_DEFAULT` | `60/minute` | Default rate limit for all other endpoints |

---

## Database Setup

### PostgreSQL 16 with pgvector

```sql
-- Enable extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Run migrations in order
psql -f backend/migrations/001_rexus_schema.sql
psql -f backend/migrations/002_enriched_schema.sql
psql -f backend/migrations/003_token_usage.sql
```

### Connection Pool

The backend uses `asyncpg` with a connection pool:
- `min_size=2, max_size=10` (hardcoded, configurable in `database.py`)
- `command_timeout=30` seconds
- Double-checked locking with `asyncio.Lock` prevents race conditions on startup

### Database Sizing

| Metric | At 25K incidents | At 100K incidents |
|--------|-----------------|-------------------|
| DB size | ~1.5 GB | ~6 GB |
| Vector index (HNSW) | ~250 MB | ~1 GB |
| Analysis logs | ~5 GB/year | ~20 GB/year |
| Token usage logs | ~100 MB/year | ~400 MB/year |

---

## Deployment

### Container Build

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY frontend/dist/ ./static/
CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Health Check

```
GET /health
Response: {"status": "healthy", "database": "connected", "incidents_count": 16892}
```

Use this for ALB health checks and container readiness probes. No authentication required.

### Startup Sequence

1. Application loads environment variables from `.env` or injected env
2. FastAPI app initializes, registers all routers
3. On first request, `get_pool()` creates the asyncpg connection pool (with lock to prevent races)
4. Subsequent requests use the pool

### Graceful Shutdown

The `lifespan` context manager in `main.py` calls `close_pool()` on shutdown, cleanly closing all database connections.

---

## Monitoring

### Token Usage Dashboard

**Endpoint:** `GET /api/v1/token-usage?days=30`

Returns:
- Total calls, tokens, and estimated cost for the period
- Breakdown by model (which model is costing the most)
- Breakdown by endpoint (which feature uses the most tokens)
- Daily trend (calls and cost per day)

Example response:
```json
{
  "period_days": 30,
  "totals": {
    "total_calls": 1250,
    "total_input_tokens": 11750000,
    "total_output_tokens": 3375000,
    "total_tokens": 15125000,
    "total_cost_usd": 62.50
  },
  "by_model": [
    {"model": "gpt-4o", "calls": 500, "input_tokens": 9400000, "output_tokens": 2700000, "cost_usd": 50.50},
    {"model": "text-embedding-3-small", "calls": 750, "input_tokens": 95250, "output_tokens": 0, "cost_usd": 0.002}
  ],
  "by_endpoint": [
    {"endpoint": "/analyze-playbook", "calls": 250, "tokens": 4600000, "cost_usd": 25.00},
    {"endpoint": "/analyze-notes", "calls": 250, "tokens": 7500000, "cost_usd": 25.50}
  ],
  "daily_trend": [
    {"date": "2026-04-01", "calls": 42, "tokens": 504000, "cost_usd": 2.08}
  ]
}
```

### Rate Limiting

Rate limits return HTTP 429 when exceeded:
```
HTTP/1.1 429 Too Many Requests
Retry-After: 60
{"error": "Rate limit exceeded: 20 per 1 minute"}
```

Current limits (configurable via environment variables):
- `/analyze` and `/analyze/text`: 20 requests/minute per IP
- `/sync/import`: 5 requests/minute per IP
- All other endpoints: 60 requests/minute per IP

### Key Metrics to Monitor

| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| API response time (p95) | ALB / CloudWatch | > 30 seconds |
| Error rate (5xx) | ALB access logs | > 1% |
| Database connections in use | RDS metrics | > 8 (out of 10 pool max) |
| Health check failures | `/health` endpoint | Any failure |
| Token cost per day | `/api/v1/token-usage` | > $10/day (adjust based on usage) |
| Rate limit hits (429s) | Application logs | Sustained > 10/hour |
| ServiceNow sync failures | Application logs | Any failure |
| Disk usage (RDS) | RDS metrics | > 80% |

### Log Format

Application logs use Python's standard logging:
```
2026-04-01 10:30:15,123 INFO   Analysis complete: INC2076805 confidence=87% matches=12
2026-04-01 10:30:15,456 INFO   Sync import complete — imported=45, skipped=3, failed=2
```

Log levels:
- `INFO`: Normal operations (analysis results, sync progress)
- `WARNING`: Non-critical issues (progressive learning failures, partial sync errors)
- `ERROR`: Failures that need attention (database errors, OpenAI API failures)
- `DEBUG`: Verbose debugging (OAuth token acquisition, detailed query results)

In production, set log level to `INFO`. Set to `DEBUG` only for troubleshooting.

---

## Operational Procedures

### Weekly: Sync New Incidents

Via the UI (SN Sync tab) or API:
```bash
# Check for new incidents
curl https://rexus.discounttire.com/api/v1/sync/delta

# Import a batch (max 50 per call)
curl -X POST https://rexus.discounttire.com/api/v1/sync/import \
  -H "Content-Type: application/json" \
  -d '{"incident_numbers": ["INC2077001", "INC2077002", ...]}'
```

### Monthly: Review Token Usage

```bash
# Get last 30 days of token usage
curl https://rexus.discounttire.com/api/v1/token-usage?days=30
```

Check:
- Is cost within budget?
- Are any endpoints using unexpected amounts?
- Is daily trend stable or growing?

### Quarterly: Database Maintenance

```sql
-- Check table sizes
SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC;

-- Check HNSW index health
SELECT indexrelname, pg_size_pretty(pg_relation_size(indexrelid))
FROM pg_stat_user_indexes WHERE indexrelname LIKE '%hnsw%';

-- Vacuum analyze (if not automated by RDS)
VACUUM ANALYZE rexus_incidents_v3;
VACUUM ANALYZE rexus_analysis_log;
VACUUM ANALYZE rexus_token_usage;
```

### Incident Response: OpenAI API Down

If OpenAI is unreachable:
- `/analyze` will return 500 errors (embedding and playbook generation both fail)
- `/sync/import` will fail on embedding step
- `/search` will fail on embedding step
- **All read-only endpoints** (`/incidents`, `/clusters`, `/analytics`, `/health`) continue working — they don't use OpenAI

The 30-second timeout on all OpenAI calls prevents indefinite hangs.

### Incident Response: ServiceNow API Down

If ServiceNow is unreachable:
- `/sync/status` will return an error message in the ServiceNow section but still show database stats
- `/sync/delta` and `/sync/import` will fail
- **All analysis and read endpoints continue working** — they use the local database, not ServiceNow

The 30-second timeout on ServiceNow calls (configurable via `SERVICENOW_TIMEOUT_S`) prevents blocking.

---

## Backup & Recovery

### What to Back Up

| Data | Method | Frequency |
|------|--------|-----------|
| PostgreSQL database | RDS automated snapshots | Daily |
| `.env` file (secrets) | AWS Secrets Manager | On change |
| Application code | Git repository | On deploy |

### Recovery

1. Restore RDS from snapshot
2. Deploy application container
3. Configure environment variables
4. Verify health check passes
5. Run a test analysis to confirm OpenAI connectivity

The knowledge base (embeddings) is stored in PostgreSQL. If the database is restored, no re-embedding is needed.

---

*REX-US v7 | DevOps Guide v1.0*
