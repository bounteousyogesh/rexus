import os
import time
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from backend.api.database import get_pool

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)

# Track when the app started
_start_time = time.time()


@router.get("/health")
async def health_check():
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT reltuples::bigint as cnt FROM pg_class WHERE relname = 'rexus_incidents'"
        )
        return {
            "status": "healthy",
            "database": "connected",
            "incidents_count": row["cnt"] if row else 0,
        }


_ADMIN_KEY = os.getenv("REXUS_ADMIN_KEY", "")


@router.get("/health/detailed")
async def health_detailed(x_admin_key: Optional[str] = Header(None)):
    """
    Comprehensive health check for monitoring and observability.
    If REXUS_ADMIN_KEY is set, requires X-Admin-Key header to access.
    """
    if _ADMIN_KEY and x_admin_key != _ADMIN_KEY:
        raise HTTPException(403, "Admin key required for detailed health check")
    checks = {}
    overall = "healthy"

    # 1. Database connectivity + pool stats
    try:
        pool = await get_pool()
        db_start = time.time()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_latency = round((time.time() - db_start) * 1000)

        pool_size = pool.get_size()
        pool_free = pool.get_idle_size()
        pool_min = pool.get_min_size()
        pool_max = pool.get_max_size()

        checks["database"] = {
            "status": "connected",
            "latency_ms": db_latency,
            "pool": {
                "active": pool_size - pool_free,
                "idle": pool_free,
                "total": pool_size,
                "min": pool_min,
                "max": pool_max,
            },
        }
    except Exception as e:
        checks["database"] = {"status": "error", "error": str(e)[:100]}
        overall = "degraded"

    # 2. Knowledge base stats
    try:
        async with pool.acquire() as conn:
            kb = await conn.fetchrow("""
                SELECT
                    (SELECT reltuples::bigint FROM pg_class WHERE relname = 'rexus_incidents_v3') as incidents_v3,
                    (SELECT reltuples::bigint FROM pg_class WHERE relname = 'rexus_incidents') as incidents_v1,
                    (SELECT reltuples::bigint FROM pg_class WHERE relname = 'rexus_clusters') as clusters,
                    (SELECT reltuples::bigint FROM pg_class WHERE relname = 'rexus_problems') as problems,
                    (SELECT reltuples::bigint FROM pg_class WHERE relname = 'rexus_analysis_log') as analyses,
                    (SELECT reltuples::bigint FROM pg_class WHERE relname = 'rexus_feedback') as feedback
            """)
            checks["knowledge_base"] = {
                "incidents_v3": kb["incidents_v3"] or 0,
                "incidents_v1": kb["incidents_v1"] or 0,
                "clusters": kb["clusters"] or 0,
                "problems": kb["problems"] or 0,
                "analyses_run": kb["analyses"] or 0,
                "feedback_entries": kb["feedback"] or 0,
            }
    except Exception as e:
        checks["knowledge_base"] = {"status": "error", "error": str(e)[:100]}

    # 3. LLM connectivity
    try:
        from backend.api.utils.llm_provider import embed_text, get_provider_info
        provider_info = get_provider_info()
        ai_start = time.time()
        await embed_text("health check")
        ai_latency = round((time.time() - ai_start) * 1000)
        checks["llm"] = {
            "status": "connected",
            "latency_ms": ai_latency,
            **provider_info,
        }
    except Exception as e:
        err = str(e)[:100]
        checks["llm"] = {"status": "error", "error": err}
        if "rate_limit" in err.lower() or "429" in err:
            checks["llm"]["status"] = "rate_limited"
            overall = "degraded"
        else:
            overall = "degraded"

    # 4. ServiceNow connectivity
    try:
        from backend.services.servicenow_client import ServiceNowClient
        sn_client = ServiceNowClient()
        sn_start = time.time()
        # Just verify we can get an OAuth token (doesn't fetch data)
        sn_client._get_token()
        sn_latency = round((time.time() - sn_start) * 1000)
        checks["servicenow"] = {
            "status": "connected",
            "latency_ms": sn_latency,
            "instance": os.getenv("SERVICENOW_INSTANCE", "").replace("https://", "").replace("http://", ""),
        }
    except ValueError:
        checks["servicenow"] = {"status": "not_configured"}
    except Exception as e:
        checks["servicenow"] = {"status": "error", "error": str(e)[:100]}
        overall = "degraded"

    # 5. Token usage (last 24h)
    try:
        async with pool.acquire() as conn:
            usage = await conn.fetchrow("""
                SELECT COUNT(*) as calls,
                       COALESCE(SUM(input_tokens + output_tokens), 0) as tokens,
                       COALESCE(SUM(estimated_cost_usd), 0)::float as cost_usd
                FROM rexus_token_usage
                WHERE created_at >= NOW() - INTERVAL '24 hours'
            """)
            checks["token_usage_24h"] = {
                "api_calls": usage["calls"] or 0,
                "total_tokens": usage["tokens"] or 0,
                "estimated_cost_usd": round(usage["cost_usd"] or 0, 4),
            }
    except Exception:
        checks["token_usage_24h"] = {"status": "table_not_found"}

    # 6. Recent analysis activity
    try:
        async with pool.acquire() as conn:
            recent = await conn.fetchrow("""
                SELECT COUNT(*) as count_24h,
                       MAX(created_at) as last_analysis,
                       AVG(confidence_score)::float as avg_confidence
                FROM rexus_analysis_log
                WHERE created_at >= NOW() - INTERVAL '24 hours'
            """)
            checks["analysis_activity_24h"] = {
                "analyses": recent["count_24h"] or 0,
                "last_analysis": str(recent["last_analysis"]) if recent["last_analysis"] else None,
                "avg_confidence": round(recent["avg_confidence"] or 0, 3),
            }
    except Exception:
        checks["analysis_activity_24h"] = {"status": "error"}

    # 7. Application info
    uptime_seconds = int(time.time() - _start_time)
    uptime_hours = uptime_seconds // 3600
    uptime_minutes = (uptime_seconds % 3600) // 60

    checks["application"] = {
        "version": "v7",
        "environment": os.getenv("REXUS_ENV", "development"),
        "uptime": f"{uptime_hours}h {uptime_minutes}m",
        "uptime_seconds": uptime_seconds,
        "started_at": datetime.fromtimestamp(_start_time).isoformat(),
        "rate_limits": {
            "analyze": os.getenv("RATE_LIMIT_ANALYZE", "20/minute"),
            "sync": os.getenv("RATE_LIMIT_SYNC", "5/minute"),
            "default": os.getenv("RATE_LIMIT_DEFAULT", "60/minute"),
        },
    }

    return {
        "status": overall,
        "timestamp": datetime.now().isoformat(),
        "checks": checks,
    }
