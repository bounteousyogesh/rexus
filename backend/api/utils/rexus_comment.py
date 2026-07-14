"""Build ServiceNow comment text for REXUS analysis links."""

import os

_SIMILAR_INCIDENTS_SHOWN = 5


def rexus_public_url() -> str | None:
    """Return the configured public URL, or None if not set."""
    url = (os.getenv("REXUS_PUBLIC_URL", "https://rexus.qa.discounttire.com") or "").strip().rstrip("/")
    return url or None


def _format_similar_incidents(similar_incident_numbers: list[str], match_count: int) -> str:
    from urllib.parse import quote
    instance = (os.getenv("SERVICENOW_INSTANCE") or "").strip().rstrip("/")
    shown = [n.strip().upper() for n in similar_incident_numbers if n and n.strip()][:_SIMILAR_INCIDENTS_SHOWN]
    if not shown:
        return "None found"

    if instance:
        lines = [
            f"{instance}/nav_to.do?uri={quote(f'incident.do?sysparm_query=number={n}')}"
            for n in shown
        ]
    else:
        lines = shown

    extra = match_count - len(shown)
    suffix = f"\n(+{extra} more in REXUS)" if extra > 0 else ""
    return "\n" + "\n".join(lines) + suffix


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

    link_line = f"\n🔗 {base_url}/?incident={inc}" if base_url else "\n(REXUS_PUBLIC_URL not configured)"

    return (
        f"[REXUS] Pre-triage intelligence available: Found {count} similar "
        f"{incident_word} ({pct}% match).\n"
        "Prior resolutions, playbook actions, and KA/KB guidance are already available.\n"
        f"Review REXUS findings before starting triage. Similar Incidents:"
        f"{similar_text}"
        f"{link_line}"
    )
