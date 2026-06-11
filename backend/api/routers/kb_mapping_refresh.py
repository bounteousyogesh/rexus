"""
REX-US — KB mapping refresh

Endpoints:
  GET  /kb-mappings/refresh/preview — List DB incidents grouped by period (no SN)
  POST /kb-mappings/refresh         — Refresh KB mappings for a batch of incidents
"""

import logging
import os
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Depends
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.api.auth import require_admin_or_api_key
from backend.api.database import get_pool
from backend.api.utils.incident_groups import group_incidents_by_period
from backend.api.utils.sync_constants import IncidentNumber, KB_MAPPING_REFRESH_MAX
from backend.services.kb_mapping_refresh import run_kb_mapping_refresh
from backend.services.servicenow_client import ServiceNowClient

logger = logging.getLogger(__name__)

router = APIRouter(tags=["kb-mapping-refresh"])
limiter = Limiter(key_func=get_remote_address)

KbArticleFilter = Literal["all", "synced", "not_synced"]


class KbMappingRefreshRequest(BaseModel):
    incident_numbers: list[IncidentNumber] = Field(..., max_length=KB_MAPPING_REFRESH_MAX)


def _serialize_incident_row(row: dict) -> dict:
    inc = dict(row)
    opened = inc.get("opened_at")
    if opened is not None:
        inc["opened_at"] = str(opened)
    return inc


@router.get("/kb-mappings/refresh/preview")
async def kb_mapping_refresh_preview(
    request: Request,
    has_kb_article: KbArticleFilter = Query("not_synced"),
):
    """
    Preview incidents in rexus_incidents_v3 grouped by day/week/month.
    Optional filter on has_kb_article (all / synced / not_synced). No ServiceNow calls.
    """
    conditions = [
        "incident_number IS NOT NULL",
        "incident_number ~ '^INC[0-9]+$'",
    ]
    if has_kb_article == "not_synced":
        conditions.append("has_kb_article IS NULL")
    elif has_kb_article == "synced":
        conditions.append("has_kb_article IS NOT NULL")

    sql = f"""
        SELECT incident_number, short_description, opened_at, cmdb_ci, category, has_kb_article
        FROM rexus_incidents_v3
        WHERE {' AND '.join(conditions)}
        ORDER BY opened_at DESC NULLS LAST
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql)

    incidents = [_serialize_incident_row(dict(r)) for r in rows]
    grouped = group_incidents_by_period(incidents)

    return {
        "filter": {"has_kb_article": has_kb_article},
        "total": len(incidents),
        **grouped,
    }


@router.post("/kb-mappings/refresh")
@limiter.limit(os.getenv("RATE_LIMIT_SYNC", "5/minute"))
async def kb_mapping_refresh(
    request: Request,
    req: KbMappingRefreshRequest,
    _admin: dict = Depends(require_admin_or_api_key),
):
    """
    Refresh KB article incident mappings from ServiceNow for the given incidents.
    Updates has_kb_article on each row after checking ServiceNow.

    Requires admin JWT or X-Admin-Key matching REXUS_ADMIN_KEY.
    """
    if not req.incident_numbers:
        raise HTTPException(400, "No incidents to refresh")

    pool = await get_pool()
    logger.info("KB mapping refresh: processing %d incidents", len(req.incident_numbers))
    result = await run_kb_mapping_refresh(pool, ServiceNowClient(), req.incident_numbers)
    summary = result["summary"]
    logger.info(
        "KB mapping refresh complete — candidates=%d with_kb=%d inserted=%d already_mapped=%d "
        "no_kb=%d not_found=%d errors=%d",
        summary["candidates"],
        summary["with_kb"],
        summary["kb_rows_inserted"],
        summary["kb_rows_existing"],
        summary["no_kb"],
        summary["not_found"],
        summary["errors"],
    )
    return result