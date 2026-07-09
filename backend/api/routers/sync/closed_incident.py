"""
Closed-incident delta sync via ServiceNow batch/detailed API.

Endpoints:
  GET  /sync/closed-incidents/config — Job schedule + last-run status
  PUT  /sync/closed-incidents/config — Update enabled + interval_hours + start_at
  POST /sync/closed-incidents/run     — On-demand sync (date range, default: today)
"""

import asyncio
import logging
import os
from datetime import date, datetime, timedelta

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
from backend.api.utils.sync_constants import NEW_INCIDENTS_SYNC_MAX
from backend.services.servicenow_client import ServiceNowClient

from .sync import (
    enrich_incident_row,
    fetch_incidents_detailed,
    is_incident_state,
    limiter,
    map_search_incident,
    upsert_incident_v3_returning,
)

logger = logging.getLogger(__name__)

router = APIRouter()

JOB_NAME = "closed_incident_sync"
ADVISORY_LOCK_ID = 7373890123


async def _upsert_one_incident(conn, pool, data: dict) -> tuple[str, str | None]:
    """Upsert one closed incident. Returns (status, error_message). status: imported|updated|skipped|error."""
    if not is_incident_state(data, "closed"):
        num = data.get("incident", {}).get("number", "unknown")
        return "skipped", f"{num}: not closed"

    row, _, _ = await enrich_incident_row(
        pool, conn, data, endpoint="/sync/closed-incidents/run",
    )
    if not row:
        return "skipped", "missing incident number"

    inserted = await upsert_incident_v3_returning(conn, row)
    return ("imported" if inserted else "updated"), None


async def _process_detailed_entries(
    conn,
    pool,
    entries: list[dict],
    summary: dict,
    closed_numbers: list[str],
) -> None:
    for data in entries:
        if not is_incident_state(data, "closed"):
            summary["skipped"] += 1
            continue

        summary["closed"] += 1
        inc_num = data.get("incident", {}).get("number", "unknown")
        try:
            status, err = await _upsert_one_incident(conn, pool, data)
            if status in ("imported", "updated"):
                summary[status] += 1
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


async def _mark_new_incidents_closed(conn, closed_numbers: list[str]) -> int:
    if not closed_numbers:
        return 0
    result = await conn.execute(
        """
        UPDATE rexus_incidents_new
        SET state = 'Closed', synced_at = CURRENT_TIMESTAMP
        WHERE incident_number = ANY($1::text[])
        """,
        closed_numbers,
    )
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError):
        return len(closed_numbers)


async def _run_closed_via_batch_days(
    client: ServiceNowClient,
    conn,
    pool,
    start_date: date,
    end_date: date,
    summary: dict,
) -> None:
    """Manual path: one SN batch/detailed call per calendar day."""
    closed_numbers: list[str] = []
    day = start_date
    while day <= end_date:
        date_str = day.isoformat()

        def fetch_batch(d=date_str):
            return list(client.get_incidents_batch_detailed(d))

        try:
            entries = await asyncio.to_thread(fetch_batch)
        except Exception as e:
            logger.error("Batch detailed fetch failed for %s: %s", date_str, e, exc_info=True)
            summary["failed"] += 1
            summary["errors"].append(f"{date_str}: {str(e)[:200]}")
            day += timedelta(days=1)
            continue

        summary["fetched"] += len(entries)
        await _process_detailed_entries(conn, pool, entries, summary, closed_numbers)
        day += timedelta(days=1)

    summary["closed_marked"] = await _mark_new_incidents_closed(conn, closed_numbers)


async def _run_closed_via_search_window(
    client: ServiceNowClient,
    conn,
    pool,
    window_start: datetime,
    window_end: datetime,
    summary: dict,
) -> None:
    """Scheduled path: search datetime window, then detailed fetch + upsert."""
    try:
        raw = await asyncio.to_thread(
            client.search_closed_incidents_window,
            window_start,
            window_end,
        )
    except Exception as e:
        logger.error("Closed search window failed: %s", e, exc_info=True)
        raise

    numbers: list[str] = []
    for inc in raw:
        mapped = map_search_incident(inc)
        if mapped and mapped.get("incident_number"):
            numbers.append(mapped["incident_number"])

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_numbers = []
    for num in numbers:
        if num not in seen:
            seen.add(num)
            unique_numbers.append(num)

    summary["fetched"] = len(unique_numbers)
    if not unique_numbers:
        return

    payloads = await fetch_incidents_detailed(
        unique_numbers,
        include_kb_articles=False,
        max_incidents=NEW_INCIDENTS_SYNC_MAX,
    )

    closed_numbers: list[str] = []
    await _process_detailed_entries(conn, pool, payloads, summary, closed_numbers)
    summary["closed_marked"] = await _mark_new_incidents_closed(conn, closed_numbers)


async def run_closed_incident_sync(
    *,
    trigger: str = "manual",
    use_lock: bool = True,
    start_date: date | None = None,
    end_date: date | None = None,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> dict:
    """
    Fetch closed incidents from ServiceNow and upsert into rexus_incidents_v3.

    Manual: calendar date range via batch/detailed (per day).
    Scheduled: datetime window via search + detailed.
    """
    pool = await get_pool()
    run_at = utc_now_naive()

    if window_start is not None and window_end is not None:
        start_date = window_start.date()
        end_date = window_end.date()
    else:
        start_date = start_date or date.today()
        end_date = end_date or start_date

    summary = {
        "target_date": end_date.isoformat(),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
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
    if window_start is not None and window_end is not None:
        summary["window_start"] = window_start.isoformat()
        summary["window_end"] = window_end.isoformat()

    async with pool.acquire() as conn:
        if use_lock:
            locked = await conn.fetchval("SELECT pg_try_advisory_lock($1)", ADVISORY_LOCK_ID)
            if not locked:
                logger.info("Closed incident sync skipped — advisory lock held")
                return {**summary, "skipped_lock": True, "status": "skipped"}

        try:
            try:
                client = ServiceNowClient()
            except ValueError as e:
                result = {**summary, "status": "error", "error": str(e)[:500]}
                if trigger == "scheduled":
                    await update_sync_run_status(conn, JOB_NAME, run_at, "error", result)
                    logger.warning("Skipping scheduled closed-incident sync: ServiceNow not configured")
                    return result
                raise HTTPException(503, "ServiceNow credentials not configured")

            try:
                if window_start is not None and window_end is not None and trigger == "scheduled":
                    await _run_closed_via_search_window(
                        client, conn, pool, window_start, window_end, summary,
                    )
                else:
                    await _run_closed_via_batch_days(
                        client, conn, pool, start_date, end_date, summary,
                    )
            except Exception as e:
                result = {**summary, "status": "error", "error": str(e)[:500]}
                if trigger == "scheduled":
                    await update_sync_run_status(conn, JOB_NAME, run_at, "error", result)
                return result

            status = "success" if summary["failed"] == 0 else "partial"
            summary["status"] = status

            if trigger == "scheduled":
                await update_sync_run_status(conn, JOB_NAME, run_at, status, summary)

            logger.info(
                "Closed incident sync %s for %s → %s — imported=%d updated=%d failed=%d",
                status,
                start_date.isoformat(),
                end_date.isoformat(),
                summary["imported"],
                summary["updated"],
                summary["failed"],
            )
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
    """Update enabled, interval_hours, and start_at; reschedules the in-process job."""
    if req.interval_hours < 1 or req.interval_hours > 168:
        raise HTTPException(400, "interval_hours must be between 1 and 168")

    pool = await get_pool()
    async with pool.acquire() as conn:
        updated = await update_sync_schedule(
            conn,
            JOB_NAME,
            enabled=req.enabled,
            interval_hours=req.interval_hours,
            start_at=req.start_at,
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
    """On-demand sync: incidents updated in the given date range (default: today)."""
    result = await run_closed_incident_sync(
        trigger="manual",
        start_date=req.start_date,
        end_date=req.end_date,
    )
    if result.get("skipped_lock"):
        raise HTTPException(409, "Sync already running")
    return result
