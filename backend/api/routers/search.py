import json
from fastapi import APIRouter, Query
from openai import AsyncOpenAI

from backend.api.config import OPENAI_API_KEY
from backend.api.database import get_pool

router = APIRouter(tags=["search"])

# ARCH-007: This module owns the shared AsyncOpenAI singleton.
# analyze.py imports embed_text() from here rather than creating its own client.
# If additional routers need embeddings, import embed_text from this module.
_openai_client: AsyncOpenAI | None = None


def _get_openai() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


async def embed_text(text: str) -> list[float]:
    client = _get_openai()
    resp = await client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return resp.data[0].embedding


@router.get("/search")
async def vector_search(
    q: str = Query(..., min_length=3, description="Search query text"),
    limit: int = Query(10, ge=1, le=50),
    threshold: float = Query(0.40, ge=0.0, le=1.0),
):
    embedding = await embed_text(q)
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT incident_id, incident_number, short_description,
                      close_notes, similarity_score, cluster_id
               FROM rexus_find_similar($1::vector, $2, $3, TRUE)""",
            embedding_str, threshold, limit,
        )

    return {
        "query": q,
        "threshold": threshold,
        "count": len(rows),
        "results": [dict(r) for r in rows],
    }
