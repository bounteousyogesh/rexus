from fastapi import APIRouter, Query

from backend.api.database import get_pool
from backend.api.utils.llm_provider import embed_text

router = APIRouter(tags=["search"])


@router.get("/search")
async def vector_search(
    q: str = Query(..., min_length=3, description="Search query text"),
    limit: int = Query(10, ge=1, le=50),
    threshold: float = Query(0.40, ge=0.0, le=1.0),
):
    embedding = await embed_text(q)
    # Build the vector literal and cast explicitly — no hardcoded dimension
    # so it works with any embed model (Cohere 1024-dim, OpenAI 1536-dim, etc.)
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT incident_id, incident_number, short_description,
                      close_notes, similarity_score, cluster_id
               FROM rexus_find_similar($1::vector, $2, $3, FALSE)""",
            embedding_str, threshold, limit,
        )

    return {
        "query": q,
        "threshold": threshold,
        "count": len(rows),
        "results": [dict(r) for r in rows],
    }
