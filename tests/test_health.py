"""
test_health.py — Tests for GET /health

Verifies:
  - Endpoint is reachable and returns HTTP 200
  - Response body contains the three required fields: status, database, incidents_count
  - `status` value is the string "healthy"
  - `database` value is the string "connected", confirming a live DB connection
  - `incidents_count` is a non-negative integer (the pg_class estimated row count)
"""

import pytest
import httpx


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------

def test_health_returns_http_200(client: httpx.Client):
    """GET /health must return HTTP 200 when the backend and database are up."""
    response = client.get("/health")
    assert response.status_code == 200, (
        f"Expected 200 but got {response.status_code}. "
        "Is the backend running at the configured BASE_URL?"
    )


def test_health_response_is_json(client: httpx.Client):
    """GET /health response body must be valid JSON."""
    response = client.get("/health")
    # httpx raises JSONDecodeError if the body is not JSON
    body = response.json()
    assert isinstance(body, dict), f"Expected a JSON object, got: {type(body)}"


def test_health_contains_required_fields(client: httpx.Client):
    """GET /health must include status, database, and incidents_count fields."""
    body = client.get("/health").json()
    required_fields = {"status", "database", "incidents_count"}
    missing = required_fields - body.keys()
    assert not missing, f"Health response is missing fields: {missing}"


def test_health_status_is_healthy(client: httpx.Client):
    """GET /health field `status` must equal 'healthy'."""
    body = client.get("/health").json()
    assert body["status"] == "healthy", (
        f"Expected status='healthy', got '{body.get('status')}'"
    )


def test_health_database_is_connected(client: httpx.Client):
    """GET /health field `database` must equal 'connected', confirming a live pool."""
    body = client.get("/health").json()
    assert body["database"] == "connected", (
        f"Expected database='connected', got '{body.get('database')}'. "
        "Check DATABASE_URL in .env."
    )


def test_health_incidents_count_is_non_negative_integer(client: httpx.Client):
    """GET /health field `incidents_count` must be an integer >= 0 (pg_class estimate)."""
    body = client.get("/health").json()
    count = body.get("incidents_count")
    assert isinstance(count, int), (
        f"incidents_count must be an int, got {type(count)}: {count}"
    )
    assert count >= 0, f"incidents_count must be >= 0, got {count}"


def test_health_does_not_expose_connection_string(client: httpx.Client):
    """GET /health must not leak the DATABASE_URL or any credentials in the response."""
    text = client.get("/health").text
    # These substrings would indicate credential leakage
    for sensitive in ("postgresql://", "password", "secret", "@localhost"):
        assert sensitive not in text.lower(), (
            f"Potential credential leak: found '{sensitive}' in /health response"
        )
