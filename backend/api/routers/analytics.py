import json
from fastapi import APIRouter, Query, HTTPException
from backend.api.database import get_pool

router = APIRouter(tags=["analytics"])


@router.get("/analytics")
async def get_analytics():
    pool = await get_pool()
    async with pool.acquire() as conn:
        # ARCH-011: Combine the four overview counts into a single query to
        # reduce round-trips; remaining queries return set-valued results so
        # they cannot be trivially merged.
        overview_row = await conn.fetchrow(
            """SELECT
                COUNT(*)                                          AS incident_count,
                COUNT(*) FILTER (WHERE embedding IS NOT NULL)    AS embedded_count,
                (SELECT COUNT(*) FROM rexus_clusters)            AS cluster_count,
                (SELECT COUNT(*) FROM rexus_playbooks)           AS playbook_count
               FROM rexus_incidents"""
        )

        # Category breakdown
        categories = await conn.fetch(
            """SELECT category, COUNT(*) as count
               FROM rexus_incidents
               WHERE category IS NOT NULL
               GROUP BY category ORDER BY count DESC"""
        )

        # Top CMDB CIs
        top_cmdb = await conn.fetch(
            """SELECT cmdb_ci, COUNT(*) as count
               FROM rexus_incidents
               WHERE cmdb_ci IS NOT NULL
               GROUP BY cmdb_ci ORDER BY count DESC LIMIT 15"""
        )

        # Top assignment groups
        top_groups = await conn.fetch(
            """SELECT assignment_group, COUNT(*) as count
               FROM rexus_incidents
               WHERE assignment_group IS NOT NULL
               GROUP BY assignment_group ORDER BY count DESC LIMIT 15"""
        )

        # Resolution time stats (using business_stc in seconds)
        resolution_stats = await conn.fetchrow(
            """SELECT ROUND(AVG(business_stc / 3600.0)::numeric, 1) as avg_hours,
                      ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY business_stc / 3600.0)::numeric, 1) as median_hours,
                      ROUND(MIN(business_stc / 3600.0)::numeric, 1) as min_hours,
                      ROUND(MAX(business_stc / 3600.0)::numeric, 1) as max_hours
               FROM rexus_incidents
               WHERE business_stc IS NOT NULL AND business_stc > 0"""
        )

        # Top clusters by size
        top_clusters = await conn.fetch(
            """SELECT id, cluster_name, incident_count, avg_resolution_hours
               FROM rexus_clusters
               ORDER BY incident_count DESC LIMIT 10"""
        )

        # Incidents over time (monthly)
        monthly_trend = await conn.fetch(
            """SELECT DATE_TRUNC('month', opened_at) as month, COUNT(*) as count
               FROM rexus_incidents
               WHERE opened_at IS NOT NULL
               GROUP BY month ORDER BY month"""
        )

        # State breakdown
        states = await conn.fetch(
            """SELECT state, COUNT(*) as count
               FROM rexus_incidents
               WHERE state IS NOT NULL
               GROUP BY state ORDER BY count DESC"""
        )

    return {
        "overview": {
            "total_incidents": overview_row["incident_count"],
            "total_clusters": overview_row["cluster_count"],
            "total_playbooks": overview_row["playbook_count"],
            "embedded_incidents": overview_row["embedded_count"],
        },
        "categories": [dict(r) for r in categories],
        "top_cmdb_cis": [dict(r) for r in top_cmdb],
        "top_assignment_groups": [dict(r) for r in top_groups],
        "resolution_time": dict(resolution_stats) if resolution_stats else {},
        "top_clusters": [dict(r) for r in top_clusters],
        "monthly_trend": [dict(r) for r in monthly_trend],
        "states": [dict(r) for r in states],
    }


# ═══════════════════════════════════════════════════════════════════
# Analysis Log — review past analyses
# ENH-010: These endpoints logically belong in a separate router
# (e.g. backend/api/routers/analysis_log.py).  They live here for now
# to keep the router count low, but can be extracted if the module grows.
# ═══════════════════════════════════════════════════════════════════

@router.get("/analysis-log")
async def list_analyses(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    pool = await get_pool()
    offset = (page - 1) * page_size

    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM rexus_analysis_log")
        rows = await conn.fetch(
            """SELECT id, incident_number, cleaned_issue, confidence_score,
                      match_count, dominant_cluster_name, top_problem_id,
                      focused_playbook_grounding, created_at
               FROM rexus_analysis_log
               ORDER BY created_at DESC
               LIMIT $1 OFFSET $2""",
            page_size, offset,
        )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "items": [dict(r) for r in rows],
    }


@router.get("/analysis-log/{log_id}")
async def get_analysis(log_id: int):
    # SEC-004 FIX: Don't return raw input_json or full_response (contains PII)
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, incident_number, cleaned_issue, confidence_score,
                      match_count, dominant_cluster_id, dominant_cluster_name,
                      focused_playbook_content, focused_playbook_grounding,
                      top_problem_id, created_at
               FROM rexus_analysis_log WHERE id = $1""", log_id
        )
        if not row:
            raise HTTPException(404, "Analysis not found")

    return dict(row)


# ═══════════════════════════════════════════════════════════════════
# Token Usage Dashboard
# ═══════════════════════════════════════════════════════════════════

@router.get("/token-usage")
async def get_token_usage(
    days: int = Query(30, ge=1, le=365),
):
    """Token usage summary for the last N days."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Overall totals
        totals = await conn.fetchrow("""
            SELECT COUNT(*) as total_calls,
                   COALESCE(SUM(input_tokens), 0) as total_input_tokens,
                   COALESCE(SUM(output_tokens), 0) as total_output_tokens,
                   COALESCE(SUM(input_tokens + output_tokens), 0) as total_tokens,
                   COALESCE(SUM(estimated_cost_usd), 0)::float as total_cost_usd
            FROM rexus_token_usage
            WHERE created_at >= NOW() - INTERVAL '1 day' * $1
        """, days)

        # By model
        by_model = await conn.fetch("""
            SELECT model,
                   COUNT(*) as calls,
                   SUM(input_tokens) as input_tokens,
                   SUM(output_tokens) as output_tokens,
                   SUM(estimated_cost_usd)::float as cost_usd
            FROM rexus_token_usage
            WHERE created_at >= NOW() - INTERVAL '1 day' * $1
            GROUP BY model ORDER BY cost_usd DESC
        """, days)

        # By endpoint
        by_endpoint = await conn.fetch("""
            SELECT endpoint,
                   COUNT(*) as calls,
                   SUM(input_tokens + output_tokens) as total_tokens,
                   SUM(estimated_cost_usd)::float as cost_usd
            FROM rexus_token_usage
            WHERE created_at >= NOW() - INTERVAL '1 day' * $1
            GROUP BY endpoint ORDER BY cost_usd DESC
        """, days)

        # Daily trend
        daily = await conn.fetch("""
            SELECT DATE(created_at) as date,
                   COUNT(*) as calls,
                   SUM(input_tokens + output_tokens) as tokens,
                   SUM(estimated_cost_usd)::float as cost_usd
            FROM rexus_token_usage
            WHERE created_at >= NOW() - INTERVAL '1 day' * $1
            GROUP BY DATE(created_at) ORDER BY date
        """, days)

    return {
        "period_days": days,
        "totals": dict(totals) if totals else {},
        "by_model": [dict(r) for r in by_model],
        "by_endpoint": [dict(r) for r in by_endpoint],
        "daily_trend": [dict(r) for r in daily],
    }
