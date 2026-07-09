# Code Review — PR #12: New Incident Implementation

**Branch:** `feature/New_Incident_Implementation` → `main`  
**Commits reviewed:** `256ba31..4f799ba`  
**Review effort:** High (8 finder angles × 6 candidates → adversarial verify per finding)  
**Date:** 2026-07-09  

---

## Summary

PR #12 splits the monolithic `backend/api/routers/sync.py` into a proper package, adds daily new-incident and closed-incident sync schedulers, introduces APScheduler coordination, and refactors inline Pydantic models into a dedicated `models/` layer.

**8 confirmed/plausible findings, 1 refuted.** The most severe issues are in the new scheduler paths: ServiceNow comments are posted to incidents whose DB records were never written, a single API error silently aborts entire sync batches with no status update, and the connection-pool design can deadlock at small pool sizes. There is also a pre-existing LLM prompt bug in a file the PR touched.

---

## Findings

### F1 — CONFIRMED · HIGH · `new_incident.py:253`

**ServiceNow comments posted when upsert fails — comment repeats on every subsequent sync**

`_analyze_and_comment` is passed `payloads` (all fetched API responses) instead of `incidents` (the successfully enriched subset). When `batch_upsert_snapshots` raises an exception the caller catches it and continues:

```python
# new_incident.py lines 241-254
try:
    inserted, updated = await batch_upsert_snapshots(conn, incidents, sync_date)
    errors = 0
except Exception as e:
    inserted = updated = 0
    errors = len(incidents)          # caught — execution falls through

# No early return here
comments_posted, comments_failed = await _analyze_and_comment(
    request or SimpleNamespace(),
    sn_client,
    payloads,                        # ← all payloads, not just upserted incidents
    pool=pool,
)
```

Inside `_analyze_and_comment`, for each incident with a valid number:

1. REXUS analysis runs and a comment is posted to ServiceNow.
2. `_mark_incident_analyzed(pool, inc_num)` fires `UPDATE rexus_incidents_new SET is_analyzed = TRUE WHERE incident_number = $1`.
3. If the row was never inserted (upsert failed), the UPDATE affects **0 rows** silently.
4. On every future sync run `is_analyzed` is still `FALSE`, so the incident is fetched again, potentially fails upsert again, and receives **another duplicate comment**.

**Fix:** Guard `_analyze_and_comment` with `if errors == 0:`, or pass only successfully upserted incident numbers rather than the raw `payloads` list.

---

### F2 — CONFIRMED · HIGH · `new_incident.py:232`

**Single embedding API error aborts the entire batch with no status update**

The enrichment loop has no per-incident exception handling:

```python
# new_incident.py lines 231-239
incidents: list[dict] = []
for data in payloads:
    row, _, _ = await enrich_incident_row(    # ← no try/except
        pool, conn, data,
        endpoint="/sync/new-incidents/run",
        default_state="New",
    )
    if row:
        incidents.append(row)
```

`enrich_incident_row` calls `embed_text_fn(embedding_text)` without an internal guard. If the embedding API returns a quota error, timeout, or non-2xx for any one incident, the exception propagates uncaught out of the loop. The result:

- `batch_upsert_snapshots` is **never called** (all enriched rows for incidents 1..K-1 are lost).
- `_analyze_and_comment` is **never called**.
- `update_sync_run_status` is **never called** — `rexus_sync_config.last_run_at` and `last_status` remain at the prior run's values. The scheduler dashboard shows no failure.
- The advisory lock is released (via `finally`), so the next scheduled run will attempt the same batch.

**Fix:** Wrap each `enrich_incident_row` call in a try/except; collect failures separately; always call `update_sync_run_status` before returning.

---

### F3 — CONFIRMED · HIGH · `sync.py:410` + `new_incident.py:160`

**Pool connection held idle for entire sync duration; nested acquires risk deadlock**

`run_new_incident_sync` holds a single connection for the complete body of `_run_new_incident_sync_body`:

```python
# new_incident.py lines 160-180
async with pool.acquire() as conn:       # conn checked out
    ...
    try:
        return await _run_new_incident_sync_body(pool, conn, ...)
    finally:
        await conn.execute("SELECT pg_advisory_unlock($1)", ADVISORY_LOCK_ID)
# conn released only here — after the full sync
```

The connection sits **idle** (no DB activity) during:

- `fetch_incidents_detailed()` — up to 8 concurrent ServiceNow HTTP calls (5–60 s)
- Each `embed_text_fn()` call inside the enrichment loop (~0.5 s × N)
- Each `analyze_ticket.__wrapped__()` call in `_analyze_and_comment` (~3–10 s × N LLM calls)
- Each `sn_client.add_incident_comment()` call (~1–3 s × N)

**Nested acquisition chain while `conn` is held:**

| Call | Connections in use |
|---|---|
| Outer `conn` | 1 |
| `track_usage(pool)` inside `enrich_incident_row` | +1 = 2 |
| `analyze_ticket.__wrapped__` → `pool.acquire()` (analyze.py:688) | +1 = 3 |
| `_generate_focused_playbook` → `pool.acquire()` (analyze.py:419) | +1 = 4 |
| `_mark_incident_analyzed(pool)` | +1 = 5 |

Pool defaults: `DB_POOL_MIN=2, DB_POOL_MAX=10`. At `pool_max ≤ 5` the pool exhausts during analysis and any concurrent `pool.acquire()` (e.g. a user hitting `/analyze`) blocks until the 10-second acquire timeout fires. At `pool_max ≤ 2` this is a **guaranteed deadlock**.

The same pattern applies to `closed_incident.py` (line 85).

**Fix:** Narrow `pool.acquire()` to only the DB-write operations. Use a separate short-lived connection for the advisory lock. Release `conn` before the HTTP/LLM phases.

---

### F4 — CONFIRMED · MEDIUM-HIGH · `sync.py:432`

**`batch_upsert_snapshots` has no transaction — partial commit with wrong counters**

```python
# sync.py lines 432-441
async def batch_upsert_snapshots(conn, incidents, sync_date) -> tuple[int, int]:
    inserted = updated = 0
    for row in incidents:
        if await upsert_incident_snapshot(conn, row, sync_date):   # individual auto-commit
            inserted += 1
        else:
            updated += 1
    return inserted, updated
```

Each `upsert_incident_snapshot` commits independently (no `async with conn.transaction()`). If the call raises on row K:

- Rows 0..K-1 are **permanently committed** in the database.
- The exception propagates to the caller, which sets `inserted=0, updated=0, errors=len(incidents)` — wrong counters for the rows that succeeded.
- `_analyze_and_comment` then runs for all payloads (see F1), posting ServiceNow comments for already-committed rows. On the next retry those rows are upserted again (idempotent) but receive a **second comment**.

**Fix:** Wrap the loop in `async with conn.transaction():` and update counters accordingly, or switch to `executemany` / a single `INSERT ... SELECT FROM unnest(...)`.

---

### F5 — CONFIRMED · MEDIUM · `main.py:86`

**`start_scheduler()` is unguarded — a silently swallowed migration failure bricks app startup**

```python
# main.py lines 78-88
await _run_migrations()          # each file's exception caught, logged as WARNING only
try:
    await _ensure_default_admin()
except Exception as exc:
    logger.info("Skipping admin bootstrap ...")
from backend.api.schedulers.scheduler import start_scheduler, stop_scheduler
await start_scheduler()          # ← no try/except
yield
```

`_run_migrations` wraps each file in its own `try/except` and logs only a `WARNING` on failure. If the migration that creates or seeds `rexus_sync_config` fails silently (concurrent lock, empty file syntax error — see F7), the table is absent. Then:

```
start_scheduler
  → register_incident_sync_job
    → load_job_config
      → SELECT ... FROM rexus_sync_config   # raises asyncpg.UndefinedTableError
```

The unhandled exception prevents `yield` from ever executing. FastAPI marks startup as failed and every incoming request returns **503**. The only diagnostic is a single `WARNING` line buried in migration logs.

**Fix:** Wrap `await start_scheduler()` in a try/except that logs clearly and allows the app to start in a degraded state (scheduler disabled), or ensure migrations always surface failures.

---

### F6 — CONFIRMED · MEDIUM · `analyze.py:377`

**Missing `f` prefix on `system_prompt` — LLM receives literal `{ORG_NAME}` in every playbook call**

```python
# analyze.py line 377 — _build_playbook_prompts()
system_prompt = """You are a technical writer for {ORG_NAME} support engineers.
ABSOLUTE RULES:
...
```

The `f` prefix is absent. Python does not interpolate `{ORG_NAME}`. The LLM receives the literal brace-expression rather than the configured value (default: `"Discount Tire"`).

The sibling prompts in the same function use `f"""` correctly:

```python
# line 323
playbook_prompt = f"""You are writing a CONCISE PLAYBOOK for a {ORG_NAME} support engineer...
# line 353
notes_prompt = f"""Create detailed resolution notes...
# line 596 — different function, same string, correct:
system_prompt = f"""You are a technical writer for {ORG_NAME} support engineers.
```

This bug pre-dates this PR but exists in `analyze.py`, a file the PR modified (removing inline models and blank lines).

**Fix:** Add the `f` prefix: `system_prompt = f"""You are a technical writer for {ORG_NAME} support engineers.`

---

### F7 — PLAUSIBLE · LOW-MEDIUM · `011_fix_kb_mapping_constraint.sql`

**Zero-byte migration file generates misleading "skipped" warning on every restart**

```bash
$ wc -c backend/migrations/011_fix_kb_mapping_constraint.sql
0
```

On every app startup, `_run_migrations` reads the file and calls `await pool.execute("")`. asyncpg raises a `PostgresSyntaxError` which is caught and logged as:

```
WARNING: Migration 011_fix_kb_mapping_constraint.sql skipped (may already be applied)
```

This message is misleading — the migration was never applied, and never will be. The file name implies a constraint was supposed to be added or fixed on `rexus_kb_article_incident_mapping`. The existing `insert_kb_mappings` code (kb_articles.py:719) uses:

```sql
ON CONFLICT (incident_number, knowledge_article_number) DO NOTHING
```

If that unique constraint is genuinely absent from the table, this `INSERT` fails at runtime with `there is no unique or exclusion constraint matching the ON CONFLICT specification`.

There is also a **duplicate prefix** issue: both `011_fix_kb_mapping_constraint.sql` (empty) and `011_rexus_incidents_new.sql` (the real migration) sort under `011_`. The empty one runs first alphabetically, errors, gets swallowed, and the real one follows — adding unnecessary noise on every boot.

**Fix:** Either populate the file with the intended SQL, or delete it and rename any future migration `012_…`.

---

### F8 — CONFIRMED · MEDIUM · `closed_incident.py:151` *(late-arriving finding)*

**`status="success"` stored even when all enrichments failed — masks data loss**

```python
# closed_incident.py lines ~151-157 (run_closed_incident_sync)
status = "success" if summary["failed"] == 0 else "partial"
```

`_upsert_one_incident` returns `("skipped", "missing incident number")` when `enrich_incident_row` returns `None`. The caller increments `summary["skipped"]` and appends to `summary["errors"]` — but **never increments `summary["failed"]`**. So a run where every closed incident payload is missing its incident number (e.g., a malformed batch API response) results in:

```json
{
  "status": "success",
  "imported": 0,
  "updated": 0,
  "failed": 0,
  "skipped": 50,
  "errors": ["unknown: missing incident number", ...]
}
```

An operator monitoring `last_status` in the sync dashboard sees no alert while all incident data for that day was silently dropped.

**Fix:** Increment `summary["failed"]` (not `summary["skipped"]`) when enrichment returns no row, or change the status check to `summary["failed"] == 0 and not summary["errors"]`.

---

## Refuted Findings

| Candidate | Verdict | Reason |
|---|---|---|
| `analyze_ticket.__wrapped__` raises `AttributeError` | **REFUTED** | `functools.wraps` always sets `__wrapped__` — it is a documented, stable stdlib contract. slowapi uses it. |
| `SimpleNamespace()` as `Request` crashes `analyze_ticket` | **REFUTED** | `analyze_ticket`'s body never accesses any attribute of `request`; the parameter exists only for the rate-limiter decorator. |

---

## Finding Index

| # | File | Line | Severity | Verdict |
|---|---|---|---|---|
| F1 | `backend/api/routers/sync/new_incident.py` | 253 | HIGH | CONFIRMED |
| F2 | `backend/api/routers/sync/new_incident.py` | 232 | HIGH | CONFIRMED |
| F3 | `backend/api/routers/sync/sync.py` + `new_incident.py` | 410 / 160 | HIGH | CONFIRMED |
| F4 | `backend/api/routers/sync/sync.py` | 432 | MEDIUM-HIGH | CONFIRMED |
| F5 | `backend/api/main.py` | 86 | MEDIUM | CONFIRMED |
| F6 | `backend/api/routers/analyze.py` | 377 | MEDIUM | CONFIRMED |
| F7 | `backend/migrations/011_fix_kb_mapping_constraint.sql` | 1 | LOW-MEDIUM | PLAUSIBLE |
| F8 | `backend/api/routers/sync/closed_incident.py` | 151 | MEDIUM | CONFIRMED |
