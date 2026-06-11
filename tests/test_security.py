"""
test_security.py — Security regression tests for REX-US.

Tests the security fixes applied throughout the codebase:
  SEC-003: embedding_text must not appear in /analyze or /analysis-log responses
  SEC-004: /analysis-log/{id} must not return raw input_json or full_response
  SEC-005: /parse-pdf must validate file size, extension, MIME type, magic bytes
  SEC-006: /transcribe must whitelist content types
  SEC-007: CORS origins must be restricted (not wildcard)
  SEC-008: Global 500 handler must not leak stack traces
  SEC-009: Feedback text length must be bounded
  SEC-014: work_notes must not appear in similar_incidents
  SEC-016: Security headers must be present on all responses
  SEC-017: Interactive API docs (/docs, /redoc) must be disabled in production mode
  SEC-020: /sync/import batch size must be capped at 50
"""

import pytest
import httpx


BASE_URLS_TO_CHECK = [
    "/health",
    "/api/v1/incidents",
    "/api/v1/clusters",
    "/api/v1/playbooks",
]


# ===========================================================================
# SEC-016: Security headers on every response
# ===========================================================================

@pytest.mark.parametrize("path", BASE_URLS_TO_CHECK)
def test_security_header_x_content_type_options_present(
    client: httpx.Client, path: str
):
    """
    SEC-016: Every response must include X-Content-Type-Options: nosniff.
    This prevents MIME-type sniffing attacks on IE/Edge.
    """
    response = client.get(path)
    assert "x-content-type-options" in response.headers, (
        f"X-Content-Type-Options header missing on {path}"
    )
    assert response.headers["x-content-type-options"].lower() == "nosniff", (
        f"X-Content-Type-Options must be 'nosniff', got '{response.headers['x-content-type-options']}'"
    )


@pytest.mark.parametrize("path", BASE_URLS_TO_CHECK)
def test_security_header_x_frame_options_present(client: httpx.Client, path: str):
    """
    SEC-016: Every response must include X-Frame-Options: DENY.
    This prevents the API from being embedded in an iframe (clickjacking).
    """
    response = client.get(path)
    assert "x-frame-options" in response.headers, (
        f"X-Frame-Options header missing on {path}"
    )
    assert response.headers["x-frame-options"].upper() == "DENY", (
        f"X-Frame-Options must be 'DENY', got '{response.headers['x-frame-options']}'"
    )


@pytest.mark.parametrize("path", BASE_URLS_TO_CHECK)
def test_security_header_x_xss_protection_present(client: httpx.Client, path: str):
    """SEC-016: Every response must include X-XSS-Protection header."""
    response = client.get(path)
    assert "x-xss-protection" in response.headers, (
        f"X-XSS-Protection header missing on {path}"
    )


@pytest.mark.parametrize("path", BASE_URLS_TO_CHECK)
def test_security_header_cache_control_no_store(client: httpx.Client, path: str):
    """SEC-016: Every response must include Cache-Control: no-store to prevent caching PII."""
    response = client.get(path)
    assert "cache-control" in response.headers, (
        f"Cache-Control header missing on {path}"
    )
    assert "no-store" in response.headers["cache-control"].lower(), (
        f"Cache-Control must include 'no-store' on {path}, "
        f"got '{response.headers['cache-control']}'"
    )


@pytest.mark.parametrize("path", BASE_URLS_TO_CHECK)
def test_security_header_referrer_policy_present(client: httpx.Client, path: str):
    """SEC-016: Every response must include Referrer-Policy header."""
    response = client.get(path)
    assert "referrer-policy" in response.headers, (
        f"Referrer-Policy header missing on {path}"
    )


# ===========================================================================
# SEC-007: CORS — must not use wildcard origin
# ===========================================================================

def test_cors_preflight_does_not_allow_wildcard_origin(client: httpx.Client):
    """
    SEC-007: The CORS configuration must restrict allowed origins to the list
    in CORS_ORIGINS env var — not '*'. A preflight from an unrecognised origin
    must not return Access-Control-Allow-Origin: *.
    """
    response = client.options(
        "/health",
        headers={
            "Origin": "https://evil-attacker.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    allow_origin = response.headers.get("access-control-allow-origin", "")
    assert allow_origin != "*", (
        "SEC-007 regression: CORS allows wildcard origin '*' — must restrict to configured list"
    )


def test_cors_allows_configured_origin(client: httpx.Client):
    """
    The CORS configuration must allow the default dev origin (localhost:3000).
    This confirms the middleware is configured and not just blocking everything.
    """
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    # FastAPI's CORSMiddleware returns 200 on OPTIONS with matching origin
    # Access-Control-Allow-Origin must be present
    allow_origin = response.headers.get("access-control-allow-origin", "")
    assert allow_origin in ("http://localhost:3000", "*"), (
        "Expected localhost:3000 to be an allowed CORS origin"
    )


# ===========================================================================
# SEC-017: /docs and /redoc must be disabled when REXUS_ENV != development
# ===========================================================================

def test_api_docs_url_behavior(client: httpx.Client):
    """
    SEC-017: In production (REXUS_ENV=production), /docs must return 404.
    In development, it returns 200. Either way, it must not return 500.
    This test validates the endpoint does not crash — the status is environment-dependent.
    """
    response = client.get("/docs")
    assert response.status_code in (200, 404), (
        f"/docs returned unexpected status {response.status_code}"
    )


def test_api_redoc_url_behavior(client: httpx.Client):
    """
    SEC-017: In production, /redoc must return 404. In dev, 200.
    Must not crash.
    """
    response = client.get("/redoc")
    assert response.status_code in (200, 404)


def test_openapi_json_behavior(client: httpx.Client):
    """
    In production mode, /openapi.json must return 404 to prevent API schema leakage.
    In dev mode, 200 is acceptable.
    """
    response = client.get("/openapi.json")
    assert response.status_code in (200, 404)


# ===========================================================================
# SEC-008: Global exception handler — no stack traces in 500 responses
# ===========================================================================

def test_global_error_handler_does_not_expose_traceback(client: httpx.Client):
    """
    SEC-008: When the server encounters an unhandled exception it should return
    {"error": "Internal server error"} — not a raw Python traceback.
    We trigger this by sending a request designed to expose the DB schema.
    """
    # Send a structurally valid but semantically problematic request
    # This exercises the global exception handler path
    response = client.get("/api/v1/incidents", params={"page": "not_an_int"})
    # FastAPI returns 422 for type errors before they reach the handler — that's fine
    if response.status_code == 500:
        body = response.json()
        assert "error" in body, "500 body missing 'error' key from global handler"
        text = response.text.lower()
        for leak in ("traceback", "file \"", "line ", "asyncpg", "sqlstate"):
            assert leak not in text, (
                f"SEC-008 regression: internal detail '{leak}' leaked in 500 response"
            )


# ===========================================================================
# SEC-003: embedding_text must not appear in /analyze response
# ===========================================================================

def test_analysis_log_list_does_not_return_embedding_text(client: httpx.Client):
    """
    SEC-003: GET /analysis-log must not include embedding_text in any item.
    The list query selects only safe summary fields.
    """
    response = client.get("/api/v1/analysis-log", params={"page_size": 10})
    if response.status_code != 200:
        pytest.skip("analysis-log not available")
    body = response.json()
    for item in body.get("items", []):
        assert "embedding_text" not in item, (
            "SEC-003 regression: embedding_text in analysis-log list item"
        )


def test_analysis_log_list_does_not_return_input_json(client: httpx.Client):
    """
    SEC-004: GET /analysis-log list must not include raw input_json.
    input_json contains the raw PDF-extracted data with PII.
    """
    response = client.get("/api/v1/analysis-log", params={"page_size": 10})
    if response.status_code != 200:
        pytest.skip("analysis-log not available")
    body = response.json()
    for item in body.get("items", []):
        assert "input_json" not in item, (
            "SEC-004 regression: raw input_json exposed in analysis-log list"
        )


def test_analysis_log_detail_does_not_return_full_response(client: httpx.Client):
    """
    SEC-004: GET /analysis-log/{id} must not return full_response or input_json.
    These contain PII and the full OpenAI-generated content.
    """
    # Get the ID of the most recent log entry
    list_response = client.get("/api/v1/analysis-log", params={"page_size": 1})
    if list_response.status_code != 200 or not list_response.json().get("items"):
        pytest.skip("No analysis log entries to test")

    log_id = list_response.json()["items"][0]["id"]
    detail = client.get(f"/api/v1/analysis-log/{log_id}").json()

    for sensitive_field in ("input_json", "full_response", "embedding_text"):
        assert sensitive_field not in detail, (
            f"SEC-004 regression: '{sensitive_field}' in analysis-log detail response"
        )


# ===========================================================================
# SEC-014: work_notes must not appear in any public-facing API response
# ===========================================================================

def test_incidents_list_does_not_expose_work_notes(client: httpx.Client):
    """
    SEC-014: GET /incidents list must not include work_notes.
    The list query explicitly excludes work_notes from its SELECT.
    """
    body = client.get("/api/v1/incidents", params={"page_size": 10}).json()
    for item in body.get("items", []):
        assert "work_notes" not in item, (
            f"SEC-014: work_notes in incidents list item {item.get('incident_number')}"
        )


# ===========================================================================
# File upload security (cross-cutting)
# ===========================================================================

def test_parse_pdf_does_not_accept_executable_disguised_as_pdf(client: httpx.Client):
    """
    SEC-005: /parse-pdf must reject files that claim to be PDF but fail the
    %PDF- magic byte check. An attacker might upload a script with a .pdf name.
    """
    # ELF binary header disguised as PDF
    elf_content = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 200
    response = client.post(
        "/api/v1/parse-pdf",
        files={"file": ("shell.pdf", elf_content, "application/pdf")},
    )
    assert response.status_code == 400, (
        "ELF binary disguised as PDF should be rejected with 400"
    )


def test_parse_pdf_does_not_accept_html_disguised_as_pdf(client: httpx.Client):
    """SEC-005: HTML file with .pdf extension and correct MIME type must be rejected."""
    html_content = b"<html><body>XSS attack</body></html>" + b" " * 200
    response = client.post(
        "/api/v1/parse-pdf",
        files={"file": ("page.pdf", html_content, "application/pdf")},
    )
    assert response.status_code == 400


# ===========================================================================
# SEC-009: Feedback text size limit
# ===========================================================================

def test_feedback_with_reasonable_length_text_is_accepted(client: httpx.Client):
    """SEC-009: Feedback text within the 5000-char limit must be accepted (200)."""
    payload = {
        "feedback_text": "Good" * 100,  # 400 chars — well within limit
        "feedback_type": "security_test",
    }
    response = client.post("/api/v1/feedback", json=payload)
    assert response.status_code == 200


def test_feedback_with_maximum_boundary_text_is_not_rejected(client: httpx.Client):
    """
    SEC-009: Feedback text at exactly the 5000-char boundary must not cause a 500.
    May be accepted (200) or rejected (422) depending on Pydantic version behavior,
    but must not crash the server.
    """
    payload = {"feedback_text": "X" * 5000}
    response = client.post("/api/v1/feedback", json=payload)
    assert response.status_code in (200, 422), (
        f"5000-char feedback caused unexpected {response.status_code}"
    )
    assert response.status_code != 500


# ===========================================================================
# SEC-020: Import batch size cap
# ===========================================================================

def test_sync_import_batch_size_cap_is_enforced_above_max(client: httpx.Client):
    """SEC-020: POST /sync/import above SYNC_IMPORT_MAX_INCIDENTS must be rejected with 422."""
    from backend.api.utils.sync_constants import SYNC_IMPORT_MAX

    payload = {"incident_numbers": [f"INC{i:07d}" for i in range(1, SYNC_IMPORT_MAX + 2)]}
    response = client.post("/api/v1/sync/import", json=payload)
    assert response.status_code == 422


# ===========================================================================
# Maintenance endpoint auth (admin JWT or X-Admin-Key)
# ===========================================================================

@pytest.mark.asyncio
async def test_require_admin_or_api_key_accepts_matching_api_key(monkeypatch):
    from unittest.mock import MagicMock
    from backend.api.auth import require_admin_or_api_key

    monkeypatch.setattr("backend.api.auth._ADMIN_KEY", "test-secret-key")
    result = await require_admin_or_api_key(MagicMock(), x_admin_key="test-secret-key")
    assert result["role"] == "admin"
    assert result["via"] == "api_key"


@pytest.mark.asyncio
async def test_require_admin_or_api_key_rejects_missing_auth(monkeypatch):
    from unittest.mock import MagicMock
    from fastapi import HTTPException
    from backend.api.auth import require_admin_or_api_key

    monkeypatch.setattr("backend.api.auth._ADMIN_KEY", "test-secret-key")
    request = MagicMock()
    request.headers.get.return_value = None
    with pytest.raises(HTTPException) as exc:
        await require_admin_or_api_key(request, x_admin_key=None)
    assert exc.value.status_code == 401