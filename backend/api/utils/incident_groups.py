"""Group incidents by month, week, and day (reverse-chronological)."""

from datetime import datetime


def _opened_date(opened) -> datetime | None:
    if not opened:
        return None
    if isinstance(opened, datetime):
        return opened
    try:
        return datetime.strptime(str(opened)[:10], "%Y-%m-%d")
    except ValueError:
        return None


def group_incidents_by_period(incidents: list[dict]) -> dict:
    """
    Group incidents into by_month, by_week, and by_day buckets.

    Each bucket is a list of {key, count, incidents} sorted newest-first,
    matching the structure returned by GET /sync/delta and KB mapping refresh preview.
    """
    months: dict[str, list] = {}
    weeks: dict[str, list] = {}
    days: dict[str, list] = {}

    for inc in incidents:
        dt = _opened_date(inc.get("opened_at"))
        if not dt:
            continue
        month_key = dt.strftime("%Y-%m")
        week_key = f"{dt.year}-W{dt.isocalendar()[1]:02d}"
        day_key = dt.strftime("%Y-%m-%d")

        months.setdefault(month_key, []).append(inc)
        weeks.setdefault(week_key, []).append(inc)
        days.setdefault(day_key, []).append(inc)

    sorted_months = sorted(months.items(), key=lambda x: x[0], reverse=True)
    sorted_weeks = sorted(weeks.items(), key=lambda x: x[0], reverse=True)
    sorted_days = sorted(days.items(), key=lambda x: x[0], reverse=True)

    return {
        "by_month": [
            {"month": m, "count": len(incs), "incidents": incs} for m, incs in sorted_months
        ],
        "by_week": [
            {"week": w, "count": len(incs), "incidents": incs} for w, incs in sorted_weeks
        ],
        "by_day": [
            {"day": d, "count": len(incs), "incidents": incs} for d, incs in sorted_days
        ],
    }