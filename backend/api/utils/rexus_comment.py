"""Build ServiceNow comment text for REXUS analysis links."""

import os

_SIMILAR_INCIDENTS_SHOWN = 5


def rexus_public_url() -> str | None:
    """Return the configured public URL, or None if not set."""
    url = (os.getenv("REXUS_PUBLIC_URL") or "").strip().rstrip("/")
    return url or None


def _format_similar_incidents(similar_incident_numbers: list[str], match_count: int) -> str:
    instance = (os.getenv("SERVICENOW_INSTANCE") or "").strip().rstrip("/")
    shown = [n.strip().upper() for n in similar_incident_numbers if n and n.strip()][:_SIMILAR_INCIDENTS_SHOWN]
    if not shown:
        return "None found"

    links = [
        f'<a href="{instance}/nav_to.do?uri=incident.do?sysparm_query=number={n}">{n}</a>' if instance else n
        for n in shown
    ]
    extra = match_count - len(shown)
    suffix = f" (+{extra} more in REXUS)" if extra > 0 else ""
    return ", ".join(links) + suffix


def build_rexus_analysis_comment(
    incident_number: str,
    confidence_score: float,
    *,
    match_count: int = 0,
    similar_incident_numbers: list[str] | None = None,
) -> str:
    """Four-line briefing posted to ServiceNow after sync-and-analyze."""
    inc = (incident_number or "").strip().upper()
    pct = round(min(max(confidence_score, 0.0), 1.0) * 100)
    base_url = rexus_public_url()

    numbers = similar_incident_numbers or []
    count = match_count if match_count > 0 else len(numbers)
    incident_word = "incident" if count == 1 else "incidents"
    similar_text = _format_similar_incidents(numbers, count)

    link_line = f"🔗 {base_url}/?incident={inc}" if base_url else "(REXUS_PUBLIC_URL not configured)"

    return (
        f"<b>[REXUS] Pre-triage intelligence available: Found {count} similar "
        f"{incident_word} ({pct}% match).</b>\n"
        "Prior resolutions, playbook actions, and KA/KB guidance are already available.\n"
        f"<b>Review REXUS findings before starting triage. Similar Incidents:</b> {similar_text}\n"
        f"{link_line}"
    )
