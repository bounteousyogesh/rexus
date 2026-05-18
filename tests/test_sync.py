"""
test_sync.py — Tests for GET/POST /api/v1/sync/*

Endpoints under test:
  GET  /api/v1/sync/status   — DB vs ServiceNow snapshot
  GET  /api/v1/sync/delta    — incidents in SN not yet in our DB
  POST /api/v1/sync/import   — import a batch of incidents from SN

Design note:
  - /sync/status and /sync/delta contact ServiceNow, so they may return partial
    data if SN credentials are not configured. We assert the response structure
    is always correct even when SN is unreachable (the DB section must still work).
  - /sync/import tests focus on validation (bad input rejection) rather than
    full end-to-end import, since that requires valid SN incident numbers.
"""

import pytest
import httpx

from backend.api.routers.sync import _SYNC_IMPORT_MAX


SYNC_STATUS_URL = "/api/v1/sync/status"
SYNC_DELTA_URL  = "/api/v1/sync/delta"
SYNC_IMPORT_URL = "/api/v1/sync/import"


# ===========================================================================
# GET /sync/status
# ===========================================================================

def test_sync_status_returns_200(client: httpx.Client):
    """GET /sync/status must return HTTP 200."""
    response = client.get(SYNC_STATUS_URL)
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text[:300]}"
    )


def test_sync_status_contains_database_section(client: httpx.Client):
    """GET /sync/status response must include a `database` key."""
    body = client.get(SYNC_STATUS_URL).json()
    assert "database" in body, "sync/status response missing 'database' key"


def test_sync_status_contains_servicenow_section(client: httpx.Client):
    """GET /sync/status response must include a `servicenow` key."""
    body = client.get(SYNC_STATUS_URL).json()
    assert "servicenow" in body, "sync/status response missing 'servicenow' key"


def test_sync_status_database_section_has_required_fields(client: httpx.Client):
    """GET /sync/status `database` section must include total_incidents, embedded, latest_incident_date."""
    body = client.get(SYNC_STATUS_URL).json()
    db = body["database"]
    for field in ("total_incidents", "embedded", "latest_incident_date"):
        assert field in db, f"database section missing field '{field}'"


def test_sync_status_database_total_incidents_is_non_negative_integer(client: httpx.Client):
    """GET /sync/status database.total_incidents must be int >= 0."""
    body = client.get(SYNC_STATUS_URL).json()
    total = body["database"]["total_incidents"]
    assert isinstance(total, int), f"total_incidents must be int, got {type(total)}"
    assert total >= 0


def test_sync_status_database_embedded_is_non_negative_integer(client: httpx.Client):
    """GET /sync/status database.embedded count must be int >= 0."""
    body = client.get(SYNC_STATUS_URL).json()
    embedded = body["database"]["embedded"]
    assert isinstance(embedded, int)
    assert embedded >= 0


def test_sync_status_embedded_not_greater_than_total(client: httpx.Client):
    """GET /sync/status embedded count cannot exceed total_incidents."""
    body = client.get(SYNC_STATUS_URL).json()
    db = body["database"]
    assert db["embedded"] <= db["total_incidents"], (
        f"embedded={db['embedded']} > total_incidents={db['total_incidents']} — data inconsistency"
    )


def test_sync_status_servicenow_section_has_closed_incidents_key(client: httpx.Client):
    """
    GET /sync/status `servicenow` section must have `closed_incidents` key.
    The value may be an int or an error string if SN is not configured.
    """
    body = client.get(SYNC_STATUS_URL).json()
    sn = body["servicenow"]
    assert "closed_incidents" in sn, "servicenow section missing 'closed_incidents'"


def test_sync_status_does_not_expose_credentials(client: httpx.Client):
    """GET /sync/status must not return SN credentials or database passwords."""
    text = client.get(SYNC_STATUS_URL).text.lower()
    for sensitive in ("client_secret", "password", "bearer", "postgresql://"):
        assert sensitive not in text, (
            f"Potential credential leak in sync/status: '{sensitive}'"
        )


# ===========================================================================
# GET /sync/delta
# ===========================================================================

def test_sync_delta_returns_200_or_500_on_sn_auth_failure(client: httpx.Client):
    """
    GET /sync/delta contacts ServiceNow. If SN is not configured it may return
    500 (caught by global exception handler as 'Internal server error').
    200 means SN is reachable and responded. Both are acceptable in CI.
    """
    response = client.get(SYNC_DELTA_URL, timeout=20.0)
    # A 500 wrapped by the global handler is acceptable when SN isn't configured.
    # A raw uncaught 500 would expose stack traces — see separate assertion below.
    assert response.status_code in (200, 500), (
        f"Unexpected status: {response.status_code}"
    )


def test_sync_delta_on_success_contains_required_fields(client: httpx.Client):
    """GET /sync/delta on success must return total_delta, by_month, by_week."""
    response = client.get(SYNC_DELTA_URL, timeout=20.0)
    if response.status_code != 200:
        pytest.skip("ServiceNow not configured — skipping delta structure test")
    body = response.json()
    for field in ("total_delta", "by_month", "by_week"):
        assert field in body, f"sync/delta response missing field '{field}'"


def test_sync_delta_total_delta_is_non_negative(client: httpx.Client):
    """GET /sync/delta total_delta must be int >= 0."""
    response = client.get(SYNC_DELTA_URL, timeout=20.0)
    if response.status_code != 200:
        pytest.skip("ServiceNow not configured")
    body = response.json()
    assert isinstance(body["total_delta"], int)
    assert body["total_delta"] >= 0


def test_sync_delta_by_month_is_a_list(client: httpx.Client):
    """GET /sync/delta `by_month` must be a list."""
    response = client.get(SYNC_DELTA_URL, timeout=20.0)
    if response.status_code != 200:
        pytest.skip("ServiceNow not configured")
    body = response.json()
    assert isinstance(body["by_month"], list)


def test_sync_delta_by_week_is_a_list(client: httpx.Client):
    """GET /sync/delta `by_week` must be a list."""
    response = client.get(SYNC_DELTA_URL, timeout=20.0)
    if response.status_code != 200:
        pytest.skip("ServiceNow not configured")
    body = response.json()
    assert isinstance(body["by_week"], list)


def test_sync_delta_by_month_items_have_expected_fields(client: httpx.Client):
    """Each by_month entry must include month, count, and incidents."""
    response = client.get(SYNC_DELTA_URL, timeout=20.0)
    if response.status_code != 200:
        pytest.skip("ServiceNow not configured")
    body = response.json()
    for entry in body["by_month"]:
        for field in ("month", "count", "incidents"):
            assert field in entry, f"by_month entry missing field '{field}'"


def test_sync_delta_500_response_uses_global_error_handler(client: httpx.Client):
    """
    If SN returns 500, the global exception handler must return
    {"error": "Internal server error"} — NOT a raw traceback.
    """
    response = client.get(SYNC_DELTA_URL, timeout=20.0)
    if response.status_code == 500:
        body = response.json()
        assert "error" in body, "500 response missing 'error' key from global handler"
        assert "traceback" not in response.text.lower()
        assert "asyncpg" not in response.text.lower()


# ===========================================================================
# POST /sync/import — validation tests
# ===========================================================================

def test_sync_import_rejects_empty_incident_list(client: httpx.Client):
    """POST /sync/import with empty incident_numbers list must return 400."""
    response = client.post(SYNC_IMPORT_URL, json={"incident_numbers": []})
    assert response.status_code == 400, (
        f"Expected 400 for empty incident list, got {response.status_code}"
    )


def test_sync_import_rejects_more_than_max_incidents(client: httpx.Client):
    """
    POST /sync/import with > SYNC_IMPORT_MAX_INCIDENTS must return 422.
    SEC-020: ImportRequest enforces configurable max per batch.
    """
    too_many = [f"INC{i:07d}" for i in range(1, _SYNC_IMPORT_MAX + 2)]
    response = client.post(SYNC_IMPORT_URL, json={"incident_numbers": too_many})
    assert response.status_code == 422, (
        f"Expected 422 for >{_SYNC_IMPORT_MAX} incidents, got {response.status_code}"
    )
    body = response.json()
    detail_text = str(body).lower()
    assert "max" in detail_text or "limit" in detail_text or str(_SYNC_IMPORT_MAX) in detail_text, (
        f"422 error should mention the import limit, got: {body}"
    )


def test_sync_import_small_batch_is_not_rejected_by_batch_size(client: httpx.Client):
    """POST /sync/import with a small batch must not fail 422 for batch-size validation."""
    response = client.post(
        SYNC_IMPORT_URL,
        json={"incident_numbers": ["INC0000001"]},
        timeout=30.0,
    )
    if response.status_code == 422:
        detail = str(response.json()).lower()
        assert "max_length" not in detail and "too_long" not in detail, (
            "Small batch was incorrectly rejected by the batch-size guard"
        )


def test_sync_import_missing_incident_numbers_field_returns_422(client: httpx.Client):
    """POST /sync/import with no `incident_numbers` key must return 422 (Pydantic)."""
    response = client.post(SYNC_IMPORT_URL, json={"wrong_field": ["INC0000001"]})
    assert response.status_code == 422


def test_sync_import_with_valid_format_numbers_returns_result_list(client: httpx.Client):
    """
    POST /sync/import with properly formatted but non-existent INC numbers must
    return 200 with a `results` list where each entry has incident + status.
    (status will be 'not_found' or 'error' since SN may not have these incidents.)
    """
    payload = {"incident_numbers": ["INC0000001", "INC0000002"]}
    response = client.post(SYNC_IMPORT_URL, json=payload, timeout=30.0)
    # If SN is configured: 200 with results; if not: 500 from global handler
    if response.status_code == 500:
        pytest.skip("ServiceNow not configured — import returned 500")
    assert response.status_code == 200
    body = response.json()
    assert "results" in body, "sync/import response missing 'results' list"
    assert isinstance(body["results"], list)
    assert len(body["results"]) == 2


def test_sync_import_response_has_imported_and_failed_counts(client: httpx.Client):
    """POST /sync/import response must include imported, failed, skipped counts."""
    payload = {"incident_numbers": ["INC0000001"]}
    response = client.post(SYNC_IMPORT_URL, json=payload, timeout=30.0)
    if response.status_code == 500:
        pytest.skip("ServiceNow not configured")
    body = response.json()
    for field in ("imported", "failed", "skipped", "results"):
        assert field in body, f"sync/import response missing field '{field}'"
