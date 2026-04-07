from fastapi import APIRouter
from backend.api.database import get_pool

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    pool = await get_pool()
    async with pool.acquire() as conn:
        # ARCH-015 FIX: Use estimated count (fast) instead of COUNT(*) (full scan)
        row = await conn.fetchrow(
            "SELECT reltuples::bigint as cnt FROM pg_class WHERE relname = 'rexus_incidents'"
        )
        return {
            "status": "healthy",
            "database": "connected",
            "incidents_count": row["cnt"] if row else 0,
        }
