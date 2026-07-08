"""
Closed-incident sync scheduler (interval-based, DB-driven config).
"""

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING

from backend.api.schedulers import incident as incident_scheduler

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

JOB_ID = "closed_incident_sync"
LOG_LABEL = "Closed incident sync"


async def _run_scheduled_sync() -> None:
    """Scheduled run: process incidents updated yesterday."""
    from backend.api.routers.sync.closed_incident import run_closed_incident_sync

    logger.info("Scheduled closed incident sync starting")
    try:
        yesterday = date.today() - timedelta(days=1)
        result = await run_closed_incident_sync(yesterday, trigger="scheduled")
        logger.info(
            "Scheduled closed incident sync finished — status=%s imported=%s updated=%s",
            result.get("status"),
            result.get("imported"),
            result.get("updated"),
        )
    except Exception:
        logger.exception("Scheduled closed incident sync failed")
        raise
    finally:
        await refresh_next_run_async()


async def refresh_next_run_async():
    return await incident_scheduler.refresh_next_run_async(JOB_ID)


def get_live_next_run():
    return incident_scheduler.get_live_next_run(JOB_ID)


async def register_job(scheduler: "AsyncIOScheduler") -> None:
    await incident_scheduler.register_incident_sync_job(
        scheduler,
        job_id=JOB_ID,
        run_fn=_run_scheduled_sync,
        log_label=LOG_LABEL,
    )


async def reschedule_job_async() -> None:
    await incident_scheduler.reschedule_job_async(JOB_ID, _run_scheduled_sync, LOG_LABEL)


def reschedule_job() -> None:
    incident_scheduler.reschedule_job(JOB_ID, _run_scheduled_sync, LOG_LABEL)
