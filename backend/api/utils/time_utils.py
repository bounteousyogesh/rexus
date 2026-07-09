"""UTC datetime helpers for DB storage (naive timestamps)."""

from datetime import datetime, timezone


def utc_now_naive() -> datetime:
    """Current UTC time as naive datetime (DB storage convention)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def from_naive_utc(dt: datetime | None) -> datetime | None:
    """Attach UTC to naive DB timestamps for APScheduler (expects aware datetimes)."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=timezone.utc)
