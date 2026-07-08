"""
Daily new-incident sync: search for preview, detailed API for database upsert.

Endpoints:
  GET  /sync/new-incidents/config  — Job schedule + last-run status
  PUT  /sync/new-incidents/config  — Update enabled + interval_hours
  GET  /sync/new-incidents/preview — Search today's New-state incidents (basic fields)
  POST /sync/new-incidents/run     — Sync, analyze, and post REXUS comment on each incident
"""

import os
import asyncio
import logging
from datetime import date
from types import SimpleNamespace

from fastapi import APIRouter, HTTPException, Request

from backend.api.database import get_pool
from backend.api.models.analyze import AnalyzeRequest
from backend.api.models.sync import NewIncidentSyncConfigUpdate, NewIncidentsRunRequest
from backend.api.routers.analyze import _build_ticket_json_from_sn, analyze_ticket
from backend.api.utils.rexus_comment import build_rexus_analysis_comment
from backend.api.utils.sync_config import (
    fetch_sync_config,
    serialize_sync_config,
    update_sync_run_status,
    update_sync_schedule,
)
from backend.api.utils.time_utils import to_naive_utc, utc_now_naive
from backend.api.utils.sync_constants import NEW_INCIDENTS_SYNC_MAX
from backend.services.servicenow_client import ServiceNowClient

from .sync import (
    batch_upsert_snapshots,
    enrich_incident_row,
    fetch_incidents_detailed,
    filter_incidents_by_opened_date,
    limiter,
    map_detailed_to_row,
    map_search_incident,
)

logger = logging.getLogger(__name__)

router = APIRouter()

JOB_NAME = "new_incident_sync"
ADVISORY_LOCK_ID = 7373890124


async def _mark_incident_analyzed(pool, incident_number: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE rexus_incidents_new
            SET is_analyzed = TRUE, updated_at = CURRENT_TIMESTAMP
            WHERE incident_number = $1
            """,
            incident_number,
        )


async def _analyze_and_comment(
    request: Request,
    sn_client: ServiceNowClient,
    payloads: list[dict],
    *,
    pool,
) -> tuple[int, int]:
    """Run REXUS analysis and post a ServiceNow comment for each synced incident."""
    comments_posted = 0
    comments_failed = 0

    for data in payloads:
        row = map_detailed_to_row(data, default_state="New")
        if not row:
            comments_failed += 1
            continue
        inc_num = row["incident_number"]
        try:
            ticket_json = await _build_ticket_json_from_sn(data, inc_num)
            analyze_result = await analyze_ticket.__wrapped__(
                request,
                AnalyzeRequest(ticket_json=ticket_json),
            )
            comment = build_rexus_analysis_comment(
                inc_num,
                analyze_result.get("confidence_score", 0.0),
            )
            posted = await asyncio.to_thread(sn_client.add_incident_comment, inc_num, comment)
            if posted:
                await _mark_incident_analyzed(pool, inc_num)
                comments_posted += 1
            else:
                comments_failed += 1
        except Exception as e:
            comments_failed += 1
            logger.warning("Analyze/comment failed for %s: %s", inc_num, e, exc_info=True)

    return comments_posted, comments_failed


async def _get_new_incidents(sync_date: date | None = None) -> list[dict]:
    """Get New-state incidents opened on sync_date from ServiceNow."""
    sync_date = sync_date or date.today()
    try:
        client = ServiceNowClient()
    except ValueError:
        raise HTTPException(503, "ServiceNow credentials not configured")

    day = sync_date.isoformat()
    raw = await asyncio.to_thread(client.get_new_incidents, sync_date)
    incidents = []
    for inc in filter_incidents_by_opened_date(raw, day, day):
        mapped = map_search_incident(inc, default_state="New")
        if mapped:
            incidents.append(mapped)
    return incidents


async def _db_stats(conn, sync_date: date) -> dict:
    row = await conn.fetchrow(
        """
        SELECT COUNT(*)::int AS db_count, MAX(synced_at) AS last_synced_at
        FROM rexus_incidents_new WHERE sync_date = $1
        """,
        sync_date,
    )
    last = row["last_synced_at"]
    return {
        "db_count": row["db_count"] or 0,
        "last_synced_at": last.isoformat() if last else None,
    }


async def run_new_incident_sync(
    *,
    trigger: str = "manual",
    incident_numbers: list[str] | None = None,
    request: Request | None = None,
    use_lock: bool = True,
) -> dict:
    """Fetch new incidents, upsert snapshots, analyze, and post ServiceNow comments."""
    run_at = utc_now_naive()
    sync_date = date.today()
    summary = {
        "sync_date": sync_date.isoformat(),
        "trigger": trigger,
        "inserted": 0,
        "updated": 0,
        "errors": 0,
        "total": 0,
        "comments_posted": 0,
        "comments_failed": 0,
    }

    pool = await get_pool()

    async with pool.acquire() as conn:
        if use_lock:
            locked = await conn.fetchval("SELECT pg_try_advisory_lock($1)", ADVISORY_LOCK_ID)
            if not locked:
                logger.info("New incident sync skipped — advisory lock held")
                return {**summary, "skipped_lock": True, "status": "skipped"}

        try:
            return await _run_new_incident_sync_body(
                pool,
                conn,
                run_at=run_at,
                sync_date=sync_date,
                summary=summary,
                trigger=trigger,
                incident_numbers=incident_numbers,
                request=request,
            )
        finally:
            if use_lock:
                await conn.execute("SELECT pg_advisory_unlock($1)", ADVISORY_LOCK_ID)


async def _run_new_incident_sync_body(
    pool,
    conn,
    *,
    run_at,
    sync_date: date,
    summary: dict,
    trigger: str,
    incident_numbers: list[str] | None,
    request: Request | None,
) -> dict:
    if incident_numbers is None:
        try:
            incidents = await _get_new_incidents(sync_date)
        except HTTPException as exc:
            result = {**summary, "status": "error", "error": str(exc.detail)[:500]}
            await update_sync_run_status(conn, JOB_NAME, run_at, "error", result)
            if trigger == "scheduled":
                logger.warning("Skipping scheduled new-incidents sync: ServiceNow not configured")
                return result
            raise
        incident_numbers = [inc["incident_number"] for inc in incidents]

    if not incident_numbers:
        summary["status"] = "success"
        db_stats = await _db_stats(conn, sync_date)
        await update_sync_run_status(conn, JOB_NAME, run_at, summary["status"], {**summary, **db_stats})
        if trigger == "manual":
            from backend.api.schedulers.new_incident import refresh_next_run_async
            await refresh_next_run_async()
        return {**summary, **db_stats}

    try:
        sn_client = ServiceNowClient()
    except ValueError:
        result = {**summary, "status": "error", "error": "ServiceNow credentials not configured"}
        await update_sync_run_status(conn, JOB_NAME, run_at, "error", result)
        if trigger == "scheduled":
            logger.warning("Skipping scheduled new-incidents sync: ServiceNow not configured")
            return result
        raise HTTPException(503, "ServiceNow credentials not configured")

    payloads = await fetch_incidents_detailed(
        incident_numbers,
        include_kb_articles=True,
        max_incidents=NEW_INCIDENTS_SYNC_MAX,
    )

    incidents: list[dict] = []
    for data in payloads:
        row, _, _ = await enrich_incident_row(
            pool, conn, data,
            endpoint="/sync/new-incidents/run",
            default_state="New",
        )
        if row:
            incidents.append(row)

    try:
        inserted, updated = await batch_upsert_snapshots(conn, incidents, sync_date)
        errors = 0
    except Exception as e:
        inserted = updated = 0
        errors = len(incidents)
        logger.error("Upsert failed for %d incidents: %s", len(incidents), e, exc_info=True)
    db_stats = await _db_stats(conn, sync_date)

    comments_posted, comments_failed = await _analyze_and_comment(
        request or SimpleNamespace(),
        sn_client,
        payloads,
        pool=pool,
    )

    summary.update({
        "inserted": inserted,
        "updated": updated,
        "errors": errors,
        "total": len(incidents),
        "comments_posted": comments_posted,
        "comments_failed": comments_failed,
    })
    status = "success" if errors == 0 and comments_failed == 0 else "partial"
    summary["status"] = status

    await update_sync_run_status(conn, JOB_NAME, run_at, status, {**summary, **db_stats})

    logger.info(
        "New incident sync %s for %s — inserted=%d updated=%d total=%d",
        status, sync_date.isoformat(), inserted, updated, len(incidents),
    )

    if trigger == "manual":
        from backend.api.schedulers.new_incident import refresh_next_run_async
        await refresh_next_run_async()

    return {**summary, **db_stats}


@router.get("/sync/new-incidents/config")
async def new_incidents_config_get():
    """Return schedule and last-run status for the new-incident sync job."""
    from backend.api.schedulers.new_incident import get_live_next_run

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await fetch_sync_config(conn, JOB_NAME)
    if not row:
        raise HTTPException(404, f"Sync config not found for job: {JOB_NAME}")

    live_next = get_live_next_run()
    if live_next is not None:
        row = dict(row)
        row["next_run_at"] = to_naive_utc(live_next)

    return serialize_sync_config(row)


@router.put("/sync/new-incidents/config")
async def new_incidents_config_update(req: NewIncidentSyncConfigUpdate):
    """Update enabled flag and interval_hours; reschedules the in-process job."""
    if req.interval_hours < 1 or req.interval_hours > 168:
        raise HTTPException(400, "interval_hours must be between 1 and 168")

    pool = await get_pool()
    async with pool.acquire() as conn:
        updated = await update_sync_schedule(
            conn,
            JOB_NAME,
            enabled=req.enabled,
            interval_hours=req.interval_hours,
        )
    if not updated:
        raise HTTPException(404, f"Sync config not found for job: {JOB_NAME}")

    from backend.api.schedulers.new_incident import reschedule_job_async

    await reschedule_job_async()

    async with pool.acquire() as conn:
        row = await fetch_sync_config(conn, JOB_NAME)
    if not row:
        raise HTTPException(404, f"Sync config not found for job: {JOB_NAME}")
    return serialize_sync_config(row)


@router.get("/sync/new-incidents/preview")
async def new_incidents_preview():
    """Get today's new incidents from ServiceNow for preview."""
    sync_date = date.today()
    pool = await get_pool()

    async def fetch_db_stats() -> dict:
        async with pool.acquire() as conn:
            return await _db_stats(conn, sync_date)

    incidents, db_stats = await asyncio.gather(_get_new_incidents(), fetch_db_stats())
    return {
        "sync_date": sync_date.isoformat(),
        "total": len(incidents),
        "incidents": incidents,
        **db_stats,
    }


@router.post("/sync/new-incidents/run")
@limiter.limit(os.getenv("RATE_LIMIT_SYNC", "5/minute"))
async def new_incidents_run(request: Request, req: NewIncidentsRunRequest):
    """Sync to rexus_incidents_new, analyze each incident, and post a REXUS comment on SN."""
    incident_numbers = req.incident_numbers or None
    result = await run_new_incident_sync(
        trigger="manual",
        incident_numbers=incident_numbers,
        request=request,
    )
    if result.get("skipped_lock"):
        raise HTTPException(409, "Sync already running")
    return result
