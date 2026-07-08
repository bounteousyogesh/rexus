"""Build ServiceNow comment text for REXUS analysis links."""

import os


def rexus_public_url() -> str:
    url = (os.getenv("REXUS_PUBLIC_URL") or "").strip().rstrip("/")
    if not url:
        raise ValueError("REXUS_PUBLIC_URL is not set in the environment")
    return url


def build_rexus_analysis_comment(
    incident_number: str,
    confidence_score: float,
) -> str:
    """Three-line briefing posted to ServiceNow after sync-and-analyze."""
    inc = (incident_number or "").strip().upper()
    pct = round(min(max(confidence_score, 0.0), 1.0) * 100)
    url = f"{rexus_public_url()}/?incident={inc}"
    return (
        f"<b>[REXUS] Pre-triage intelligence available ({pct}% match).</b>\n"
        "Relevant historical resolutions and knowledge guidance have already been mapped to this incident.\n"
        f"<b>Expected First Step: </b>Review REXUS findings manual investigation🔗{url}"
    )
