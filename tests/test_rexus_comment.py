"""Tests for ServiceNow REXUS analysis comment formatting."""

import os
from unittest.mock import patch

import pytest

from backend.api.utils.rexus_comment import build_rexus_analysis_comment


@pytest.fixture(autouse=True)
def _rexus_env(monkeypatch):
    monkeypatch.setenv("REXUS_PUBLIC_URL", "https://rexus.discounttire.com")
    monkeypatch.setenv("SERVICENOW_INSTANCE", "https://dtcprod.service-now.com")


def test_build_rexus_analysis_comment_full_format():
    similar = [
        "INC2401234",
        "INC2405678",
        "INC2409012",
        "INC2412345",
        "INC2416789",
        "INC2411111",
        "INC2422222",
        "INC2433333",
    ]
    comment = build_rexus_analysis_comment(
        "INC2409818",
        0.92,
        match_count=8,
        similar_incident_numbers=similar,
    )
    assert "[REXUS] Pre-triage intelligence available: Found 8 similar incidents (92% match)." in comment
    assert "<b>" not in comment
    assert "Prior resolutions, playbook actions, and KA/KB guidance are already available." in comment
    assert "Review REXUS findings before starting triage. Similar Incidents:" in comment
    assert "[code]<a href='https://dtcprod.service-now.com/nav_to.do?uri=incident.do%3Fsysparm_query%3Dnumber%3DINC2401234' target='_blank'>INC2401234</a>[/code]" in comment
    assert "<a href=" in comment
    assert "(+3 more in REXUS)" in comment
    assert "[code]<a href='https://rexus.discounttire.com/?incident=INC2409818' target='_blank'>Open in REXUS</a>[/code]" in comment


def test_build_rexus_analysis_comment_without_servicenow_instance():
    with patch.dict(os.environ, {"SERVICENOW_INSTANCE": ""}, clear=False):
        comment = build_rexus_analysis_comment(
            "INC2409818",
            0.75,
            match_count=2,
            similar_incident_numbers=["INC2401234", "INC2405678"],
        )

    assert "INC2401234" in comment
    assert "INC2405678" in comment
    assert "<a href=" not in comment


def test_build_rexus_analysis_comment_no_similar_incidents():
    comment = build_rexus_analysis_comment("INC2409818", 0.0, match_count=0)

    assert "Found 0 similar incidents (0% match)" in comment
    assert "Similar Incidents:" in comment
    assert "None found" in comment
    assert "<b>" not in comment
