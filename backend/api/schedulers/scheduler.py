"""
In-process APScheduler coordination for sync jobs.

Registers closed-incident and new-incident jobs from this package.
"""

import asyncio
import logging
from datetime import timezone

from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_MISSED
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.api.utils.time_utils import utc_now_naive

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler | None:
    return _scheduler


def _on_scheduler_event(event) -> None:
    from backend.api.schedulers.closed_incident import (
        JOB_ID as CLOSED_JOB_ID,
        refresh_next_run_async as refresh_closed_next_run_async,
    )
    from backend.api.schedulers.new_incident import (
        JOB_ID as NEW_JOB_ID,
        refresh_next_run_async as refresh_new_next_run_async,
    )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    if event.job_id == CLOSED_JOB_ID:
        loop.create_task(refresh_closed_next_run_async())
    elif event.job_id == NEW_JOB_ID:
        loop.create_task(refresh_new_next_run_async())


async def start_scheduler() -> AsyncIOScheduler:
    """Start the global scheduler and register all sync jobs."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    from backend.api.schedulers.closed_incident import register_job as register_closed_incident
    from backend.api.schedulers.new_incident import register_job as register_new_incident

    _scheduler = AsyncIOScheduler(timezone=timezone.utc)
    _scheduler.add_listener(_on_scheduler_event, EVENT_JOB_EXECUTED | EVENT_JOB_MISSED)
    _scheduler.start()
    await register_closed_incident(_scheduler)
    await register_new_incident(_scheduler)
    return _scheduler


async def stop_scheduler() -> None:
    """Shut down the scheduler on app shutdown."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")
