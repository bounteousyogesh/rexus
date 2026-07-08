"""Shared APScheduler helpers for incident sync jobs."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from backend.api.database import get_pool
from backend.api.schedulers.scheduler import get_scheduler
from backend.api.utils.time_utils import to_naive_utc, utc_now_naive

logger = logging.getLogger(__name__)

MISFIRE_GRACE_SECONDS = int(timedelta(hours=24).total_seconds())


async def load_job_config(job_id: str) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT enabled, interval_hours
            FROM rexus_sync_config
            WHERE job_name = $1
            """,
            job_id,
        )
    return dict(row) if row else None


async def _update_next_run_at(job_id: str, next_run: datetime | None) -> None:
    pool = await get_pool()
    now = utc_now_naive()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE rexus_sync_config
            SET next_run_at = $2, updated_at = $3
            WHERE job_name = $1
            """,
            job_id,
            to_naive_utc(next_run),
            now,
        )


async def refresh_next_run_async(job_id: str) -> datetime | None:
    """Persist APScheduler's live next-run time to rexus_sync_config."""
    scheduler = get_scheduler()
    if scheduler is None:
        return None
    job = scheduler.get_job(job_id)
    next_run = job.next_run_time if job else None
    await _update_next_run_at(job_id, next_run)
    return next_run


def get_live_next_run(job_id: str) -> datetime | None:
    """Return the scheduler's in-memory next run (may be newer than DB)."""
    scheduler = get_scheduler()
    if scheduler is None:
        return None
    job = scheduler.get_job(job_id)
    return job.next_run_time if job else None


async def register_incident_sync_job(
    scheduler: AsyncIOScheduler,
    *,
    job_id: str,
    run_fn: Callable[[], Awaitable[None]],
    log_label: str,
) -> None:
    """Reload config from DB and register an interval-based incident sync job."""
    config = await load_job_config(job_id)
    if not config:
        logger.warning("No sync config for %s — scheduler job not registered", job_id)
        return

    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    if not config.get("enabled", True):
        await _update_next_run_at(job_id, None)
        logger.info("%s scheduler disabled", log_label)
        return

    hours = int(config.get("interval_hours") or 24)
    scheduler.add_job(
        run_fn,
        trigger=IntervalTrigger(hours=hours),
        id=job_id,
        max_instances=1,
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
    )

    await refresh_next_run_async(job_id)
    job = scheduler.get_job(job_id)
    next_run = job.next_run_time if job else None
    logger.info(
        "%s scheduled every %d hour(s); next run: %s",
        log_label,
        hours,
        next_run,
    )


async def reschedule_job_async(job_id: str, run_fn: Callable[[], Awaitable[None]], log_label: str) -> None:
    """Reload config from DB and reschedule an incident sync job."""
    scheduler = get_scheduler()
    if scheduler is None:
        return
    await register_incident_sync_job(
        scheduler,
        job_id=job_id,
        run_fn=run_fn,
        log_label=log_label,
    )


def reschedule_job(job_id: str, run_fn: Callable[[], Awaitable[None]], log_label: str) -> None:
    """Schedule a reschedule on the running event loop (fire-and-forget)."""
    if get_scheduler() is None:
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    loop.create_task(reschedule_job_async(job_id, run_fn, log_label))
