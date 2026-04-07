"""
test_analyze.py — Tests for the core analysis endpoints.

Endpoints under test:
  POST /api/v1/analyze        — analyze a ServiceNow ticket JSON
  POST /api/v1/analyze/text   — analyze plain text
  POST /api/v1/parse-pdf      — upload a PDF and extract JSON

Key security regressions verified:
  SEC-003: embedding_text must NOT appear in /analyze response
  SEC-014: work_notes must NOT appear in similar_incidents items

Note: /analyze and /analyze/text call OpenAI (embeddings + GPT-4o completions),
so these tests use the `openai_client` fixture which has a 60-second timeout.
/parse-pdf does NOT call OpenAI, so it uses the fast `client` fixture.
"""

import io
import pytest
import httpx


ANALYZE_URL = "/api/v1/analyze"
ANALYZE_TEXT_URL = "/api/v1/analyze/text"
PARSE_PDF_URL = "/api/v1/parse-pdf"


# ===========================================================================
# POST /analyze — happy-path response shape
# ===========================================================================

def test_analyze_with_valid_ticket_json_returns_200(
    openai_client: httpx.Client, minimal_ticket_json: dict
):
    """POST /analyze with a valid ServiceNow ticket JSON must return HTTP 200."""
    response = openai_client.post(ANALYZE_URL, json=minimal_ticket_json)
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text[:300]}"
    )


def test_analyze_response_contains_confidence_score(
    openai_client: httpx.Client, minimal_ticket_json: dict
):
    """POST /analyze response must include `confidence_score` (float 0.0-1.0)."""
    body = openai_client.post(ANALYZE_URL, json=minimal_ticket_json).json()
    assert "confidence_score" in body, "Missing confidence_score in /analyze response"
    score = body["confidence_score"]
    assert isinstance(score, float), f"confidence_score must be float, got {type(score)}"
    assert 0.0 <= score <= 1.0, f"confidence_score out of [0,1] range: {score}"


def test_analyze_response_contains_similar_incidents(
    openai_client: httpx.Client, minimal_ticket_json: dict
):
    """POST /analyze response must include `similar_incidents` list."""
    body = openai_client.post(ANALYZE_URL, json=minimal_ticket_json).json()
    assert "similar_incidents" in body, "Missing similar_incidents in /analyze response"
    assert isinstance(body["similar_incidents"], list)


def test_analyze_response_contains_focused_playbook(
    openai_client: httpx.Client, minimal_ticket_json: dict
):
    """POST /analyze response must include `focused_playbook` dict."""
    body = openai_client.post(ANALYZE_URL, json=minimal_ticket_json).json()
    assert "focused_playbook" in body, "Missing focused_playbook in /analyze response"
    assert isinstance(body["focused_playbook"], dict)


def test_analyze_response_contains_match_count(
    openai_client: httpx.Client, minimal_ticket_json: dict
):
    """POST /analyze response must include `match_count` non-negative integer."""
    body = openai_client.post(ANALYZE_URL, json=minimal_ticket_json).json()
    assert "match_count" in body
    assert isinstance(body["match_count"], int)
    assert body["match_count"] >= 0


def test_analyze_response_contains_cleaned_issue(
    openai_client: httpx.Client, minimal_ticket_json: dict
):
    """POST /analyze response must include `cleaned_issue` string."""
    body = openai_client.post(ANALYZE_URL, json=minimal_ticket_json).json()
    assert "cleaned_issue" in body
    assert isinstance(body["cleaned_issue"], str)


def test_analyze_response_contains_analysis_id(
    openai_client: httpx.Client, minimal_ticket_json: dict
):
    """POST /analyze response must include `analysis_id` — the log row PK."""
    body = openai_client.post(ANALYZE_URL, json=minimal_ticket_json).json()
    assert "analysis_id" in body, "Missing analysis_id — analysis not saved to log"
    assert isinstance(body["analysis_id"], int)
    assert body["analysis_id"] > 0


def test_analyze_dominant_cluster_is_dict_or_null(
    openai_client: httpx.Client, minimal_ticket_json: dict
):
    """POST /analyze `dominant_cluster` must be a dict or null — never a raw DB object."""
    body = openai_client.post(ANALYZE_URL, json=minimal_ticket_json).json()
    dc = body.get("dominant_cluster")
    if dc is not None:
        assert isinstance(dc, dict)


# ===========================================================================
# SEC-003 — embedding_text must NOT be in the response
# ===========================================================================

def test_analyze_does_not_expose_embedding_text_in_response(
    openai_client: httpx.Client, minimal_ticket_json: dict
):
    """
    SEC-003: POST /analyze must NOT return embedding_text in the top-level response.
    embedding_text is an internal concatenation that may contain PII / sensitive data.
    """
    body = openai_client.post(ANALYZE_URL, json=minimal_ticket_json).json()
    assert "embedding_text" not in body, (
        "SEC-003 regression: embedding_text exposed in /analyze response"
    )


def test_analyze_does_not_expose_embedding_vector_in_response(
    openai_client: httpx.Client, minimal_ticket_json: dict
):
    """POST /analyze must not return the raw embedding float array."""
    body = openai_client.post(ANALYZE_URL, json=minimal_ticket_json).json()
    assert "embedding" not in body, (
        "Raw embedding vector should not appear in /analyze response"
    )


# ===========================================================================
# SEC-014 — work_notes must NOT appear in similar_incidents
# ===========================================================================

def test_analyze_similar_incidents_do_not_contain_work_notes(
    openai_client: httpx.Client, minimal_ticket_json: dict
):
    """
    SEC-014: similar_incidents items in /analyze response must not include work_notes.
    work_notes can contain PII (agent names, customer details, internal communications).
    """
    body = openai_client.post(ANALYZE_URL, json=minimal_ticket_json).json()
    for inc in body.get("similar_incidents", []):
        assert "work_notes" not in inc, (
            f"SEC-014 regression: work_notes exposed in similar_incidents for "
            f"incident {inc.get('incident_number', 'UNKNOWN')}"
        )


def test_analyze_similar_incidents_do_not_contain_embedding_text(
    openai_client: httpx.Client, minimal_ticket_json: dict
):
    """similar_incidents items must not expose the internal embedding_text field."""
    body = openai_client.post(ANALYZE_URL, json=minimal_ticket_json).json()
    for inc in body.get("similar_incidents", []):
        assert "embedding_text" not in inc, (
            "SEC-003 regression: embedding_text found in a similar_incident item"
        )


def test_analyze_similar_incidents_items_have_expected_safe_fields(
    openai_client: httpx.Client, minimal_ticket_json: dict
):
    """similar_incidents items must expose the expected safe display fields."""
    body = openai_client.post(ANALYZE_URL, json=minimal_ticket_json).json()
    incidents = body.get("similar_incidents", [])
    if not incidents:
        pytest.skip("No similar incidents returned — cannot verify field shape")

    safe_fields = {"incident_number", "short_description", "similarity_score"}
    for inc in incidents:
        missing = safe_fields - inc.keys()
        assert not missing, (
            f"similar_incident item missing expected fields: {missing}"
        )


# ===========================================================================
# POST /analyze — edge cases
# ===========================================================================

def test_analyze_with_empty_description_still_returns_200(
    openai_client: httpx.Client,
):
    """
    POST /analyze with an empty Description field should still return 200 —
    short_description alone is enough to build embedding_text.
    """
    payload = {
        "ticket_json": {
            "pdf_fields": {
                "Short description": "Vision order not syncing",
                "Description": "",
            },
            "incident_section": {},
            "resolution_information_section": {},
        }
    }
    response = openai_client.post(ANALYZE_URL, json=payload)
    assert response.status_code == 200


def test_analyze_with_short_description_under_5_chars_handled_gracefully(
    openai_client: httpx.Client,
):
    """
    POST /analyze with a very short short_description (< 5 chars) must not
    crash the server — it should return 400 (no usable text) or 200 with low confidence.
    Returning 500 is NOT acceptable.
    """
    payload = {
        "ticket_json": {
            "pdf_fields": {
                "Short description": "err",
                "Description": "",
            },
            "incident_section": {},
            "resolution_information_section": {},
        }
    }
    response = openai_client.post(ANALYZE_URL, json=payload)
    # The server must respond, not crash (500 is unacceptable)
    assert response.status_code in (200, 400), (
        f"Short description caused unexpected status {response.status_code}: {response.text[:200]}"
    )


def test_analyze_with_completely_empty_ticket_json_returns_400(
    openai_client: httpx.Client,
):
    """
    POST /analyze with an empty ticket_json dict returns 400 because
    build_embedding_text produces an empty string with no usable fields.
    """
    payload = {"ticket_json": {}}
    response = openai_client.post(ANALYZE_URL, json=payload)
    # Expect 400: "No usable text found in ticket JSON"
    assert response.status_code == 400, (
        f"Expected 400 for empty ticket_json, got {response.status_code}"
    )


def test_analyze_missing_ticket_json_field_returns_422(
    openai_client: httpx.Client,
):
    """POST /analyze with no `ticket_json` key returns 422 (Pydantic validation)."""
    response = openai_client.post(ANALYZE_URL, json={"wrong_key": {}})
    assert response.status_code == 422


def test_analyze_limit_and_threshold_parameters_accepted(
    openai_client: httpx.Client, minimal_ticket_json: dict
):
    """POST /analyze accepts optional `limit` and `threshold` parameters."""
    payload = dict(minimal_ticket_json)
    payload["limit"] = 5
    payload["threshold"] = 0.50
    response = openai_client.post(ANALYZE_URL, json=payload)
    assert response.status_code == 200
    body = response.json()
    # match_count should respect the limit (cannot exceed it)
    assert body["match_count"] <= 5


# ===========================================================================
# POST /analyze/text — plain text endpoint
# ===========================================================================

def test_analyze_text_with_valid_text_returns_200(openai_client: httpx.Client):
    """POST /analyze/text with a descriptive text string must return HTTP 200."""
    payload = {"text": "GK POS terminal not processing payment at store checkout"}
    response = openai_client.post(ANALYZE_TEXT_URL, json=payload)
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text[:300]}"
    )


def test_analyze_text_response_shape_matches_analyze_endpoint(openai_client: httpx.Client):
    """POST /analyze/text wraps into ticket_json and delegates — response shape must match /analyze."""
    payload = {"text": "Vision order not processing after final close"}
    body = openai_client.post(ANALYZE_TEXT_URL, json=payload).json()
    for field in ("confidence_score", "similar_incidents", "focused_playbook", "analysis_id"):
        assert field in body, f"/analyze/text response missing field: {field}"


def test_analyze_text_does_not_expose_embedding_text(openai_client: httpx.Client):
    """SEC-003: POST /analyze/text must not return embedding_text."""
    body = openai_client.post(
        ANALYZE_TEXT_URL, json={"text": "POS finalize error on checkout"}
    ).json()
    assert "embedding_text" not in body


def test_analyze_text_similar_incidents_do_not_contain_work_notes(openai_client: httpx.Client):
    """SEC-014: POST /analyze/text similar_incidents must not include work_notes."""
    body = openai_client.post(
        ANALYZE_TEXT_URL, json={"text": "WE19 IDoc not processing"}
    ).json()
    for inc in body.get("similar_incidents", []):
        assert "work_notes" not in inc, (
            "SEC-014 regression: work_notes in similar_incidents from /analyze/text"
        )


def test_analyze_text_missing_text_field_returns_422(openai_client: httpx.Client):
    """POST /analyze/text with no `text` key must return 422 (Pydantic validation)."""
    response = openai_client.post(ANALYZE_TEXT_URL, json={"wrong": "field"})
    assert response.status_code == 422


# ===========================================================================
# POST /parse-pdf — file upload endpoint
# ===========================================================================

def test_parse_pdf_with_valid_pdf_bytes_returns_200(
    client: httpx.Client, minimal_pdf_bytes: bytes
):
    """POST /parse-pdf with a valid minimal PDF must return HTTP 200."""
    response = client.post(
        PARSE_PDF_URL,
        files={"file": ("test.pdf", minimal_pdf_bytes, "application/pdf")},
    )
    # 200 means the PDF was accepted and parsed (even if extraction returned few fields)
    # 400 is acceptable if the PDF has no text layers — what's NOT acceptable is 500.
    assert response.status_code in (200, 400), (
        f"Unexpected status {response.status_code}: {response.text[:200]}"
    )
    assert response.status_code != 500


def test_parse_pdf_rejects_non_pdf_file_extension(client: httpx.Client):
    """POST /parse-pdf with a .txt file extension must return HTTP 400."""
    response = client.post(
        PARSE_PDF_URL,
        files={"file": ("incident.txt", b"some text content", "text/plain")},
    )
    assert response.status_code == 400, (
        f"Expected 400 for non-PDF extension, got {response.status_code}"
    )


def test_parse_pdf_rejects_wrong_mime_type(client: httpx.Client):
    """POST /parse-pdf with application/octet-stream MIME type must return HTTP 400."""
    # The file is named .pdf but has the wrong Content-Type
    response = client.post(
        PARSE_PDF_URL,
        files={"file": ("fake.pdf", b"%PDF-1.4 some content", "application/octet-stream")},
    )
    assert response.status_code == 400, (
        f"Expected 400 for wrong MIME type, got {response.status_code}"
    )


def test_parse_pdf_rejects_file_without_pdf_magic_bytes(client: httpx.Client):
    """POST /parse-pdf with application/pdf MIME but no %PDF- magic bytes must return 400."""
    fake_pdf = b"This is not a real PDF file at all."
    response = client.post(
        PARSE_PDF_URL,
        files={"file": ("fake.pdf", fake_pdf, "application/pdf")},
    )
    assert response.status_code == 400


def test_parse_pdf_rejects_oversized_file(client: httpx.Client, minimal_pdf_bytes: bytes):
    """
    POST /parse-pdf with a file exceeding MAX_PDF_SIZE (10 MB) must return HTTP 400.
    We simulate an oversized file by padding beyond the 10 MB limit.
    """
    # 10 MB + 1 byte
    oversized = minimal_pdf_bytes + b"\x00" * (10 * 1024 * 1024 + 1)
    response = client.post(
        PARSE_PDF_URL,
        files={"file": ("big.pdf", oversized, "application/pdf")},
        # Use a longer timeout since we're uploading 10 MB
        timeout=30.0,
    )
    assert response.status_code == 400, (
        f"Expected 400 for oversized file, got {response.status_code}"
    )
    assert "too large" in response.text.lower() or "maximum" in response.text.lower()


def test_parse_pdf_rejects_file_too_small(client: httpx.Client):
    """POST /parse-pdf with fewer than 100 bytes must return HTTP 400 (too small)."""
    tiny = b"%PDF-1.4 tiny"
    response = client.post(
        PARSE_PDF_URL,
        files={"file": ("tiny.pdf", tiny, "application/pdf")},
    )
    assert response.status_code == 400


def test_parse_pdf_returns_dict_on_success(client: httpx.Client, minimal_pdf_bytes: bytes):
    """POST /parse-pdf on a parseable PDF must return a JSON object (dict), not a list."""
    response = client.post(
        PARSE_PDF_URL,
        files={"file": ("test.pdf", minimal_pdf_bytes, "application/pdf")},
    )
    if response.status_code == 200:
        body = response.json()
        assert isinstance(body, dict), f"parse-pdf should return a dict, got {type(body)}"
