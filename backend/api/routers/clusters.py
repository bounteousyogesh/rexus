from typing import Literal
from fastapi import APIRouter, Query, HTTPException
from backend.api.database import get_pool

router = APIRouter(tags=["clusters"])

# ARCH-004 / ENH-004: Allowed sort columns — enforced via Literal so FastAPI
# validates the value without a fragile regex and the OpenAPI docs show valid choices.
SortColumn = Literal["incident_count", "avg_resolution_hours", "cluster_name"]


@router.get("/clusters")
async def list_clusters(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    min_size: int = Query(1, ge=1),
    sort_by: SortColumn = Query("incident_count"),
):
    pool = await get_pool()
    offset = (page - 1) * page_size

    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM rexus_clusters WHERE incident_count >= $1", min_size
        )
        rows = await conn.fetch(
            f"""SELECT id, cluster_name, cluster_description, incident_count,
                       dominant_category, avg_resolution_hours, avg_internal_similarity,
                       status, created_at
                FROM rexus_clusters
                WHERE incident_count >= $1
                ORDER BY {sort_by} DESC NULLS LAST
                LIMIT $2 OFFSET $3""",
            min_size, page_size, offset,
        )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "items": [dict(r) for r in rows],
    }


@router.get("/clusters/{cluster_id}")
async def get_cluster(cluster_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        cluster = await conn.fetchrow(
            """SELECT id, cluster_name, cluster_description, incident_count,
                      problem_ids, dominant_category, avg_resolution_hours,
                      avg_internal_similarity, status, created_at
               FROM rexus_clusters WHERE id = $1""",
            cluster_id,
        )
        if not cluster:
            raise HTTPException(404, "Cluster not found")

        # Top incidents in this cluster
        incidents = await conn.fetch(
            """SELECT ri.incident_number, ri.short_description, ri.close_notes,
                      ri.cmdb_ci, ri.assignment_group, ri.business_duration,
                      rcm.similarity_to_centroid
               FROM rexus_cluster_mapping rcm
               JOIN rexus_incidents_v3 ri ON ri.id = rcm.incident_id
               WHERE rcm.cluster_id = $1
               ORDER BY rcm.similarity_to_centroid DESC
               LIMIT 20""",
            cluster_id,
        )

        # Playbook for this cluster
        playbook = await conn.fetchrow(
            "SELECT id, title, grounding_score, status FROM rexus_playbooks WHERE cluster_id = $1",
            cluster_id,
        )

    result = dict(cluster)
    result["top_incidents"] = [dict(i) for i in incidents]
    result["playbook"] = dict(playbook) if playbook else None
    return result
