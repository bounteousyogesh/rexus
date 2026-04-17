from fastapi import APIRouter, Query, HTTPException
from backend.api.database import get_pool

router = APIRouter(tags=["incidents"])


@router.get("/incidents")
async def list_incidents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: str | None = None,
    cmdb_ci: str | None = None,
    state: str | None = None,
    assignment_group: str | None = None,
    search: str | None = None,
):
    pool = await get_pool()
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
        conditions.append(f"(short_description ILIKE ${idx} OR close_notes ILIKE ${idx})")
        params.append(f"%{search}%")
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with pool.acquire() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM rexus_incidents_v3 {where}", *params
        )
        rows = await conn.fetch(
            f"""SELECT id, incident_number, short_description, category, subcategory,
                       priority, state, cmdb_ci, assignment_group, close_notes,
                       opened_at, resolved_at, business_duration
                FROM rexus_incidents_v3 {where}
                ORDER BY opened_at DESC NULLS LAST
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
                      caller_id, location, company
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
