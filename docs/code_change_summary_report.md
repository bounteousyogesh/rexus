# Code Change Summary Report

Generated: 2026-05-11 18:56:50

Compared folders:
- Source baseline: `rexus-main_dev`
- Target variant: `rexus_dt`
- Excluded from report: `.git`, `.artifacts`, generated summary files

## How to Read This Report

- `Added Files`: files that exist only in `rexus_dt`.
- `Modified Files`: each hunk shows the exact old/new line range plus a `Before` and `After` code block.
- `Before` is the snippet from `rexus-main_dev`; `After` is the matching snippet from `rexus_dt`.

## Overview

- Added files in `rexus_dt`: 21
- Deleted files from `rexus-main_dev`: 0
- Modified files: 18
- Binary-only changed files: 0

## Modified Changes by Folder

### Root

- `.gitignore`

### backend

- `backend/requirements.txt`

### backend/api

- `backend/api/config.py`
- `backend/api/main.py`

### backend/api/routers

- `backend/api/routers/analyze.py`
- `backend/api/routers/search.py`
- `backend/api/routers/sync.py`

### backend/api/utils

- `backend/api/utils/llm_provider.py`
- `backend/api/utils/token_tracker.py`

### backend/migrations

- `backend/migrations/006_create_v3_table.sql`

### frontend

- `frontend/package-lock.json`

### frontend/src

- `frontend/src/api.ts`
- `frontend/src/App.tsx`

### frontend/src/contexts

- `frontend/src/contexts/AuthContext.tsx`

### frontend/src/pages

- `frontend/src/pages/Analyze.tsx`
- `frontend/src/pages/AuthCallback.tsx`
- `frontend/src/pages/Incidents.tsx`
- `frontend/src/pages/Login.tsx`

## Added Files

- `rexus_dt/.env`
- `rexus_dt/backend/.dockerignore`
- `rexus_dt/backend/.env`
- `rexus_dt/backend/Dockerfile`
- `rexus_dt/backend/migrations/007_fix_find_similar_v3.sql`
- `rexus_dt/backend/scripts/apply_fix_find_similar.py`
- `rexus_dt/backend/start.sh`
- `rexus_dt/bitbucket-pipelines.yml`
- `rexus_dt/docs/01_RESEARCH_ANALYSIS.md`
- `rexus_dt/docs/02_ARCHITECTURE_DECISIONS.md`
- `rexus_dt/docs/03_DT_ACCESS_REQUIREMENTS.md`
- `rexus_dt/docs/04_TECHNOLOGY_STACK.md`
- `rexus_dt/docs/05_IMPLEMENTATION_ROADMAP.md`
- `rexus_dt/docs/ai-approval-questionnaire.md`
- `rexus_dt/docs/api-enhancement-request-2.md`
- `rexus_dt/docs/cto-update-followup.md`
- `rexus_dt/docs/data-gaps-recommendations.md`
- `rexus_dt/docs/servicenow-api-access.md`
- `rexus_dt/docs/servicenow-api-enhancement-request.md`
- `rexus_dt/frontend/.dockerignore`
- `rexus_dt/frontend/Dockerfile`

## Modified Files

### `rexus-main_dev/.gitignore` -> `rexus_dt/.gitignore`

- Hunk count: 1

#### Hunk 1 — Old lines 1-5 -> New lines 1-5
- Removed summary: .env
- Added summary: [blank line]

**Before**

```text
# Environment & secrets
.env
*.env.local

# Python
```

**After**

```text
# Environment & secrets

*.env.local

# Python
```

### `rexus-main_dev/backend/api/config.py` -> `rexus_dt/backend/api/config.py`

- Hunk count: 2

#### Hunk 1 — Old lines 1-4 -> New lines 1-6
- Added summary: import warnings | [blank line]

**Before**

```python
import os
from pathlib import Path

from dotenv import load_dotenv
```

**After**

```python
import os
import warnings

from pathlib import Path

from dotenv import load_dotenv
```

#### Hunk 2 — Old lines 15-21 -> New lines 17-23
- Removed summary:     raise RuntimeError("OPENAI_API_KEY environment variable is required when LLM_PROVIDER=openai.")
- Added summary:     warnings.warn("OPENAI_API_KEY is not set. LLM features will not work.", stacklevel=2)

**Before**

```python
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
if LLM_PROVIDER == "openai" and not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY environment variable is required when LLM_PROVIDER=openai.")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")  # Optional; required when Claude integration is enabled

```

**After**

```python
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
if LLM_PROVIDER == "openai" and not OPENAI_API_KEY:
    warnings.warn("OPENAI_API_KEY is not set. LLM features will not work.", stacklevel=2)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")  # Optional; required when Claude integration is enabled

```

### `rexus-main_dev/backend/api/main.py` -> `rexus_dt/backend/api/main.py`

- Hunk count: 2

#### Hunk 1 — Old lines 11-16 -> New lines 11-17
- Added summary: from fastapi.exceptions import RequestValidationError

**Before**

```python
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
```

**After**

```python
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
```

#### Hunk 2 — Old lines 130-135 -> New lines 131-143
- Added summary: # DIAG-001: Log full Pydantic validation errors so 422s are debuggable in CloudWatch | @app.exception_handler(RequestValidationError)

**Before**

```python
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


# ARCH-013: Rate limiting via slowapi — protects expensive endpoints from abuse.
# Configurable via environment variables.
_RATE_ANALYZE = os.getenv("RATE_LIMIT_ANALYZE", "20/minute")
```

**After**

```python
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


# DIAG-001: Log full Pydantic validation errors so 422s are debuggable in CloudWatch
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning("422 Validation error on %s %s: %s", request.method, request.url, exc.errors())
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


# ARCH-013: Rate limiting via slowapi — protects expensive endpoints from abuse.
# Configurable via environment variables.
_RATE_ANALYZE = os.getenv("RATE_LIMIT_ANALYZE", "20/minute")
```

### `rexus-main_dev/backend/api/routers/analyze.py` -> `rexus_dt/backend/api/routers/analyze.py`

- Hunk count: 3

#### Hunk 1 — Old lines 584-590 -> New lines 584-590
- Removed summary:                  AND split_group IN ('training', 'analyzed', 'synced')
- Added summary:                  AND split_group IN ('training',  'analyzed', 'synced')

**Before**

```python
                      NULL::int as cluster_id
               FROM rexus_incidents_v3
               WHERE embedding IS NOT NULL
                 AND split_group IN ('training', 'analyzed', 'synced')
                 AND 1 - (embedding <=> $1::vector) >= $2
               ORDER BY embedding <=> $1::vector
               LIMIT $3""",
```

**After**

```python
                      NULL::int as cluster_id
               FROM rexus_incidents_v3
               WHERE embedding IS NOT NULL
                 AND split_group IN ('training',  'analyzed', 'synced')
                 AND 1 - (embedding <=> $1::vector) >= $2
               ORDER BY embedding <=> $1::vector
               LIMIT $3""",
```

#### Hunk 2 — Old lines 599-605 -> New lines 599-605
- Removed summary:                    WHERE split_group IN ('training', 'analyzed', 'synced')
- Added summary:                    WHERE split_group IN ('training',  'analyzed', 'synced')

**Before**

```python
                          similarity(short_description, $1)::float AS similarity_score,
                          NULL::int as cluster_id
                   FROM rexus_incidents_v3
                   WHERE split_group IN ('training', 'analyzed', 'synced')
                     AND short_description % $1
                   ORDER BY similarity(short_description, $1) DESC
                   LIMIT $2""",
```

**After**

```python
                          similarity(short_description, $1)::float AS similarity_score,
                          NULL::int as cluster_id
                   FROM rexus_incidents_v3
                   WHERE split_group IN ('training',  'analyzed', 'synced')
                     AND short_description % $1
                   ORDER BY similarity(short_description, $1) DESC
                   LIMIT $2""",
```

#### Hunk 3 — Old lines 622-632 -> New lines 622-632
- Removed summary:         # Calculate hybrid score |             m["similarity_score"] = base + bonus
- Added summary:         # Calculate hybrid score — capped at 1.0 so it never exceeds 100% |             m["similarity_score"] = min(base + bonus, 1.0)

**Before**

```python
            else:
                merged[iid] = {**dict(r), "vec": 0.0, "kw": r["similarity_score"]}

        # Calculate hybrid score
        for iid, m in merged.items():
            base = max(m["vec"], m["kw"])
            bonus = min(m["vec"], m["kw"]) * _HYBRID_BONUS_MULTIPLIER if m["vec"] > _HYBRID_VEC_MIN and m["kw"] > _HYBRID_KW_MIN else 0
            m["similarity_score"] = base + bonus

        # Sort by hybrid score and take top N
        similar = sorted(merged.values(), key=lambda x: -x["similarity_score"])[:req.limit]
```

**After**

```python
            else:
                merged[iid] = {**dict(r), "vec": 0.0, "kw": r["similarity_score"]}

        # Calculate hybrid score — capped at 1.0 so it never exceeds 100%
        for iid, m in merged.items():
            base = max(m["vec"], m["kw"])
            bonus = min(m["vec"], m["kw"]) * _HYBRID_BONUS_MULTIPLIER if m["vec"] > _HYBRID_VEC_MIN and m["kw"] > _HYBRID_KW_MIN else 0
            m["similarity_score"] = min(base + bonus, 1.0)

        # Sort by hybrid score and take top N
        similar = sorted(merged.values(), key=lambda x: -x["similarity_score"])[:req.limit]
```

### `rexus-main_dev/backend/api/routers/search.py` -> `rexus_dt/backend/api/routers/search.py`

- Hunk count: 2

#### Hunk 1 — Old lines 13-18 -> New lines 13-20
- Added summary:     # Build the vector literal and cast explicitly — no hardcoded dimension |     # so it works with any embed model (Cohere 1024-dim, OpenAI 1536-dim, etc.)

**Before**

```python
    threshold: float = Query(0.40, ge=0.0, le=1.0),
):
    embedding = await embed_text(q)
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    pool = await get_pool()
```

**After**

```python
    threshold: float = Query(0.40, ge=0.0, le=1.0),
):
    embedding = await embed_text(q)
    # Build the vector literal and cast explicitly — no hardcoded dimension
    # so it works with any embed model (Cohere 1024-dim, OpenAI 1536-dim, etc.)
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    pool = await get_pool()
```

#### Hunk 2 — Old lines 20-26 -> New lines 22-28
- Removed summary:                FROM rexus_find_similar($1::vector, $2, $3, TRUE)""",
- Added summary:                FROM rexus_find_similar($1::vector, $2, $3, FALSE)""",

**Before**

```python
        rows = await conn.fetch(
            """SELECT incident_id, incident_number, short_description,
                      close_notes, similarity_score, cluster_id
               FROM rexus_find_similar($1::vector, $2, $3, TRUE)""",
            embedding_str, threshold, limit,
        )

```

**After**

```python
        rows = await conn.fetch(
            """SELECT incident_id, incident_number, short_description,
                      close_notes, similarity_score, cluster_id
               FROM rexus_find_similar($1::vector, $2, $3, FALSE)""",
            embedding_str, threshold, limit,
        )

```

### `rexus-main_dev/backend/api/routers/sync.py` -> `rexus_dt/backend/api/routers/sync.py`

- Hunk count: 9

#### Hunk 1 — Old lines 15-21 -> New lines 15-21
- Removed summary: from datetime import datetime
- Added summary: from datetime import datetime, date

**Before**

```python
import csv
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated

```

**After**

```python
import csv
import asyncio
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Annotated

```

#### Hunk 2 — Old lines 50-56 -> New lines 50-56
- Removed summary: _CATALOG_PATH = Path(__file__).parent.parent.parent.parent / "data" / "incident_catalog.csv"
- Added summary: _CATALOG_PATH = Path(os.getenv("CATALOG_PATH", "/app/data/incident_catalog.csv"))

**Before**

```python
# before the API is deployed). Falls back to the incident_catalog.csv
# exported from the dev environment.

_CATALOG_PATH = Path(__file__).parent.parent.parent.parent / "data" / "incident_catalog.csv"


def _load_from_catalog(
```

**After**

```python
# before the API is deployed). Falls back to the incident_catalog.csv
# exported from the dev environment.

_CATALOG_PATH = Path(os.getenv("CATALOG_PATH", "/app/data/incident_catalog.csv"))


def _load_from_catalog(
```

#### Hunk 3 — Old lines 188-193 -> New lines 188-219
- Added summary:     def parse_date(v): |         """Parse a date string into a datetime.date object (or None)."""

**Before**

```python
    def parse_bool(v):
        return v in (True, 'true', '1', 1)

    return {
        "number": inc.get("number"),
        "sys_id": inc.get("sys_id"),
```

**After**

```python
    def parse_bool(v):
        return v in (True, 'true', '1', 1)

    def parse_date(v):
        """Parse a date string into a datetime.date object (or None)."""
        if not v:
            return None
        if isinstance(v, date):
            return v
        try:
            return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
        except ValueError:
            logger.warning("Could not parse date %r — storing NULL", v)
            return None

    def parse_ts(v):
        """Parse a ServiceNow timestamp string into a datetime object (or None)."""
        if not v:
            return None
        if isinstance(v, datetime):
            return v
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(str(v)[:19], fmt)
            except ValueError:
                continue
        logger.warning("Could not parse timestamp %r — storing NULL", v)
        return None

    return {
        "number": inc.get("number"),
        "sys_id": inc.get("sys_id"),
```

#### Hunk 4 — Old lines 219-225 -> New lines 245-251
- Removed summary:         "u_order_date": order.get("u_order_date") or None,
- Added summary:         "u_order_date": parse_date(order.get("u_order_date")),

**Before**

```python
        "u_order_number": order.get("u_order_number"),
        "u_total_order_amount": order.get("u_total_order_amount"),
        "u_order_type": order.get("u_order_type"),
        "u_order_date": order.get("u_order_date") or None,
        "u_financial_impact": order.get("u_financial_impact"),
        "u_correction": parse_bool(inc.get("u_correction")),
        "u_correction_type": order.get("u_correction_type"),
```

**After**

```python
        "u_order_number": order.get("u_order_number"),
        "u_total_order_amount": order.get("u_total_order_amount"),
        "u_order_type": order.get("u_order_type"),
        "u_order_date": parse_date(order.get("u_order_date")),
        "u_financial_impact": order.get("u_financial_impact"),
        "u_correction": parse_bool(inc.get("u_correction")),
        "u_correction_type": order.get("u_correction_type"),
```

#### Hunk 5 — Old lines 234-242 -> New lines 260-268
- Removed summary:         "opened_at": inc.get("opened_at"), |         "resolved_at": inc.get("u_resolved_at"),
- Added summary:         "opened_at": parse_ts(inc.get("opened_at")), |         "resolved_at": parse_ts(inc.get("u_resolved_at")),

**Before**

```python
        "escalation": ops.get("escalation_display"),
        "work_notes": wn_text,
        "comments": cm_text,
        "opened_at": inc.get("opened_at"),
        "resolved_at": inc.get("u_resolved_at"),
        "closed_at": inc.get("closed_at"),
    }


```

**After**

```python
        "escalation": ops.get("escalation_display"),
        "work_notes": wn_text,
        "comments": cm_text,
        "opened_at": parse_ts(inc.get("opened_at")),
        "resolved_at": parse_ts(inc.get("u_resolved_at")),
        "closed_at": parse_ts(inc.get("closed_at")),
    }


```

#### Hunk 6 — Old lines 477-482 -> New lines 503-509
- Added summary:             embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

**Before**

```python

            # Use provider-agnostic embed function
            embedding = await _embed_text_fn(embedding_text)

            # Track embedding token usage
            emb_tokens = len(embedding_text) // 4
```

**After**

```python

            # Use provider-agnostic embed function
            embedding = await _embed_text_fn(embedding_text)
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

            # Track embedding token usage
            emb_tokens = len(embedding_text) // 4
```

#### Hunk 7 — Old lines 505-511 -> New lines 532-538
- Removed summary:                         $46::timestamp,$47::timestamp,$48::timestamp,
- Added summary:                         $46,$47,$48,

**Before**

```python
                        $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,
                        $17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31,
                        $32,$33,$34,$35,$36,$37,$38,$39,$40,$41,$42,$43,$44,$45,
                        $46::timestamp,$47::timestamp,$48::timestamp,
                        'synced', $49, $50
                    ) ON CONFLICT (incident_number) DO NOTHING
                """,
```

**After**

```python
                        $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,
                        $17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31,
                        $32,$33,$34,$35,$36,$37,$38,$39,$40,$41,$42,$43,$44,$45,
                        $46,$47,$48,
                        'synced', $49, $50
                    ) ON CONFLICT (incident_number) DO NOTHING
                """,
```

#### Hunk 8 — Old lines 522-528 -> New lines 549-555
- Removed summary:                     embedding_text, embedding,
- Added summary:                     embedding_text, embedding_str,

**Before**

```python
                    flat["reassignment_count"], flat["reopen_count"], flat["made_sla"], flat["escalation"],
                    flat["work_notes"], flat["comments"],
                    flat["opened_at"], flat["resolved_at"], flat["closed_at"],
                    embedding_text, embedding,
                )

            imported += 1
```

**After**

```python
                    flat["reassignment_count"], flat["reopen_count"], flat["made_sla"], flat["escalation"],
                    flat["work_notes"], flat["comments"],
                    flat["opened_at"], flat["resolved_at"], flat["closed_at"],
                    embedding_text, embedding_str,
                )

            imported += 1
```

#### Hunk 9 — Old lines 530-536 -> New lines 557-564
- Removed summary:             results.append({"incident": inc_num, "status": "error", "error": str(e)[:100]})
- Added summary:             logger.error("Failed to import %s: %s", inc_num, e, exc_info=True) |             results.append({"incident": inc_num, "status": "error", "error": str(e)[:500]})

**Before**

```python

        except Exception as e:
            failed += 1
            results.append({"incident": inc_num, "status": "error", "error": str(e)[:100]})

    skipped = total - imported - failed
    logger.info(f"Sync import complete — imported={imported}, skipped={skipped}, failed={failed}")
```

**After**

```python

        except Exception as e:
            failed += 1
            logger.error("Failed to import %s: %s", inc_num, e, exc_info=True)
            results.append({"incident": inc_num, "status": "error", "error": str(e)[:500]})

    skipped = total - imported - failed
    logger.info(f"Sync import complete — imported={imported}, skipped={skipped}, failed={failed}")
```

### `rexus-main_dev/backend/api/utils/llm_provider.py` -> `rexus_dt/backend/api/utils/llm_provider.py`

- Hunk count: 10

#### Hunk 1 — Old lines 20-35 -> New lines 20-67
- Removed summary: LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai") | AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
- Added summary: import warnings | LLM_PROVIDER   = os.getenv("LLM_PROVIDER",   "openai")

**Before**

```python
import json
import logging
import asyncio
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_CHAT_MODEL = os.getenv("LLM_CHAT_MODEL", "gpt-4o")
LLM_EMBED_MODEL = os.getenv("LLM_EMBED_MODEL", "text-embedding-3-small")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")


# ═══════════════════════════════════════════════════════════════════
```

**After**

```python
import json
import logging
import asyncio
import warnings
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────

LLM_PROVIDER   = os.getenv("LLM_PROVIDER",   "openai")
LLM_CHAT_MODEL = os.getenv("LLM_CHAT_MODEL", "gpt-4o")
LLM_EMBED_MODEL = os.getenv("LLM_EMBED_MODEL", "text-embedding-3-small")
AWS_REGION     = os.getenv("AWS_REGION",     "us-west-2")

# Bedrock inference profile ARNs  (used as modelId instead of plain model strings)
BEDROCK_CHAT_MODEL_ID  = os.getenv(
    "BEDROCK_CHAT_MODEL_ID",
    "arn:aws:bedrock:us-west-2:288761730964:application-inference-profile/rax65scdbqk0",
)
BEDROCK_EMBED_MODEL_ID = os.getenv(
    "BEDROCK_EMBED_MODEL_ID",
    "arn:aws:bedrock:us-west-2:288761730964:application-inference-profile/2jjbzso7jmr7",
)

# IAM role to assume before calling Bedrock (leave blank to use the task's own role)
BEDROCK_ROLE_ARN = os.getenv(
    "BEDROCK_ROLE_ARN",
    "arn:aws:iam::288761730964:role/dt-rexus-prd",
)

# Embed request body format: "titan" | "cohere" (default)
# Use "titan" for amazon.titan-embed-* models (body: {"inputText": "..."})
# Use "cohere" for cohere.embed-* models     (body: {"texts": [...], "input_type": "..."})
BEDROCK_EMBED_MODEL_TYPE = os.getenv("BEDROCK_EMBED_MODEL_TYPE", "cohere")

# Expected embedding output dimensions — must match the vector column size in the DB.
# Cohere Embed v3 = 1024, Cohere Embed v4 = 1536, OpenAI text-embedding-3-small = 1536.
# Used only for logging/validation; pgvector accepts dimensionless vectors in queries.
BEDROCK_EMBED_DIMENSIONS = int(os.getenv("BEDROCK_EMBED_DIMENSIONS", "1024"))

# Chat request body format: "anthropic" (default) | "other"
# When using application inference profile ARNs (which contain no model family hint),
# set this to "anthropic" for Claude models (system prompt extracted to top-level param).
BEDROCK_CHAT_MODEL_TYPE = os.getenv("BEDROCK_CHAT_MODEL_TYPE", "anthropic")


# ═══════════════════════════════════════════════════════════════════
```

#### Hunk 2 — Old lines 37-51 -> New lines 69-124
- Removed summary:     """Lazy-init boto3 bedrock-runtime client.""" |     global _boto_client
- Added summary: _boto_client_expiry = None  # datetime when the assumed-role credentials expire |     """Lazy-init boto3 bedrock-runtime client.

**Before**

```python
# ═══════════════════════════════════════════════════════════════════

_boto_client = None


def _get_boto_client():
    """Lazy-init boto3 bedrock-runtime client."""
    global _boto_client
    if _boto_client is None:
        import boto3
        _boto_client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
        logger.info(f"Bedrock client initialized (region={AWS_REGION})")
    return _boto_client


```

**After**

```python
# ═══════════════════════════════════════════════════════════════════

_boto_client = None
_boto_client_expiry = None  # datetime when the assumed-role credentials expire


def _get_boto_client():
    """Lazy-init boto3 bedrock-runtime client.

    If BEDROCK_ROLE_ARN is set the client assumes that IAM role via STS first
    and uses the resulting temporary credentials.  Credentials are refreshed
    automatically 5 minutes before they expire (default session = 1 h).
    """
    global _boto_client, _boto_client_expiry
    import boto3
    from datetime import datetime, timezone, timedelta

    # Refresh if credentials are about to expire (within 5 minutes)
    needs_refresh = (
        _boto_client is None
        or (
            BEDROCK_ROLE_ARN
            and _boto_client_expiry is not None
            and datetime.now(timezone.utc) >= _boto_client_expiry - timedelta(minutes=5)
        )
    )

    if needs_refresh:
        if BEDROCK_ROLE_ARN:
            logger.info("Assuming Bedrock role: %s", BEDROCK_ROLE_ARN)
            sts = boto3.client("sts", region_name=AWS_REGION)
            response = sts.assume_role(
                RoleArn=BEDROCK_ROLE_ARN,
                RoleSessionName="rexus-bedrock-session",
                DurationSeconds=3600,
            )
            creds = response["Credentials"]
            _boto_client_expiry = creds["Expiration"]
            _boto_client = boto3.client(
                "bedrock-runtime",
                region_name=AWS_REGION,
                aws_access_key_id=creds["AccessKeyId"],
                aws_secret_access_key=creds["SecretAccessKey"],
                aws_session_token=creds["SessionToken"],
            )
            logger.info(
                "Bedrock client initialised via assumed role (region=%s, expires=%s)",
                AWS_REGION, _boto_client_expiry.isoformat(),
            )
        else:
            _boto_client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
            logger.info("Bedrock client initialised with task role (region=%s)", AWS_REGION)

    return _boto_client


```

#### Hunk 3 — Old lines 61-67 -> New lines 134-141
- Removed summary:     if model.startswith("anthropic."):
- Added summary:     is_anthropic = "anthropic" in model.lower() or BEDROCK_CHAT_MODEL_TYPE == "anthropic" |     if is_anthropic:

**Before**

```python
        else:
            chat_messages.append({"role": msg["role"], "content": msg["content"]})

    if model.startswith("anthropic."):
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
```

**After**

```python
        else:
            chat_messages.append({"role": msg["role"], "content": msg["content"]})

    is_anthropic = "anthropic" in model.lower() or BEDROCK_CHAT_MODEL_TYPE == "anthropic"
    if is_anthropic:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
```

#### Hunk 4 — Old lines 87-93 -> New lines 161-167
- Removed summary:     if model.startswith("anthropic."):
- Added summary:     if is_anthropic:

**Before**

```python

    result = json.loads(response["body"].read())

    if model.startswith("anthropic."):
        content = result.get("content", [{}])
        text = content[0].get("text", "") if content else ""
        input_tokens = result.get("usage", {}).get("input_tokens", 0)
```

**After**

```python

    result = json.loads(response["body"].read())

    if is_anthropic:
        content = result.get("content", [{}])
        text = content[0].get("text", "") if content else ""
        input_tokens = result.get("usage", {}).get("input_tokens", 0)
```

#### Hunk 5 — Old lines 101-113 -> New lines 175-196
- Removed summary:     """Generate embedding via boto3 invoke_model. Supports Titan and OpenAI models.""" |     if "titan" in model.lower():
- Added summary:     """Generate embedding via boto3 invoke_model. | [blank line]

**Before**

```python


async def _bedrock_embed(model, text):
    """Generate embedding via boto3 invoke_model. Supports Titan and OpenAI models."""
    client = _get_boto_client()

    if "titan" in model.lower():
        body = {"inputText": text}
    else:
        body = {"input": text, "model": model}

    response = await asyncio.to_thread(
        client.invoke_model,
```

**After**

```python


async def _bedrock_embed(model, text):
    """Generate embedding via boto3 invoke_model.

    Body format is determined by BEDROCK_EMBED_MODEL_TYPE (not the model ARN,
    which may be an opaque inference profile and contain no model family hint):
      titan  — {"inputText": "..."}                (amazon.titan-embed-*)
      cohere — {"texts": [...], "input_type": ...}  (cohere.embed-*)
    """
    client = _get_boto_client()

    model_type = BEDROCK_EMBED_MODEL_TYPE.lower()

    if model_type == "cohere":
        body = {"texts": [text], "input_type": "search_document"}
    else:
        # Default: titan
        body = {"inputText": text}

    response = await asyncio.to_thread(
        client.invoke_model,
```

#### Hunk 6 — Old lines 119-129 -> New lines 202-241
- Removed summary:     if "titan" in model.lower(): |         return result.get("embedding", [])
- Added summary:     logger.debug( |         "_bedrock_embed response | model=%s model_type=%s top_keys=%s",

**Before**

```python

    result = json.loads(response["body"].read())

    if "titan" in model.lower():
        return result.get("embedding", [])
    else:
        data = result.get("data", [{}])
        return data[0].get("embedding", []) if data else []


# ═══════════════════════════════════════════════════════════════════
```

**After**

```python

    result = json.loads(response["body"].read())

    logger.debug(
        "_bedrock_embed response | model=%s model_type=%s top_keys=%s",
        model, model_type, list(result.keys()),
    )
    # Cohere Embed v3 returns: {"embeddings": [[float, ...]]}
    if model_type == "cohere":
        # Cohere Embed v3 returns: {"embeddings": [[float, ...]]}
        # Cohere Embed v4 returns: {"embeddings": {"float": [[float, ...]]}}
        embeddings = result.get("embeddings", [])
        logger.debug(
            "_bedrock_embed cohere | embeddings type=%s keys=%s",
            type(embeddings).__name__,
            list(embeddings.keys()) if isinstance(embeddings, dict) else f"list[{len(embeddings)}]",
        )
        if isinstance(embeddings, dict):
            # v4 format
            float_embeddings = embeddings.get("float", [[]])
            logger.debug("_bedrock_embed cohere v4 | float vectors=%d dim=%d",
                         len(float_embeddings),
                         len(float_embeddings[0]) if float_embeddings else 0)
            return float_embeddings[0] if float_embeddings else []
        else:
            # v3 format
            logger.debug("_bedrock_embed cohere v3 | vectors=%d dim=%d",
                         len(embeddings),
                         len(embeddings[0]) if embeddings else 0)
            return embeddings[0] if embeddings else []
    else:
        # titan returns {"embedding": [...], "inputTextTokenCount": N}
        embedding = result.get("embedding", [])
        logger.debug("_bedrock_embed titan | dim=%d tokens=%s",
                     len(embedding),
                     result.get("inputTextTokenCount", "?"))
        return embedding


# ═══════════════════════════════════════════════════════════════════
```

#### Hunk 7 — Old lines 140-146 -> New lines 252-261
- Removed summary:             raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
- Added summary:             logger.warning( |                 "OPENAI_API_KEY is not set — LLM features will not work. "

**Before**

```python
        from openai import AsyncOpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        _openai_client = AsyncOpenAI(api_key=api_key)
        logger.info(f"OpenAI client initialized")
    return _openai_client
```

**After**

```python
        from openai import AsyncOpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning(
                "OPENAI_API_KEY is not set — LLM features will not work. "
                "Set LLM_PROVIDER=bedrock for AWS production deployments."
            )
        _openai_client = AsyncOpenAI(api_key=api_key)
        logger.info(f"OpenAI client initialized")
    return _openai_client
```

#### Hunk 8 — Old lines 226-232 -> New lines 341-347
- Removed summary:         return await _bedrock_embed(LLM_EMBED_MODEL, text)
- Added summary:         return await _bedrock_embed(BEDROCK_EMBED_MODEL_ID, text)

**Before**

```python
async def embed_text(text: str) -> list[float]:
    """Generate embedding for a single text."""
    if LLM_PROVIDER == "bedrock":
        return await _bedrock_embed(LLM_EMBED_MODEL, text)
    return await _openai_embed(LLM_EMBED_MODEL, text)


```

**After**

```python
async def embed_text(text: str) -> list[float]:
    """Generate embedding for a single text."""
    if LLM_PROVIDER == "bedrock":
        return await _bedrock_embed(BEDROCK_EMBED_MODEL_ID, text)
    return await _openai_embed(LLM_EMBED_MODEL, text)


```

#### Hunk 9 — Old lines 239-245 -> New lines 354-360
- Removed summary:         return await _bedrock_chat(LLM_CHAT_MODEL, messages, max_tokens, temperature)
- Added summary:         return await _bedrock_chat(BEDROCK_CHAT_MODEL_ID, messages, max_tokens, temperature)

**Before**

```python
    Works identically for both providers.
    """
    if LLM_PROVIDER == "bedrock":
        return await _bedrock_chat(LLM_CHAT_MODEL, messages, max_tokens, temperature)
    return await _openai_chat(LLM_CHAT_MODEL, messages, max_tokens, temperature)


```

**After**

```python
    Works identically for both providers.
    """
    if LLM_PROVIDER == "bedrock":
        return await _bedrock_chat(BEDROCK_CHAT_MODEL_ID, messages, max_tokens, temperature)
    return await _openai_chat(LLM_CHAT_MODEL, messages, max_tokens, temperature)


```

#### Hunk 10 — Old lines 253-256 -> New lines 368-374
- Added summary:         info["chat_model"] = BEDROCK_CHAT_MODEL_ID |         info["embed_model"] = BEDROCK_EMBED_MODEL_ID

**Before**

```python
    }
    if LLM_PROVIDER == "bedrock":
        info["region"] = AWS_REGION
    return info
```

**After**

```python
    }
    if LLM_PROVIDER == "bedrock":
        info["region"] = AWS_REGION
        info["chat_model"] = BEDROCK_CHAT_MODEL_ID
        info["embed_model"] = BEDROCK_EMBED_MODEL_ID
        info["role_arn"] = BEDROCK_ROLE_ARN or "task-role (no assume)"
    return info
```

### `rexus-main_dev/backend/api/utils/token_tracker.py` -> `rexus_dt/backend/api/utils/token_tracker.py`

- Hunk count: 1

#### Hunk 1 — Old lines 31-42 -> New lines 31-56
- Added summary:     # AWS Bedrock — Cohere Embed v3/v4 (price per 1M tokens) |     "cohere.embed-english-v3": {"input": 0.10, "output": 0.0},

**Before**

```python
    "gpt-5.4-nano": {"input": 0.20, "output": 1.25},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD for a single API call."""
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        logger.warning(
            "Unknown model '%s' — using default pricing ($2.50/$15.00 per 1M tokens). "
```

**After**

```python
    "gpt-5.4-nano": {"input": 0.20, "output": 1.25},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    # AWS Bedrock — Cohere Embed v3/v4 (price per 1M tokens)
    "cohere.embed-english-v3": {"input": 0.10, "output": 0.0},
    "cohere.embed-multilingual-v3": {"input": 0.10, "output": 0.0},
    "cohere.embed-v4:0": {"input": 0.10, "output": 0.0},
    # AWS Bedrock — Anthropic Claude (approximate, varies by version)
    "anthropic.claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "anthropic.claude-3-haiku": {"input": 0.25, "output": 1.25},
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD for a single API call."""
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        # Bedrock inference profile ARNs contain the model family name — do substring match
        model_lower = model.lower()
        for key, p in MODEL_PRICING.items():
            if key in model_lower:
                pricing = p
                break
    if pricing is None:
        logger.warning(
            "Unknown model '%s' — using default pricing ($2.50/$15.00 per 1M tokens). "
```

### `rexus-main_dev/backend/migrations/006_create_v3_table.sql` -> `rexus_dt/backend/migrations/006_create_v3_table.sql`

- Hunk count: 2

#### Hunk 1 — Old lines 1-22 -> New lines 1-11
- Removed summary: CREATE TABLE IF NOT EXISTS rexus_problems ( |     problem_id VARCHAR(50) PRIMARY KEY,
- Added summary: -- Migration 006: Formally create rexus_incidents_v3 | -- Previously this table was only created ad-hoc by load_enriched_v3.py.

**Before**

```sql

CREATE TABLE IF NOT EXISTS rexus_incidents_v3 (LIKE rexus_incidents INCLUDING ALL);

CREATE TABLE IF NOT EXISTS rexus_problems (
    problem_id VARCHAR(50) PRIMARY KEY,
    short_description TEXT,
    state VARCHAR(50),
    state_display VARCHAR(50),
    priority VARCHAR(50),
    opened_at TIMESTAMP,
    closed_at TIMESTAMP,
    last_synced TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Ensure the HNSW vector index exists on v3 (same as rexus_incidents)
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_v3_embedding
ON rexus_incidents_v3 USING hnsw (embedding vector_cosine_ops)
```

**After**

```sql
-- Migration 006: Formally create rexus_incidents_v3
-- Previously this table was only created ad-hoc by load_enriched_v3.py.
-- It is the production table used by /analyze, /sync/import, and /health.
-- This migration ensures it exists on fresh deployments where data is
-- loaded entirely via the UI (sync tab) rather than CLI scripts.

CREATE TABLE IF NOT EXISTS rexus_incidents_v3 (LIKE rexus_incidents INCLUDING ALL);

-- Ensure the HNSW vector index exists on v3 (same as rexus_incidents)
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_v3_embedding
ON rexus_incidents_v3 USING hnsw (embedding vector_cosine_ops)
```

#### Hunk 2 — Old lines 28-30 -> New lines 17-55
- Added summary: [blank line] | -- Fix rexus_find_similar to query rexus_incidents_v3 (production table) instead of

**Before**

```sql
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_v3_opened ON rexus_incidents_v3(opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_v3_category ON rexus_incidents_v3(category);
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_v3_state ON rexus_incidents_v3(state);
```

**After**

```sql
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_v3_opened ON rexus_incidents_v3(opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_v3_category ON rexus_incidents_v3(category);
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_v3_state ON rexus_incidents_v3(state);

-- Fix rexus_find_similar to query rexus_incidents_v3 (production table) instead of
-- rexus_incidents (v1), and drop the hardcoded vector(1536) dimension so that
-- Cohere Embed v3 (1024-dim) vectors are accepted without a cast error.
CREATE OR REPLACE FUNCTION rexus_find_similar(
    query_embedding vector,
    similarity_threshold FLOAT DEFAULT 0.40,
    max_results INTEGER DEFAULT 15,
    training_only BOOLEAN DEFAULT TRUE
)
RETURNS TABLE (
    incident_id INTEGER,
    incident_number VARCHAR(50),
    short_description TEXT,
    close_notes TEXT,
    similarity_score FLOAT,
    cluster_id INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ri.id,
        ri.incident_number,
        ri.short_description,
        ri.close_notes,
        (1 - (ri.embedding <=> query_embedding))::FLOAT AS similarity_score,
        rcm.cluster_id
    FROM rexus_incidents_v3 ri
    LEFT JOIN rexus_cluster_mapping rcm ON ri.id = rcm.incident_id
    WHERE ri.embedding IS NOT NULL
      AND (NOT training_only OR ri.split_group = 'training')
      AND 1 - (ri.embedding <=> query_embedding) >= similarity_threshold
    ORDER BY ri.embedding <=> query_embedding
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql;
```

### `rexus-main_dev/backend/requirements.txt` -> `rexus_dt/backend/requirements.txt`

- Hunk count: 1

#### Hunk 1 — Old lines 18-20 -> New lines 18-21
- Added summary: boto3==1.38.0

**Before**

```text
slowapi==0.1.9
bcrypt==5.0.0
PyJWT==2.12.1
```

**After**

```text
slowapi==0.1.9
bcrypt==5.0.0
PyJWT==2.12.1
boto3==1.38.0
```

### `rexus-main_dev/frontend/package-lock.json` -> `rexus_dt/frontend/package-lock.json`

- Hunk count: 15

#### Hunk 1 — Old lines 63-68 -> New lines 63-69
- Added summary:       "peer": true,

**Before**

```json
      "integrity": "sha512-CGOfOJqWjg2qW/Mb6zNsDm+u5vFQ8DxXfbM09z69p5Z6+mE1ikP2jUXw+j42Pf1XTYED2Rni5f95npYeuwMDQA==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@babel/code-frame": "^7.29.0",
        "@babel/generator": "^7.29.0",
```

**After**

```json
      "integrity": "sha512-CGOfOJqWjg2qW/Mb6zNsDm+u5vFQ8DxXfbM09z69p5Z6+mE1ikP2jUXw+j42Pf1XTYED2Rni5f95npYeuwMDQA==",
      "dev": true,
      "license": "MIT",
      "peer": true,
      "dependencies": {
        "@babel/code-frame": "^7.29.0",
        "@babel/generator": "^7.29.0",
```

#### Hunk 2 — Old lines 1309-1314 -> New lines 1310-1316
- Added summary:       "peer": true,

**Before**

```json
      "integrity": "sha512-GYDxsZi3ChgmckRT9HPU0WEhKLP08ev/Yfcq2AstjrDASOYCSXeyjDsHg4v5t4jOj7cyDX3vmprafKlWIG9MXQ==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "undici-types": "~7.16.0"
      }
```

**After**

```json
      "integrity": "sha512-GYDxsZi3ChgmckRT9HPU0WEhKLP08ev/Yfcq2AstjrDASOYCSXeyjDsHg4v5t4jOj7cyDX3vmprafKlWIG9MXQ==",
      "dev": true,
      "license": "MIT",
      "peer": true,
      "dependencies": {
        "undici-types": "~7.16.0"
      }
```

#### Hunk 3 — Old lines 1318-1323 -> New lines 1320-1326
- Added summary:       "peer": true,

**Before**

```json
      "resolved": "https://registry.npmjs.org/@types/react/-/react-19.2.14.tgz",
      "integrity": "sha512-ilcTH/UniCkMdtexkoCN0bI7pMcJDvmQFPvuPvmEaYA/NSfFTAgdUSLAoVjaRJm7+6PvcM+q1zYOwS4wTYMF9w==",
      "license": "MIT",
      "dependencies": {
        "csstype": "^3.2.2"
      }
```

**After**

```json
      "resolved": "https://registry.npmjs.org/@types/react/-/react-19.2.14.tgz",
      "integrity": "sha512-ilcTH/UniCkMdtexkoCN0bI7pMcJDvmQFPvuPvmEaYA/NSfFTAgdUSLAoVjaRJm7+6PvcM+q1zYOwS4wTYMF9w==",
      "license": "MIT",
      "peer": true,
      "dependencies": {
        "csstype": "^3.2.2"
      }
```

#### Hunk 4 — Old lines 1389-1394 -> New lines 1392-1398
- Added summary:       "peer": true,

**Before**

```json
      "integrity": "sha512-30ScMRHIAD33JJQkgfGW1t8CURZtjc2JpTrq5n2HFhOefbAhb7ucc7xJwdWcrEtqUIYJ73Nybpsggii6GtAHjA==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@typescript-eslint/scope-manager": "8.57.2",
        "@typescript-eslint/types": "8.57.2",
```

**After**

```json
      "integrity": "sha512-30ScMRHIAD33JJQkgfGW1t8CURZtjc2JpTrq5n2HFhOefbAhb7ucc7xJwdWcrEtqUIYJ73Nybpsggii6GtAHjA==",
      "dev": true,
      "license": "MIT",
      "peer": true,
      "dependencies": {
        "@typescript-eslint/scope-manager": "8.57.2",
        "@typescript-eslint/types": "8.57.2",
```

#### Hunk 5 — Old lines 1677-1682 -> New lines 1681-1687
- Added summary:       "peer": true,

**Before**

```json
      "integrity": "sha512-UVJyE9MttOsBQIDKw1skb9nAwQuR5wuGD3+82K6JgJlm/Y+KI92oNsMNGZCYdDsVtRHSak0pcV5Dno5+4jh9sw==",
      "dev": true,
      "license": "MIT",
      "bin": {
        "acorn": "bin/acorn"
      },
```

**After**

```json
      "integrity": "sha512-UVJyE9MttOsBQIDKw1skb9nAwQuR5wuGD3+82K6JgJlm/Y+KI92oNsMNGZCYdDsVtRHSak0pcV5Dno5+4jh9sw==",
      "dev": true,
      "license": "MIT",
      "peer": true,
      "bin": {
        "acorn": "bin/acorn"
      },
```

#### Hunk 6 — Old lines 1795-1800 -> New lines 1800-1806
- Added summary:       "peer": true,

**Before**

```json
        }
      ],
      "license": "MIT",
      "dependencies": {
        "baseline-browser-mapping": "^2.9.0",
        "caniuse-lite": "^1.0.30001759",
```

**After**

```json
        }
      ],
      "license": "MIT",
      "peer": true,
      "dependencies": {
        "baseline-browser-mapping": "^2.9.0",
        "caniuse-lite": "^1.0.30001759",
```

#### Hunk 7 — Old lines 2237-2242 -> New lines 2243-2249
- Added summary:       "peer": true,

**Before**

```json
      "integrity": "sha512-XoMjdBOwe/esVgEvLmNsD3IRHkm7fbKIUGvrleloJXUZgDHig2IPWNniv+GwjyJXzuNqVjlr5+4yVUZjycJwfQ==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@eslint-community/eslint-utils": "^4.8.0",
        "@eslint-community/regexpp": "^4.12.1",
```

**After**

```json
      "integrity": "sha512-XoMjdBOwe/esVgEvLmNsD3IRHkm7fbKIUGvrleloJXUZgDHig2IPWNniv+GwjyJXzuNqVjlr5+4yVUZjycJwfQ==",
      "dev": true,
      "license": "MIT",
      "peer": true,
      "dependencies": {
        "@eslint-community/eslint-utils": "^4.8.0",
        "@eslint-community/regexpp": "^4.12.1",
```

#### Hunk 8 — Old lines 4262-4267 -> New lines 4269-4275
- Added summary:       "peer": true,

**Before**

```json
      "integrity": "sha512-QP88BAKvMam/3NxH6vj2o21R6MjxZUAd6nlwAS/pnGvN9IVLocLHxGYIzFhg6fUQ+5th6P4dv4eW9jX3DSIj7A==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=12"
      },
```

**After**

```json
      "integrity": "sha512-QP88BAKvMam/3NxH6vj2o21R6MjxZUAd6nlwAS/pnGvN9IVLocLHxGYIzFhg6fUQ+5th6P4dv4eW9jX3DSIj7A==",
      "dev": true,
      "license": "MIT",
      "peer": true,
      "engines": {
        "node": ">=12"
      },
```

#### Hunk 9 — Old lines 4333-4338 -> New lines 4341-4347
- Added summary:       "peer": true,

**Before**

```json
      "resolved": "https://registry.npmjs.org/react/-/react-19.2.4.tgz",
      "integrity": "sha512-9nfp2hYpCwOjAN+8TZFGhtWEwgvWHXqESH8qT89AT/lWklpLON22Lc8pEtnpsZz7VmawabSU0gCjnj8aC0euHQ==",
      "license": "MIT",
      "engines": {
        "node": ">=0.10.0"
      }
```

**After**

```json
      "resolved": "https://registry.npmjs.org/react/-/react-19.2.4.tgz",
      "integrity": "sha512-9nfp2hYpCwOjAN+8TZFGhtWEwgvWHXqESH8qT89AT/lWklpLON22Lc8pEtnpsZz7VmawabSU0gCjnj8aC0euHQ==",
      "license": "MIT",
      "peer": true,
      "engines": {
        "node": ">=0.10.0"
      }
```

#### Hunk 10 — Old lines 4342-4347 -> New lines 4351-4357
- Added summary:       "peer": true,

**Before**

```json
      "resolved": "https://registry.npmjs.org/react-dom/-/react-dom-19.2.4.tgz",
      "integrity": "sha512-AXJdLo8kgMbimY95O2aKQqsz2iWi9jMgKJhRBAxECE4IFxfcazB2LmzloIoibJI3C12IlY20+KFaLv+71bUJeQ==",
      "license": "MIT",
      "dependencies": {
        "scheduler": "^0.27.0"
      },
```

**After**

```json
      "resolved": "https://registry.npmjs.org/react-dom/-/react-dom-19.2.4.tgz",
      "integrity": "sha512-AXJdLo8kgMbimY95O2aKQqsz2iWi9jMgKJhRBAxECE4IFxfcazB2LmzloIoibJI3C12IlY20+KFaLv+71bUJeQ==",
      "license": "MIT",
      "peer": true,
      "dependencies": {
        "scheduler": "^0.27.0"
      },
```

#### Hunk 11 — Old lines 4388-4393 -> New lines 4398-4404
- Added summary:       "peer": true,

**Before**

```json
      "resolved": "https://registry.npmjs.org/react-redux/-/react-redux-9.2.0.tgz",
      "integrity": "sha512-ROY9fvHhwOD9ySfrF0wmvu//bKCQ6AeZZq1nJNtbDC+kk5DuSuNX/n6YWYF/SYy7bSba4D4FSz8DJeKY/S/r+g==",
      "license": "MIT",
      "dependencies": {
        "@types/use-sync-external-store": "^0.0.6",
        "use-sync-external-store": "^1.4.0"
```

**After**

```json
      "resolved": "https://registry.npmjs.org/react-redux/-/react-redux-9.2.0.tgz",
      "integrity": "sha512-ROY9fvHhwOD9ySfrF0wmvu//bKCQ6AeZZq1nJNtbDC+kk5DuSuNX/n6YWYF/SYy7bSba4D4FSz8DJeKY/S/r+g==",
      "license": "MIT",
      "peer": true,
      "dependencies": {
        "@types/use-sync-external-store": "^0.0.6",
        "use-sync-external-store": "^1.4.0"
```

#### Hunk 12 — Old lines 4440-4446 -> New lines 4451-4458
- Removed summary:       "license": "MIT"
- Added summary:       "license": "MIT", |       "peer": true

**Before**

```json
      "version": "5.0.1",
      "resolved": "https://registry.npmjs.org/redux/-/redux-5.0.1.tgz",
      "integrity": "sha512-M9/ELqF6fy8FwmkpnF0S3YKOqMyoWJ4+CS5Efg2ct3oY9daQvd/Pc71FpGZsVsbl3Cpb+IIcjBDUnnyBdQbq4w==",
      "license": "MIT"
    },
    "node_modules/redux-thunk": {
      "version": "3.1.0",
```

**After**

```json
      "version": "5.0.1",
      "resolved": "https://registry.npmjs.org/redux/-/redux-5.0.1.tgz",
      "integrity": "sha512-M9/ELqF6fy8FwmkpnF0S3YKOqMyoWJ4+CS5Efg2ct3oY9daQvd/Pc71FpGZsVsbl3Cpb+IIcjBDUnnyBdQbq4w==",
      "license": "MIT",
      "peer": true
    },
    "node_modules/redux-thunk": {
      "version": "3.1.0",
```

#### Hunk 13 — Old lines 4795-4800 -> New lines 4807-4813
- Added summary:       "peer": true,

**Before**

```json
      "integrity": "sha512-jl1vZzPDinLr9eUt3J/t7V6FgNEw9QjvBPdysz9KfQDD41fQrC2Y4vKQdiaUpFT4bXlb1RHhLpp8wtm6M5TgSw==",
      "dev": true,
      "license": "Apache-2.0",
      "bin": {
        "tsc": "bin/tsc",
        "tsserver": "bin/tsserver"
```

**After**

```json
      "integrity": "sha512-jl1vZzPDinLr9eUt3J/t7V6FgNEw9QjvBPdysz9KfQDD41fQrC2Y4vKQdiaUpFT4bXlb1RHhLpp8wtm6M5TgSw==",
      "dev": true,
      "license": "Apache-2.0",
      "peer": true,
      "bin": {
        "tsc": "bin/tsc",
        "tsserver": "bin/tsserver"
```

#### Hunk 14 — Old lines 5027-5032 -> New lines 5040-5046
- Added summary:       "peer": true,

**Before**

```json
      "integrity": "sha512-1gFhNi+bHhRE/qKZOJXACm6tX4bA3Isy9KuKF15AgSRuRazNBOJfdDemPBU16/mpMxApDPrWvZ08DcLPEoRnuA==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "lightningcss": "^1.32.0",
        "picomatch": "^4.0.3",
```

**After**

```json
      "integrity": "sha512-1gFhNi+bHhRE/qKZOJXACm6tX4bA3Isy9KuKF15AgSRuRazNBOJfdDemPBU16/mpMxApDPrWvZ08DcLPEoRnuA==",
      "dev": true,
      "license": "MIT",
      "peer": true,
      "dependencies": {
        "lightningcss": "^1.32.0",
        "picomatch": "^4.0.3",
```

#### Hunk 15 — Old lines 5151-5156 -> New lines 5165-5171
- Added summary:       "peer": true,

**Before**

```json
      "integrity": "sha512-rftlrkhHZOcjDwkGlnUtZZkvaPHCsDATp4pGpuOOMDaTdDDXF91wuVDJoWoPsKX/3YPQ5fHuF3STjcYyKr+Qhg==",
      "dev": true,
      "license": "MIT",
      "funding": {
        "url": "https://github.com/sponsors/colinhacks"
      }
```

**After**

```json
      "integrity": "sha512-rftlrkhHZOcjDwkGlnUtZZkvaPHCsDATp4pGpuOOMDaTdDDXF91wuVDJoWoPsKX/3YPQ5fHuF3STjcYyKr+Qhg==",
      "dev": true,
      "license": "MIT",
      "peer": true,
      "funding": {
        "url": "https://github.com/sponsors/colinhacks"
      }
```

### `rexus-main_dev/frontend/src/api.ts` -> `rexus_dt/frontend/src/api.ts`

- Hunk count: 2

#### Hunk 1 — Old lines 30-36 -> New lines 30-36
- Removed summary: async function put<T>(path: string, body: unknown): Promise<T> {
- Added summary: export async function put<T>(path: string, body: unknown): Promise<T> {

**Before**

```ts
  return res.json();
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
```

**After**

```ts
  return res.json();
}

export async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
```

#### Hunk 2 — Old lines 40-46 -> New lines 40-46
- Removed summary: async function del<T>(path: string): Promise<T> {
- Added summary: export async function del<T>(path: string): Promise<T> {

**Before**

```ts
  return res.json();
}

async function del<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'DELETE',
    headers: { ...authHeaders() },
```

**After**

```ts
  return res.json();
}

export async function del<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'DELETE',
    headers: { ...authHeaders() },
```

### `rexus-main_dev/frontend/src/App.tsx` -> `rexus_dt/frontend/src/App.tsx`

- Hunk count: 2

#### Hunk 1 — Old lines 1-6 -> New lines 1-7
- Removed summary: import { useState } from 'react'; | import { AuthProvider, useAuth } from './contexts/AuthContext';
- Added summary: import { useState, useEffect } from 'react'; | import { AuthProvider, useAuth, LOGGED_OUT_KEY } from './contexts/AuthContext';

**Before**

```tsx
import { useState } from 'react';
import { Search, BarChart3, Layers, Activity, Zap, RefreshCw, Shield, LogOut, KeyRound } from 'lucide-react';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import LoginPage from './pages/Login';
import AuthCallback from './pages/AuthCallback';
import DashboardPage from './pages/Dashboard';
```

**After**

```tsx
import { useState, useEffect } from 'react';
import { Search, BarChart3, Layers, Activity, Zap, RefreshCw, Shield, LogOut, KeyRound } from 'lucide-react';
import { AuthProvider, useAuth, LOGGED_OUT_KEY } from './contexts/AuthContext';
import { authApi, type SSOConfig } from './api';
import LoginPage from './pages/Login';
import AuthCallback from './pages/AuthCallback';
import DashboardPage from './pages/Dashboard';
```

#### Hunk 2 — Old lines 111-125 -> New lines 112-197
- Removed summary:   // Handle SSO callback route before anything else |   if (window.location.pathname === '/auth/callback') {
- Added summary: // ── PKCE Helpers ───────────────────────────────────────────────────────────── | [blank line]

**Before**

```tsx
  );
}

function AppGate() {
  const { isAuthenticated, isLoading } = useAuth();

  // Handle SSO callback route before anything else
  if (window.location.pathname === '/auth/callback') {
    return <AuthCallback />;
  }

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-100">
        <div className="text-slate-500 text-sm">Loading...</div>
```

**After**

```tsx
  );
}

// ── PKCE Helpers ─────────────────────────────────────────────────────────────

function generateCodeVerifier(): string {
  const array = new Uint8Array(32);
  crypto.getRandomValues(array);
  return btoa(String.fromCharCode(...array))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
}

async function generateCodeChallenge(verifier: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(verifier);
  const digest = await crypto.subtle.digest('SHA-256', data);
  return btoa(String.fromCharCode(...new Uint8Array(digest)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
}

async function redirectToSSO(ssoConfig: SSOConfig) {
  const codeVerifier = generateCodeVerifier();
  const codeChallenge = await generateCodeChallenge(codeVerifier);
  const state = crypto.randomUUID();

  sessionStorage.setItem('sso_code_verifier', codeVerifier);
  sessionStorage.setItem('sso_state', state);

  const params = new URLSearchParams({
    client_id: ssoConfig.client_id!,
    response_type: 'code',
    scope: 'openid email profile',
    redirect_uri: ssoConfig.redirect_uri!,
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
    state,
  });

  if (ssoConfig.audience) {
    params.set('audience', ssoConfig.audience);
  }

  window.location.href = `${ssoConfig.authorize_url}?${params.toString()}`;
}

// ── AppGate ───────────────────────────────────────────────────────────────────

function AppGate() {
  const { isAuthenticated, isLoading } = useAuth();
  const [ssoChecked, setSsoChecked] = useState(false);

  const isCallback = window.location.pathname === '/auth/callback';
  const hasSsoError = new URLSearchParams(window.location.search).has('sso_error');
  // After an explicit logout, show the login page instead of auto-redirecting
  const didLogOut = sessionStorage.getItem(LOGGED_OUT_KEY) === '1';

  useEffect(() => {
    if (isCallback || isLoading || isAuthenticated || hasSsoError || didLogOut) {
      setSsoChecked(true);
      return;
    }

    authApi.ssoConfig().then((config) => {
      if (config && config.enabled) {
        redirectToSSO(config); // navigates away — component will unmount
      } else {
        setSsoChecked(true);
      }
    }).catch(() => {
      setSsoChecked(true);
    });
  }, [isCallback, isLoading, isAuthenticated, hasSsoError, didLogOut]);

  // Handle SSO callback route — safe to return after all hooks
  if (isCallback) {
    return <AuthCallback />;
  }

  if (isLoading || (!isAuthenticated && !hasSsoError && !ssoChecked)) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-100">
        <div className="text-slate-500 text-sm">Loading...</div>
```

### `rexus-main_dev/frontend/src/contexts/AuthContext.tsx` -> `rexus_dt/frontend/src/contexts/AuthContext.tsx`

- Hunk count: 6

#### Hunk 1 — Old lines 14-25 -> New lines 14-29
- Added summary:   loginWithToken: (data: LoginResponse) => void; | // Set after an explicit logout so AppGate shows the login page instead of

**Before**

```tsx
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

const TOKEN_KEY = 'rexus_token';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
```

**After**

```tsx
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  loginWithToken: (data: LoginResponse) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

const TOKEN_KEY = 'rexus_token';
// Set after an explicit logout so AppGate shows the login page instead of
// auto-redirecting to SSO again.
export const LOGGED_OUT_KEY = 'rexus_logged_out';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
```

#### Hunk 2 — Old lines 27-35 -> New lines 31-49
- Added summary:   // Internal: clears auth state when a stored token is found to be invalid on |   // page load. Does NOT set LOGGED_OUT_KEY so AppGate still auto-redirects to SSO.

**Before**

```tsx
    () => localStorage.getItem(TOKEN_KEY),
  );
  const [isLoading, setIsLoading] = useState(true);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);
```

**After**

```tsx
    () => localStorage.getItem(TOKEN_KEY),
  );
  const [isLoading, setIsLoading] = useState(true);
  // Internal: clears auth state when a stored token is found to be invalid on
  // page load. Does NOT set LOGGED_OUT_KEY so AppGate still auto-redirects to SSO.
  const clearSession = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);

  // Explicit user sign-out: sets LOGGED_OUT_KEY so AppGate shows the login page
  // with the SSO button instead of silently auto-redirecting to Okta again.
  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    sessionStorage.setItem(LOGGED_OUT_KEY, '1');
    setToken(null);
    setUser(null);
  }, []);
```

#### Hunk 3 — Old lines 51-62 -> New lines 65-77
- Removed summary:       .me() |       .then((u) => {
- Added summary:       .me()      .then((u) => { |         // Token is expired/invalid — clear it silently so AppGate can

**Before**

```tsx
    // Only call me() on initial mount with a stored token (page refresh)
    let cancelled = false;
    authApi
      .me()
      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .catch(() => {
        if (!cancelled) logout();
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
```

**After**

```tsx
    // Only call me() on initial mount with a stored token (page refresh)
    let cancelled = false;
    authApi
      .me()      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .catch(() => {
        // Token is expired/invalid — clear it silently so AppGate can
        // auto-redirect to SSO (do NOT set LOGGED_OUT_KEY here).
        if (!cancelled) clearSession();
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
```

#### Hunk 4 — Old lines 65-71 -> New lines 80-86
- Removed summary:   }, [token, logout]); // eslint-disable-line react-hooks/exhaustive-deps
- Added summary:   }, [token, clearSession]); // eslint-disable-line react-hooks/exhaustive-deps

**Before**

```tsx
    return () => {
      cancelled = true;
    };
  }, [token, logout]); // eslint-disable-line react-hooks/exhaustive-deps

  const login = useCallback(async (username: string, password: string) => {
    const data: LoginResponse = await authApi.login(username, password);
```

**After**

```tsx
    return () => {
      cancelled = true;
    };
  }, [token, clearSession]); // eslint-disable-line react-hooks/exhaustive-deps

  const login = useCallback(async (username: string, password: string) => {
    const data: LoginResponse = await authApi.login(username, password);
```

#### Hunk 5 — Old lines 78-83 -> New lines 93-109
- Added summary:   // Used by AuthCallback after SSO — sets token + user directly, no /me round-trip |   const loginWithToken = useCallback((data: LoginResponse) => {

**Before**

```tsx
    });
  }, []);

  return (
    <AuthContext.Provider
      value={{
```

**After**

```tsx
    });
  }, []);

  // Used by AuthCallback after SSO — sets token + user directly, no /me round-trip
  const loginWithToken = useCallback((data: LoginResponse) => {
    localStorage.setItem(TOKEN_KEY, data.token);
    setToken(data.token);
    setUser({
      id: data.user.id,
      username: data.user.username,
      role: data.user.role,
    });
  }, []);

  return (
    <AuthContext.Provider
      value={{
```

#### Hunk 6 — Old lines 86-91 -> New lines 112-118
- Added summary:         loginWithToken,

**Before**

```tsx
        isAuthenticated: !!user,
        isLoading,
        login,
        logout,
      }}
    >
```

**After**

```tsx
        isAuthenticated: !!user,
        isLoading,
        login,
        loginWithToken,
        logout,
      }}
    >
```

### `rexus-main_dev/frontend/src/pages/Analyze.tsx` -> `rexus_dt/frontend/src/pages/Analyze.tsx`

- Hunk count: 3

#### Hunk 1 — Old lines 27-33 -> New lines 27-33
- Removed summary:   const [isDev, setIsDev] = useState(true);
- Added summary:   const [isDev, setIsDev] = useState(false);

**Before**

```tsx
  const [expandedInc, setExpandedInc] = useState<string | null>(null);
  const [error, setError] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const [isDev, setIsDev] = useState(true);

  // Check environment — hide PDF upload in production
  useEffect(() => {
```

**After**

```tsx
  const [expandedInc, setExpandedInc] = useState<string | null>(null);
  const [error, setError] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const [isDev, setIsDev] = useState(false);

  // Check environment — hide PDF upload in production
  useEffect(() => {
```

#### Hunk 2 — Old lines 225-237 -> New lines 225-236
- Removed summary:             <div className="bg-white rounded-lg p-3 shadow-sm border border-slate-100 flex items-center gap-3"> |               <p className={`text-2xl font-bold ${confidenceColor(result.confidence_score)}`}>
- Added summary:             <div className="bg-white rounded-lg p-3 shadow-sm border border-slate-100 flex items-center gap-3">              <p className={`… |                 {(Math.min(result.confidence_score, 1) * 100).toFixed(0)}%

**Before**

```tsx
          {/* Row 1: Confidence + Cluster + Problem Tag */}
          <div className="grid grid-cols-[auto_1fr_auto] gap-3 items-stretch">
            {/* Confidence */}
            <div className="bg-white rounded-lg p-3 shadow-sm border border-slate-100 flex items-center gap-3">
              <p className={`text-2xl font-bold ${confidenceColor(result.confidence_score)}`}>
                {(result.confidence_score * 100).toFixed(0)}%
              </p>
              <div>
                <div className="w-24 h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div className={`h-2 rounded-full ${confidenceBg(result.confidence_score)}`} style={{ width: `${result.confidence_score * 100}%` }} />
                </div>
                <p className="text-[10px] text-slate-500 mt-0.5">{result.match_count} matches</p>
              </div>
```

**After**

```tsx
          {/* Row 1: Confidence + Cluster + Problem Tag */}
          <div className="grid grid-cols-[auto_1fr_auto] gap-3 items-stretch">
            {/* Confidence */}
            <div className="bg-white rounded-lg p-3 shadow-sm border border-slate-100 flex items-center gap-3">              <p className={`text-2xl font-bold ${confidenceColor(result.confidence_score)}`}>
                {(Math.min(result.confidence_score, 1) * 100).toFixed(0)}%
              </p>
              <div>
                <div className="w-24 h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div className={`h-2 rounded-full ${confidenceBg(result.confidence_score)}`} style={{ width: `${Math.min(result.confidence_score, 1) * 100}%` }} />
                </div>
                <p className="text-[10px] text-slate-500 mt-0.5">{result.match_count} matches</p>
              </div>
```

#### Hunk 3 — Old lines 307-315 -> New lines 306-313
- Removed summary:                       <td className="px-2 py-1 text-slate-500">{inc.cmdb_ci}</td> |                       <td className={`px-2 py-1 text-right font-semibold ${confidenceColor(inc.similarity_score || 0)}`}>
- Added summary:                       <td className="px-2 py-1 text-slate-500">{inc.cmdb_ci}</td>                      <td className={`px-2 py-1 text-right … |                         {(Math.min(inc.similarity_score || 0, 1) * 100).toFixed(0)}%

**Before**

```tsx
                      onClick={() => setExpandedInc(expandedInc === inc.incident_number ? null : inc.incident_number)}>
                      <td className="px-2 py-1 font-mono text-blue-600">{inc.incident_number}</td>
                      <td className="px-2 py-1 text-slate-700 truncate max-w-xs">{inc.short_description}</td>
                      <td className="px-2 py-1 text-slate-500">{inc.cmdb_ci}</td>
                      <td className={`px-2 py-1 text-right font-semibold ${confidenceColor(inc.similarity_score || 0)}`}>
                        {((inc.similarity_score || 0) * 100).toFixed(0)}%
                      </td>
                    </tr>
                  ))}
```

**After**

```tsx
                      onClick={() => setExpandedInc(expandedInc === inc.incident_number ? null : inc.incident_number)}>
                      <td className="px-2 py-1 font-mono text-blue-600">{inc.incident_number}</td>
                      <td className="px-2 py-1 text-slate-700 truncate max-w-xs">{inc.short_description}</td>
                      <td className="px-2 py-1 text-slate-500">{inc.cmdb_ci}</td>                      <td className={`px-2 py-1 text-right font-semibold ${confidenceColor(inc.similarity_score || 0)}`}>
                        {(Math.min(inc.similarity_score || 0, 1) * 100).toFixed(0)}%
                      </td>
                    </tr>
                  ))}
```

### `rexus-main_dev/frontend/src/pages/AuthCallback.tsx` -> `rexus_dt/frontend/src/pages/AuthCallback.tsx`

- Hunk count: 2

#### Hunk 1 — Old lines 1-9 -> New lines 1-9
- Removed summary: [blank line] | const TOKEN_KEY = 'rexus_token';
- Added summary: import { useAuth } from '../contexts/AuthContext'; |   const { loginWithToken } = useAuth();

**Before**

```tsx
import { useEffect, useState } from 'react';
import { authApi } from '../api';

const TOKEN_KEY = 'rexus_token';

export default function AuthCallback() {
  const [error, setError] = useState('');
  const [status, setStatus] = useState('Processing SSO login...');

```

**After**

```tsx
import { useEffect, useState } from 'react';
import { authApi } from '../api';
import { useAuth } from '../contexts/AuthContext';

export default function AuthCallback() {
  const { loginWithToken } = useAuth();
  const [error, setError] = useState('');
  const [status, setStatus] = useState('Processing SSO login...');

```

#### Hunk 2 — Old lines 38-58 -> New lines 38-58
- Removed summary:       } | [blank line]
- Added summary:       }      // Clean up sessionStorage |           setStatus('Exchanging authorization code...');

**Before**

```tsx
      if (!codeVerifier) {
        setError('Missing PKCE code verifier. Please try logging in again.');
        return;
      }

      // Clean up sessionStorage
      sessionStorage.removeItem('sso_code_verifier');
      sessionStorage.removeItem('sso_state');

      try {
        setStatus('Exchanging authorization code...');
        const data = await authApi.ssoCallback(code, codeVerifier);
        localStorage.setItem(TOKEN_KEY, data.token);
        // Redirect to app root
        window.location.href = '/';
      } catch (err) {
        setError(err instanceof Error ? err.message : 'SSO authentication failed');
      }
    }

    handleCallback();
```

**After**

```tsx
      if (!codeVerifier) {
        setError('Missing PKCE code verifier. Please try logging in again.');
        return;
      }      // Clean up sessionStorage
      sessionStorage.removeItem('sso_code_verifier');
      sessionStorage.removeItem('sso_state');

      try {
          setStatus('Exchanging authorization code...');
          const data = await authApi.ssoCallback(code, codeVerifier);
          // Set token + user directly in AuthContext — avoids a /me round-trip
          // that can 401 if the context hasn't rehydrated yet.
          loginWithToken(data);
          // Replace history so back-button doesn't return to /auth/callback
          window.location.replace('/');
        } catch (err) {
          setError(err instanceof Error ? err.message : 'SSO authentication failed');
        }
    }

    handleCallback();
```

### `rexus-main_dev/frontend/src/pages/Incidents.tsx` -> `rexus_dt/frontend/src/pages/Incidents.tsx`

- Hunk count: 1

#### Hunk 1 — Old lines 118-125 -> New lines 118-131
- Removed summary:         )} |       </div>
- Added summary:         )}      </div> | [blank line]

**Before**

```tsx
          >
            <X size={14} /> Clear
          </button>
        )}
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden">
```

**After**

```tsx
          >
            <X size={14} /> Clear
          </button>
        )}      </div>

      {/* Error banner */}
      {error && (
        <div className="px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden">
```

### `rexus-main_dev/frontend/src/pages/Login.tsx` -> `rexus_dt/frontend/src/pages/Login.tsx`

- Hunk count: 5

#### Hunk 1 — Old lines 1-8 -> New lines 1-8
- Removed summary: import { useState, useEffect, type FormEvent } from 'react'; | import { useAuth } from '../contexts/AuthContext';
- Added summary: import { useState, useEffect } from 'react'; | import { LOGGED_OUT_KEY } from '../contexts/AuthContext';

**Before**

```tsx
import { useState, useEffect, type FormEvent } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { authApi, type SSOConfig } from '../api';

// ── PKCE Helpers ────────────────────────────────────────────────

function generateCodeVerifier(): string {
  const array = new Uint8Array(32);
```

**After**

```tsx
import { useState, useEffect } from 'react';
import { authApi, type SSOConfig } from '../api';
import { LOGGED_OUT_KEY } from '../contexts/AuthContext';

// ── PKCE Helpers ──────────────────────────────────────────────────────────────

function generateCodeVerifier(): string {
  const array = new Uint8Array(32);
```

#### Hunk 2 — Old lines 26-38 -> New lines 26-34
- Removed summary:   const { login } = useAuth(); |   const [username, setUsername] = useState('');

**Before**

```tsx
// ── Login Page ──────────────────────────────────────────────────

export default function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [ssoConfig, setSsoConfig] = useState<SSOConfig | null>(null);
  const [ssoLoading, setSsoLoading] = useState(false);

  // Check for SSO error passed via URL params (from callback redirect)
  useEffect(() => {
```

**After**

```tsx
// ── Login Page ──────────────────────────────────────────────────

export default function LoginPage() {
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [ssoConfig, setSsoConfig] = useState<SSOConfig | null>(null);

  // Check for SSO error passed via URL params (from callback redirect)
  useEffect(() => {
```

#### Hunk 3 — Old lines 40-87 -> New lines 36-66
- Removed summary:       // Clean URL |   // Fetch SSO config on mount
- Added summary:   // Fetch SSO config so the button can be enabled |       if (config && config.enabled) setSsoConfig(config);

**Before**

```tsx
    const ssoError = params.get('sso_error');
    if (ssoError) {
      setError(ssoError);
      // Clean URL
      window.history.replaceState({}, '', '/');
    }
  }, []);

  // Fetch SSO config on mount
  useEffect(() => {
    authApi.ssoConfig().then((config) => {
      if (config && config.enabled) {
        setSsoConfig(config);
      }
    });
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(username, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  }

  async function handleSSOLogin() {
    if (!ssoConfig) return;
    setSsoLoading(true);
    setError('');

    try {
      const codeVerifier = generateCodeVerifier();
      const codeChallenge = await generateCodeChallenge(codeVerifier);
      const state = crypto.randomUUID();

      // Store PKCE verifier and state for the callback
      sessionStorage.setItem('sso_code_verifier', codeVerifier);
      sessionStorage.setItem('sso_state', state);

      // Build authorization URL
      const params = new URLSearchParams({
        client_id: ssoConfig.client_id!,
        response_type: 'code',
```

**After**

```tsx
    const ssoError = params.get('sso_error');
    if (ssoError) {
      setError(ssoError);
      window.history.replaceState({}, '', '/');
    }
  }, []);

  // Fetch SSO config so the button can be enabled
  useEffect(() => {
    authApi.ssoConfig().then((config) => {
      if (config && config.enabled) setSsoConfig(config);
    }).catch(() => {});
  }, []);

  async function handleSSOLogin() {
    if (!ssoConfig) return;
    setLoading(true);
    setError('');
    try {
      const codeVerifier = generateCodeVerifier();
      const codeChallenge = await generateCodeChallenge(codeVerifier);
      const state = crypto.randomUUID();

      sessionStorage.setItem('sso_code_verifier', codeVerifier);
      sessionStorage.setItem('sso_state', state);
      // Clear the logged-out flag so the next fresh session auto-redirects again
      sessionStorage.removeItem(LOGGED_OUT_KEY);

      const params = new URLSearchParams({
        client_id: ssoConfig.client_id!,
        response_type: 'code',
```

#### Hunk 4 — Old lines 92-105 -> New lines 71-82
- Removed summary:       if (ssoConfig.audience) { |         params.set('audience', ssoConfig.audience);
- Added summary:       if (ssoConfig.audience) params.set('audience', ssoConfig.audience); |       setLoading(false);

**Before**

```tsx
        state,
      });

      if (ssoConfig.audience) {
        params.set('audience', ssoConfig.audience);
      }

      window.location.href = `${ssoConfig.authorize_url}?${params.toString()}`;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to initiate SSO');
      setSsoLoading(false);
    }
  }

```

**After**

```tsx
        state,
      });

      if (ssoConfig.audience) params.set('audience', ssoConfig.audience);

      window.location.href = `${ssoConfig.authorize_url}?${params.toString()}`;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to initiate SSO');
      setLoading(false);
    }
  }

```

#### Hunk 5 — Old lines 118-196 -> New lines 95-121
- Removed summary:           <form onSubmit={handleSubmit} className="space-y-4"> |             <div>
- Added summary:           <p className="text-center text-sm text-slate-500 mb-6"> |             Sign in with your organisation account

**Before**

```tsx
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-slate-700 mb-1">
                Username
              </label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                placeholder="Enter username"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-slate-700 mb-1">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                placeholder="Enter password"
              />
            </div>

            {error && (
              <div className="bg-red-50 text-red-700 text-sm px-3 py-2 rounded-lg border border-red-200">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-red-500 hover:bg-red-600 disabled:bg-red-300 text-white font-medium py-2.5 rounded-lg text-sm transition-colors"
            >
              {loading ? 'Signing in...' : 'Sign in'}
            </button>
          </form>

          {/* SSO Button — only shown when SSO is enabled */}
          {ssoConfig && (
            <>
              <div className="relative my-5">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-slate-200" />
                </div>
                <div className="relative flex justify-center text-xs">
                  <span className="bg-white px-3 text-slate-400">or</span>
                </div>
              </div>

              <button
                onClick={handleSSOLogin}
                disabled={ssoLoading}
                className="w-full border border-slate-300 hover:bg-slate-50 disabled:opacity-50 text-slate-700 font-medium py-2.5 rounded-lg text-sm transition-colors flex items-center justify-center gap-2"
              >
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                  <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                </svg>
                {ssoLoading ? 'Redirecting...' : 'Sign in with SSO'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
```

**After**

```tsx
            </div>
          </div>

          <p className="text-center text-sm text-slate-500 mb-6">
            Sign in with your organisation account
          </p>

          {error && (
            <div className="bg-red-50 text-red-700 text-sm px-3 py-2 rounded-lg border border-red-200 mb-4">
              {error}
            </div>
          )}

          <button
            onClick={handleSSOLogin}
            disabled={loading || !ssoConfig}
            className="w-full border border-slate-300 hover:bg-slate-50 disabled:opacity-50 text-slate-700 font-medium py-2.5 rounded-lg text-sm transition-colors flex items-center justify-center gap-2"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
            {loading ? 'Redirecting to SSO…' : 'Sign in with SSO'}
          </button>
        </div>
      </div>
    </div>
```

