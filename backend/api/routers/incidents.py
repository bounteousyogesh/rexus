from datetime import date

from fastapi import APIRouter, Query, HTTPException
from backend.api.database import get_pool

router = APIRouter(tags=["incidents"])

def _kb_incident_match(alias: str) -> str:
    return f"UPPER(TRIM(m.incident_number)) = UPPER(TRIM({alias}.incident_number))"

# Pre-aggregated KA numbers per incident — joined once instead of a per-row subquery.
_KB_ARTICLE_NUMBERS_JOIN = """
LEFT JOIN (
    SELECT UPPER(TRIM(incident_number)) AS inc_norm,
           STRING_AGG(DISTINCT knowledge_article_number, ', '
                     ORDER BY knowledge_article_number) AS kb_article_numbers
    FROM rexus_kb_article_incident_mapping
    GROUP BY UPPER(TRIM(incident_number))
) kb ON kb.inc_norm = UPPER(TRIM(i.incident_number))
"""

# Only expose KA numbers when sync flag confirms a KB exists
_KB_ARTICLE_NUMBERS_SELECT = (
    "CASE WHEN i.has_kb_article = TRUE THEN kb.kb_article_numbers END AS kb_article_numbers"
)

def _kb_filter_join(param_idx: int) -> str:
    return f"""
INNER JOIN rexus_kb_article_incident_mapping m_filter
  ON {_kb_incident_match('i')}
 AND UPPER(TRIM(m_filter.knowledge_article_number)) = UPPER(TRIM(${param_idx}))
"""

async def _list_new_incidents(
    conn,
    *,
    page: int,
    page_size: int,
    search: str | None,
) -> dict:
    """Paginated list from rexus_incidents_new for the latest sync_date."""
    sync_date = await conn.fetchval(
        "SELECT MAX(sync_date) FROM rexus_incidents_new"
    )
    if not sync_date:
        return {
            "total": 0,
            "page": page,
            "page_size": page_size,
            "pages": 1,
            "sync_date": date.today().isoformat(),
            "items": [],
        }

    conditions = ["i.sync_date = $1"]
    params: list = [sync_date]
    idx = 2

    if search:
        conditions.append(
            f"(i.incident_number ILIKE ${idx} OR i.short_description ILIKE ${idx} "
            f"OR i.cmdb_ci ILIKE ${idx} OR i.category ILIKE ${idx} "
            f"OR i.assignment_group ILIKE ${idx})"
        )
        params.append(f"%{search}%")
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}"
    offset = (page - 1) * page_size

    total = await conn.fetchval(
        f"SELECT COUNT(*) FROM rexus_incidents_new i {where}", *params
    )
    rows = await conn.fetch(
        f"""SELECT i.id, i.incident_number, i.short_description, i.category, i.priority, i.state,
                   i.cmdb_ci, i.assignment_group, i.assigned_to, i.opened_by, i.opened_at,
                   i.has_kb_article,
                   CASE WHEN i.has_kb_article = TRUE THEN kb.kb_article_numbers END AS kb_article_numbers
            FROM rexus_incidents_new i
            {_KB_ARTICLE_NUMBERS_JOIN}
            {where}
            ORDER BY i.opened_at DESC NULLS LAST, i.incident_number
            LIMIT ${idx} OFFSET ${idx + 1}""",
        *params, page_size, offset,
    )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "sync_date": sync_date.isoformat(),
        "items": [dict(r) for r in rows],
    }

@router.get("/incidents")
async def list_incidents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: str | None = None,
    cmdb_ci: str | None = None,
    state: str | None = None,
    state_group: str | None = None,
    assignment_group: str | None = None,
    search: str | None = None,
    kb_article: str | None = None,
):
    pool = await get_pool()

    if state_group == "new":
        async with pool.acquire() as conn:
            return await _list_new_incidents(
                conn, page=page, page_size=page_size, search=search,
            )

    offset = (page - 1) * page_size

    conditions = []
    params = []
    idx = 1

    if category:
        conditions.append(f"category = ${idx}")
        params.append(category)
        idx += 1
    if cmdb_ci:
        conditions.append(f"cmdb_ci = ${idx}")
        params.append(cmdb_ci)
        idx += 1
    if state:
        conditions.append(f"state = ${idx}")
        params.append(state)
        idx += 1
    if assignment_group:
        conditions.append(f"assignment_group = ${idx}")
        params.append(assignment_group)
        idx += 1
    if search:
        conditions.append(
            f"(incident_number ILIKE ${idx} OR short_description ILIKE ${idx} "
            f"OR description ILIKE ${idx} OR close_notes ILIKE ${idx})"
        )
        params.append(f"%{search}%")
        idx += 1

    kb_filter_join = ""
    if kb_article and kb_article.strip():
        kb_filter_join = _kb_filter_join(idx)
        params.append(kb_article.strip())
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with pool.acquire() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM rexus_incidents_v3 i {kb_filter_join} {where}", *params
        )
        rows = await conn.fetch(
            f"""SELECT i.id, i.incident_number, i.short_description, i.category, i.subcategory,
                       i.priority, i.state, i.cmdb_ci, i.assignment_group, i.close_notes,
                       i.opened_at, i.resolved_at, i.business_duration, i.has_kb_article,
                       {_KB_ARTICLE_NUMBERS_SELECT}
                FROM rexus_incidents_v3 i
                {kb_filter_join}
                {_KB_ARTICLE_NUMBERS_JOIN}
                {where}
                ORDER BY i.opened_at DESC NULLS LAST
                LIMIT ${idx} OFFSET ${idx + 1}""",
            *params, page_size, offset,
        )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "items": [dict(r) for r in rows],
    }

@router.get("/incidents/kb-articles")
async def list_incident_kb_articles():
    """Distinct KA numbers linked to incidents with has_kb_article = TRUE."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT m.knowledge_article_number, COUNT(DISTINCT i.id) AS incident_count
               FROM rexus_kb_article_incident_mapping m
               INNER JOIN rexus_incidents_v3 i ON {_kb_incident_match('i')}
               WHERE i.has_kb_article = TRUE
               GROUP BY m.knowledge_article_number
               ORDER BY m.knowledge_article_number"""
        )
    return {"items": [dict(r) for r in rows]}

@router.get("/incidents/{incident_number}")
async def get_incident(incident_number: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        # SEC-014: work_notes is intentionally excluded from the API response.
        # It may contain PII (names, email addresses, phone numbers from notes).
        # If work_notes are needed for a specific use-case, add a separate
        # privileged endpoint with appropriate access controls.
        row = await conn.fetchrow(
            """SELECT id, incident_number, sys_id, problem_id, parent_incident,
                      short_description, description,
                      category, subcategory, priority, state, close_code,
                      assignment_group, assigned_to, cmdb_ci, business_service,
                      close_notes, opened_at, resolved_at, closed_at,
                      business_duration, u_jira_number, u_order_number,
                      caller_id, location, company, has_kb_article
               FROM rexus_incidents_v3 WHERE incident_number = $1""",
            incident_number,
        )
        if not row:
            raise HTTPException(404, "Incident not found")

        # Get cluster info if available
        cluster = await conn.fetchrow(
            """SELECT rc.id, rc.cluster_name, rcm.similarity_to_centroid
               FROM rexus_cluster_mapping rcm
               JOIN rexus_clusters rc ON rc.id = rcm.cluster_id
               WHERE rcm.incident_id = $1""",
            row["id"],
        )

    result = dict(row)
    result["cluster"] = dict(cluster) if cluster else None
    return result
