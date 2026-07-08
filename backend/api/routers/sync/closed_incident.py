"""
Closed-incident delta sync via ServiceNow batch/detailed API.

Endpoints:
  GET  /sync/closed-incidents/config — Job schedule + last-run status
  PUT  /sync/closed-incidents/config — Update enabled + interval_hours
  POST /sync/closed-incidents/run     — On-demand sync (default: today)
"""

import asyncio
import logging
import os
from datetime import date

from fastapi import APIRouter, HTTPException, Request, Body

from backend.api.database import get_pool
from backend.api.models.sync import ClosedIncidentSyncConfigUpdate, ClosedIncidentSyncRunRequest
from backend.api.utils.sync_config import (
    fetch_sync_config,
    serialize_sync_config,
    update_sync_run_status,
    update_sync_schedule,
)
from backend.api.utils.time_utils import to_naive_utc, utc_now_naive
from backend.services.servicenow_client import ServiceNowClient

from .sync import (
    enrich_incident_row,
    is_closed_incident,
    limiter,
    upsert_incident_v3_returning,
)

logger = logging.getLogger(__name__)

router = APIRouter()

JOB_NAME = "closed_incident_sync"
ADVISORY_LOCK_ID = 7373890123


async def _upsert_one_incident(conn, pool, data: dict) -> tuple[str, str | None]:
    """Upsert one closed incident. Returns (status, error_message). status: imported|updated|skipped|error."""
    if not is_closed_incident(data):
        num = data.get("incident", {}).get("number", "unknown")
        return "skipped", f"{num}: not closed"

    row, _, _ = await enrich_incident_row(
        pool, conn, data, endpoint="/sync/closed-incidents/run",
    )
    if not row:
        return "skipped", "missing incident number"

    inserted = await upsert_incident_v3_returning(conn, row)
    return ("imported" if inserted else "updated"), None


async def run_closed_incident_sync(
    target_date: date,
    *,
    trigger: str = "manual",
    use_lock: bool = True,
) -> dict:
    """
    Fetch incidents updated on target_date from ServiceNow batch API,
    upsert closed ones into rexus_incidents_v3, mark rexus_incidents_new as Closed.
    """
    pool = await get_pool()
    date_str = target_date.isoformat()
    run_at = utc_now_naive()
    summary = {
        "target_date": date_str,
        "trigger": trigger,
        "fetched": 0,
        "closed": 0,
        "imported": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "closed_marked": 0,
        "errors": [],
    }

    async with pool.acquire() as conn:
        if use_lock:
            locked = await conn.fetchval("SELECT pg_try_advisory_lock($1)", ADVISORY_LOCK_ID)
            if not locked:
                logger.info("Closed incident sync skipped — advisory lock held")
                return {**summary, "skipped_lock": True, "status": "skipped"}

        try:
            client = ServiceNowClient()
            closed_numbers: list[str] = []

            def fetch_batch():
                return list(client.get_incidents_batch_detailed(date_str))

            try:
                entries = await asyncio.to_thread(fetch_batch)
            except Exception as e:
                logger.error("Batch detailed fetch failed for %s: %s", date_str, e, exc_info=True)
                result = {**summary, "status": "error", "error": str(e)[:500]}
                await update_sync_run_status(conn, JOB_NAME, run_at, "error", result)
                return result

            summary["fetched"] = len(entries)

            for data in entries:
                if not is_closed_incident(data):
                    summary["skipped"] += 1
                    continue

                summary["closed"] += 1
                inc_num = data.get("incident", {}).get("number", "unknown")
                try:
                    status, err = await _upsert_one_incident(conn, pool, data)
                    if status == "imported":
                        summary["imported"] += 1
                        if inc_num and inc_num != "unknown":
                            closed_numbers.append(inc_num)
                    elif status == "updated":
                        summary["updated"] += 1
                        if inc_num and inc_num != "unknown":
                            closed_numbers.append(inc_num)
                    else:
                        summary["skipped"] += 1
                        if err:
                            summary["errors"].append(err)
                except Exception as e:
                    summary["failed"] += 1
                    msg = f"{inc_num}: {str(e)[:200]}"
                    summary["errors"].append(msg)
                    logger.error("Failed to sync %s: %s", inc_num, e, exc_info=True)

            if closed_numbers:
                result = await conn.execute(
                    """
                    UPDATE rexus_incidents_new
                    SET state = 'Closed', synced_at = CURRENT_TIMESTAMP
                    WHERE incident_number = ANY($1::text[])
                    """,
                    closed_numbers,
                )
                # result is like "UPDATE N"
                try:
                    summary["closed_marked"] = int(result.split()[-1])
                except (ValueError, IndexError):
                    summary["closed_marked"] = len(closed_numbers)

            status = "success" if summary["failed"] == 0 else "partial"
            summary["status"] = status

            await update_sync_run_status(conn, JOB_NAME, run_at, status, summary)
            logger.info(
                "Closed incident sync %s for %s — imported=%d updated=%d failed=%d",
                status, date_str, summary["imported"], summary["updated"], summary["failed"],
            )
            if trigger == "manual":
                from backend.api.schedulers.closed_incident import refresh_next_run_async
                await refresh_next_run_async()
            return summary
        finally:
            if use_lock:
                await conn.execute("SELECT pg_advisory_unlock($1)", ADVISORY_LOCK_ID)


@router.get("/sync/closed-incidents/config")
async def closed_incidents_config_get():
    """Return schedule and last-run status for the closed-incident sync job."""
    from backend.api.schedulers.closed_incident import get_live_next_run

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


@router.put("/sync/closed-incidents/config")
async def closed_incidents_config_update(req: ClosedIncidentSyncConfigUpdate):
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

    from backend.api.schedulers.closed_incident import reschedule_job_async

    await reschedule_job_async()

    async with pool.acquire() as conn:
        row = await fetch_sync_config(conn, JOB_NAME)
    if not row:
        raise HTTPException(404, f"Sync config not found for job: {JOB_NAME}")
    return serialize_sync_config(row)


@router.post("/sync/closed-incidents/run")
@limiter.limit(os.getenv("RATE_LIMIT_SYNC", "5/minute"))
async def closed_incidents_run(
    request: Request,
    req: ClosedIncidentSyncRunRequest = Body(default_factory=ClosedIncidentSyncRunRequest),
):
    """On-demand sync: incidents updated on the given date (default: today)."""
    target = req.date or date.today()
    result = await run_closed_incident_sync(target, trigger="manual")
    if result.get("skipped_lock"):
        raise HTTPException(409, "Sync already running")
    return result
