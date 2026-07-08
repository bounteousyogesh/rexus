"""
New-incident sync scheduler (interval-based, DB-driven config).
"""

import logging
from typing import TYPE_CHECKING

from backend.api.schedulers import incident as incident_scheduler

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

JOB_ID = "new_incident_sync"
LOG_LABEL = "New incident sync"


async def _run_scheduled_sync() -> None:
    """Scheduled run: sync today's new incidents from ServiceNow."""
    from backend.api.routers.sync.new_incident import run_new_incident_sync

    logger.info("Scheduled new incident sync starting")
    try:
        result = await run_new_incident_sync(trigger="scheduled")
        logger.info(
            "Scheduled new incident sync finished — status=%s inserted=%s updated=%s total=%s",
            result.get("status"),
            result.get("inserted"),
            result.get("updated"),
            result.get("total"),
        )
    except Exception:
        logger.exception("Scheduled new incident sync failed")
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
