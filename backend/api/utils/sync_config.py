"""Shared helpers for rexus_sync_config read/write and API serialization."""

import json
from datetime import datetime, timedelta

from backend.api.utils.time_utils import to_naive_utc, utc_now_naive

MAX_SYNC_WINDOW = timedelta(days=7)


def format_utc_iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    return dt.isoformat() + "Z"


def format_sn_datetime(dt: datetime) -> str:
    """Format naive UTC datetime for ServiceNow search start_date/end_date."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def compute_scheduled_window(
    last_run_at: datetime | None,
    interval_hours: int,
    *,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """
    Scheduled SN query window: [last_run_at → now], clamped to 7 days.
    First run (no last_run_at): look back one interval from now.
    """
    now = now or utc_now_naive()
    hours = max(1, int(interval_hours or 24))
    interval = timedelta(hours=hours)

    if last_run_at is not None:
        window_start = to_naive_utc(last_run_at) or now - interval
    else:
        window_start = now - interval

    window_end = now

    if window_end - window_start > MAX_SYNC_WINDOW:
        window_start = window_end - MAX_SYNC_WINDOW

    if window_start >= window_end:
        window_start = window_end - interval

    return window_start, window_end


async def fetch_sync_config(conn, job_name: str) -> dict | None:
    row = await conn.fetchrow(
        """
        SELECT job_name, enabled, interval_hours, start_at, last_run_at, last_status,
               last_result, next_run_at, updated_at
        FROM rexus_sync_config
        WHERE job_name = $1
        """,
        job_name,
    )
    return dict(row) if row else None


def serialize_sync_config(row: dict) -> dict:
    last_result = row.get("last_result")
    if isinstance(last_result, str):
        try:
            last_result = json.loads(last_result)
        except json.JSONDecodeError:
            pass
    return {
        "job_name": row["job_name"],
        "enabled": row["enabled"],
        "interval_hours": row["interval_hours"],
        "start_at": format_utc_iso(row.get("start_at")),
        "last_run_at": format_utc_iso(row.get("last_run_at")),
        "last_status": row.get("last_status"),
        "last_result": last_result,
        "next_run_at": format_utc_iso(row.get("next_run_at")),
        "updated_at": format_utc_iso(row.get("updated_at")),
    }


async def update_sync_run_status(
    conn,
    job_name: str,
    run_at: datetime,
    status: str,
    result: dict,
) -> None:
    await conn.execute(
        """
        UPDATE rexus_sync_config
        SET last_run_at = $2, last_status = $3,
            last_result = $4::jsonb, updated_at = $2
        WHERE job_name = $1
        """,
        job_name,
        run_at,
        status,
        json.dumps(result),
    )


async def update_sync_schedule(
    conn,
    job_name: str,
    *,
    enabled: bool,
    interval_hours: int,
    start_at: datetime | None,
) -> bool:
    row = await conn.fetchrow(
        """
        UPDATE rexus_sync_config
        SET enabled = $2, interval_hours = $3, start_at = $4,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_name = $1
        RETURNING job_name
        """,
        job_name,
        enabled,
        interval_hours,
        to_naive_utc(start_at),
    )
    return row is not None
