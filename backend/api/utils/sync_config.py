"""Shared helpers for rexus_sync_config read/write and API serialization."""

import json
from datetime import datetime


def format_utc_iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    return dt.isoformat() + "Z"


async def fetch_sync_config(conn, job_name: str) -> dict | None:
    row = await conn.fetchrow(
        """
        SELECT job_name, enabled, interval_hours, last_run_at, last_status,
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
) -> bool:
    row = await conn.fetchrow(
        """
        UPDATE rexus_sync_config
        SET enabled = $2, interval_hours = $3, updated_at = CURRENT_TIMESTAMP
        WHERE job_name = $1
        RETURNING job_name
        """,
        job_name,
        enabled,
        interval_hours,
    )
    return row is not None
