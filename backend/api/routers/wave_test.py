"""
REX-US Wave Testing — Pick incidents from test waves and analyze them.

The key rule: when testing a wave incident, we only send the "intake" data
(short_description, description, category, cmdb_ci, caller, location) to the
analyzer — NOT the work_notes, close_notes, or problem_id. Those are the
"answers" we compare against.
"""

import re
from fastapi import APIRouter, Query, HTTPException
from backend.api.database import get_pool

router = APIRouter(tags=["wave_test"])

# ARCH-012: Allowlist pattern for wave parameter — must match wave_N or wave_<label>
_WAVE_RE = re.compile(r'^wave_[a-zA-Z0-9_]{1,40}$')


def _validate_wave(wave: str) -> str:
    """Validate the wave path parameter against the allowed format."""
    if not _WAVE_RE.match(wave):
        raise HTTPException(400, "Invalid wave identifier. Must match pattern: wave_<alphanumeric>")
    return wave


@router.get("/waves")
async def list_waves():
    """List available test waves with counts."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT split_group, COUNT(*) as total,
                   MIN(opened_at)::date as from_date,
                   MAX(opened_at)::date as to_date,
                   COUNT(*) FILTER (WHERE problem_id IS NOT NULL AND problem_id != '') as with_problem,
                   COUNT(*) FILTER (WHERE work_notes IS NOT NULL AND length(work_notes) > 50) as with_notes
            FROM rexus_incidents
            WHERE split_group LIKE 'wave_%'
            GROUP BY split_group
            ORDER BY MIN(opened_at)
        """)
    return {"waves": [dict(r) for r in rows]}


@router.get("/waves/{wave}/incidents")
async def list_wave_incidents(
    wave: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List incidents in a test wave (shows basic info only, not the answers)."""
    _validate_wave(wave)  # ARCH-012
    pool = await get_pool()
    offset = (page - 1) * page_size

    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM rexus_incidents WHERE split_group = $1", wave
        )
        rows = await conn.fetch(
            """SELECT incident_number, short_description, category, subcategory,
                      cmdb_ci, priority, caller_id, location, opened_at,
                      -- These are the "answers" — show as indicators only
                      CASE WHEN problem_id IS NOT NULL AND problem_id != '' THEN true ELSE false END as has_problem,
                      CASE WHEN close_notes IS NOT NULL AND length(close_notes) > 10 THEN true ELSE false END as has_resolution,
                      CASE WHEN u_jira_number IS NOT NULL AND u_jira_number != '' THEN true ELSE false END as has_jira
               FROM rexus_incidents
               WHERE split_group = $1
               ORDER BY opened_at
               LIMIT $2 OFFSET $3""",
            wave, page_size, offset,
        )

    return {
        "wave": wave,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "items": [dict(r) for r in rows],
    }


@router.get("/waves/{wave}/test/{incident_number}")
async def get_test_incident(wave: str, incident_number: str):
    """
    Get a test incident split into:
    - input: what we send to the analyzer (what the team sees at intake)
    - actual: the real resolution (hidden, for comparison after analysis)
    """
    _validate_wave(wave)  # ARCH-012
    pool = await get_pool()
    async with pool.acquire() as conn:
        # ENH-014: Explicit column list instead of SELECT * to avoid accidental
        # exposure of future columns and to make the query self-documenting.
        row = await conn.fetchrow(
            """SELECT incident_number, split_group, short_description, description,
                      category, subcategory, priority, state, impact, urgency,
                      cmdb_ci, assignment_group, caller_id, location,
                      opened_at, resolved_at, closed_at,
                      close_notes, work_notes,
                      problem_id, u_jira_number, u_order_number,
                      u_correction_type, u_error_category,
                      u_resolved_by, business_duration, reassignment_count
               FROM rexus_incidents
               WHERE incident_number = $1 AND split_group = $2""",
            incident_number, wave,
        )
        if not row:
            raise HTTPException(404, "Incident not found in this wave")

    r = dict(row)

    # INPUT: what we give to the analyzer (simulating a new ticket)
    input_data = {
        "pdf_fields": {
            "Short description": r["short_description"] or "",
            "Description": r["description"] or "",
        },
        "incident_section": {
            "Number": r["incident_number"],
            "Category": r["category"] or "",
            "Subcategory": r["subcategory"] or "",
            "Priority": r["priority"] or "",
            "Configuration item": r["cmdb_ci"] or "",
            "Assignment group": r["assignment_group"] or "",
            "Caller": r["caller_id"] or "",
            "Location": r["location"] or "",
            "Opened": str(r["opened_at"]) if r["opened_at"] else "",
            "Impact": r["impact"] or "",
            "Urgency": r["urgency"] or "",
        },
        "resolution_information_section": {},
    }

    # ACTUAL: the real answers (for comparison after running the analysis)
    # SEC-014: work_notes and u_resolved_by excluded — may contain PII
    actual = {
        "problem_id": r["problem_id"],
        "u_jira_number": r["u_jira_number"],
        "close_notes": r["close_notes"],
        "u_order_number": r["u_order_number"],
        "u_correction_type": r["u_correction_type"],
        "u_error_category": r["u_error_category"],
        "business_duration": r["business_duration"],
        "reassignment_count": r["reassignment_count"],
        "assignment_group": r["assignment_group"],
    }

    return {
        "incident_number": r["incident_number"],
        "wave": wave,
        "input": input_data,
        "actual": actual,
    }
