# REX-US Code Review Fix Summary - Medium & Low Findings

**Date**: 2026-04-07
**Scope**: All Medium and Low findings from steps 06-09

## Fixes Applied

### Critical Path Fix

| ID | Severity | File | Fix |
|---|---|---|---|
| **QUAL-012** | MEDIUM (functionally critical) | `backend/api/routers/sync.py` | Changed all table references from `rexus_incidents_v2` to `rexus_incidents_v3`. Synced incidents are now visible to the analysis engine. This was the most impactful fix -- without it, all imported incidents via /sync/import were invisible to /analyze. |

### Security Fixes

| ID | Severity | File | Fix |
|---|---|---|---|
| **SEC-005** | MEDIUM | `backend/api/main.py` | Added Content-Security-Policy header: `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none';`. Removed deprecated X-XSS-Protection header. |
| **SEC-006** | MEDIUM | `backend/services/servicenow_client.py` | Added HTTPS enforcement: `__init__` now raises ValueError if `instance_url` does not start with `https://`. |
| **SEC-007** | MEDIUM | `backend/api/routers/feedback.py` | Changed `feedback_type` to `Literal["general", "positive", "negative", "suggestion"]` and `input_method` to `Literal["text", "voice"]`. |
| **SEC-008** | MEDIUM | `backend/api/routers/feedback.py` | Fixed MIME check bypass: changed `if file.content_type and ...` to `if not file.content_type or ...` so missing content_type is now rejected. |
| **SEC-009** | MEDIUM | `backend/api/routers/analyze.py` | Added Pydantic `model_validator` on `AnalyzeRequest` to reject `ticket_json` payloads over 100,000 characters. |

### Architecture Fixes

| ID | Severity | File | Fix |
|---|---|---|---|
| **ARCH-007** | MEDIUM | `backend/api/routers/sync.py` | Replaced hardcoded `state=7` with `os.getenv("SN_CLOSED_STATE_CODE", "7")` in both Table API fallback paths. |
| **ARCH-012** | MEDIUM | `backend/api/utils/token_tracker.py` | `estimate_cost()` now logs a warning for unknown models instead of silently using default pricing. |
| **ARCH-018** | LOW | `backend/api/database.py` | Pool sizes now configurable via `DB_POOL_MIN` (default 2) and `DB_POOL_MAX` (default 10) environment variables. |

### Quality Fixes

| ID | Severity | File | Fix |
|---|---|---|---|
| **QUAL-002** | HIGH | `backend/api/utils/text_cleaning.py` (new) | Extracted `clean_for_embedding` into shared utility with `strict` parameter. `analyze.py` uses `strict=False` (placeholders), `sync.py` uses `strict=True` (PII stripping). Both now delegate to the canonical implementation. |
| **QUAL-008** | MEDIUM | `frontend/src/pages/Analyze.tsx` | Removed two artificial `setTimeout(r, 300)` delays in `handleAnalyze`, eliminating 600ms of fake latency. |
| **QUAL-015** | LOW | `backend/services/servicenow_client.py` | Updated type annotations from `Dict`, `List`, `Optional` to modern `dict`, `list`, `X \| None` syntax. |
| **QUAL-016** | LOW | `backend/api/routers/analyze.py` | Changed `not content[:5] == b'%PDF-'` to `not content.startswith(b'%PDF-')`. |
| **QUAL-017** | LOW | `backend/api/utils/token_tracker.py` | Added `asyncpg.Pool` type annotation to `track_usage` `pool` parameter. |
| **QUAL-019** | LOW | `backend/api/utils/llm_provider.py` | Renamed `_LLMResponse` to `LLMResponse` (public API contract, not an implementation detail). Added docstring. |

### Enhanced Review Fixes

| ID | Severity | File | Fix |
|---|---|---|---|
| **ENH-010** | MEDIUM | `frontend/src/pages/Clusters.tsx` | Added `error` and `clusterError` state. Wrapped `load()` and `openCluster()` in try/catch with error display banners. |
| **ENH-012** | MEDIUM | `frontend/src/pages/Analyze.tsx` | Moved all `useState` declarations to the top of the component, before any function definitions. |
| **ENH-013** | MEDIUM | `backend/migrations/004_indexes_and_extensions.sql` (new) | Created migration adding: `pg_trgm` extension, `idx_feedback_incident`, `idx_analysis_log_incident`, and `idx_rexus_incidents_v3_trgm` GIN trigram index. |
| **ENH-014** | MEDIUM | `backend/api/routers/analyze.py` | Added docstring to `AnalyzeResponse` documenting the `similar_incidents` dict shape. |
| **ENH-016** | LOW | `backend/api/routers/incidents.py`, `clusters.py` | Standardized pagination to `max(1, ...)` matching playbooks.py and feedback.py. |
| **ENH-020** | LOW | `frontend/src/pages/SyncPage.tsx` | Changed React key from array index `key={i}` to stable `key={r.incident}`. |

### Additional Fixes (Overlap with ARCH-015/SEC-014)

| ID | Severity | File | Fix |
|---|---|---|---|
| **ARCH-015** / **SEC-014** | LOW | `frontend/src/pages/Analyze.tsx` | Replaced `INC2061899` placeholder/error references with generic `INC0000000`. Default `incNumber` was already empty string. |

## Verification

- All 11 modified Python files pass `ast.parse()` syntax verification
- TypeScript: `npx tsc --noEmit` passes with zero errors
- App import: `from backend.api.main import app` succeeds

## Files Modified

### Backend
- `backend/api/main.py` - CSP header
- `backend/api/database.py` - Configurable pool sizes
- `backend/api/routers/analyze.py` - Shared text_cleaning import, ticket_json size validator, docstrings, startswith fix
- `backend/api/routers/sync.py` - v2 -> v3 table alignment, env-configurable state code, shared text_cleaning
- `backend/api/routers/feedback.py` - Literal types, MIME check fix
- `backend/api/routers/incidents.py` - Pagination standardization
- `backend/api/routers/clusters.py` - Pagination standardization
- `backend/api/utils/token_tracker.py` - Unknown model warning, type annotation
- `backend/api/utils/llm_provider.py` - LLMResponse rename + docstring
- `backend/services/servicenow_client.py` - HTTPS enforcement, modern type hints

### Backend (New Files)
- `backend/api/utils/text_cleaning.py` - Shared text cleaning utility
- `backend/migrations/004_indexes_and_extensions.sql` - Indexes and pg_trgm extension

### Frontend
- `frontend/src/pages/Analyze.tsx` - Removed delays, state ordering, placeholder fix
- `frontend/src/pages/Clusters.tsx` - Error handling for load and openCluster
- `frontend/src/pages/SyncPage.tsx` - React key fix
