"""Ensure sync schedules interpret naive UTC timestamps consistently."""

from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from backend.api.utils.time_utils import from_naive_utc, to_naive_utc


def test_from_naive_utc_marks_db_timestamp_as_utc():
    naive = datetime(2026, 7, 10, 8, 30, 0)
    aware = from_naive_utc(naive)
    assert aware is not None
    assert aware.tzinfo == timezone.utc
    assert aware.hour == 8
    assert aware.minute == 30


def test_interval_trigger_uses_utc_start_not_local():
    """14:00 IST is stored as 08:30 naive UTC; scheduler must fire at 08:30 UTC."""
    scheduler = BackgroundScheduler(timezone=timezone.utc)
    scheduler.start()
    try:
        start_at = from_naive_utc(datetime(2026, 7, 10, 8, 30, 0))
        trigger = IntervalTrigger(hours=24, start_date=start_at)
        previous = datetime(2026, 7, 9, 0, 0, 0, tzinfo=timezone.utc)
        next_run = trigger.get_next_fire_time(None, previous)
        assert next_run is not None
        assert next_run.tzinfo == timezone.utc
        assert next_run == datetime(2026, 7, 10, 8, 30, 0, tzinfo=timezone.utc)
        assert to_naive_utc(next_run) == datetime(2026, 7, 10, 8, 30, 0)
    finally:
        scheduler.shutdown(wait=False)
