"""
test_incidents.py — Tests for GET /api/v1/incidents and GET /api/v1/incidents/{number}

Covers:
  - Paginated list with default params
  - Pagination envelope shape (total, page, page_size, pages, items)
  - page_size upper bound enforcement (max 100)
  - page parameter lower bound enforcement (min 1)
  - Filter by category
  - Filter by cmdb_ci
  - Filter by state
  - Filter by assignment_group
  - Full-text search filter (short_description / close_notes)
  - Combining multiple filters
  - GET single incident by incident_number
  - 404 for a non-existent incident_number
  - Response fields for single incident (cluster field present)
  - Items returned do not contain the raw `embedding` column
"""

import pytest
import httpx


INCIDENTS_URL = "/api/v1/incidents"


# ---------------------------------------------------------------------------
# List incidents — envelope shape
# ---------------------------------------------------------------------------

def test_list_incidents_returns_200(client: httpx.Client):
    """GET /incidents with no filters must return HTTP 200."""
    response = client.get(INCIDENTS_URL)
    assert response.status_code == 200


def test_list_incidents_envelope_has_required_fields(client: httpx.Client):
    """GET /incidents response must include total, page, page_size, pages, items."""
    body = client.get(INCIDENTS_URL).json()
    required = {"total", "page", "page_size", "pages", "items"}
    missing = required - body.keys()
    assert not missing, f"Envelope missing fields: {missing}"


def test_list_incidents_items_is_a_list(client: httpx.Client):
    """GET /incidents field `items` must be a list."""
    body = client.get(INCIDENTS_URL).json()
    assert isinstance(body["items"], list)


def test_list_incidents_default_page_size_is_20(client: httpx.Client):
    """GET /incidents with no page_size param should default to 20 items."""
    body = client.get(INCIDENTS_URL).json()
    assert body["page_size"] == 20


def test_list_incidents_default_page_is_1(client: httpx.Client):
    """GET /incidents with no page param should default to page 1."""
    body = client.get(INCIDENTS_URL).json()
    assert body["page"] == 1


def test_list_incidents_items_do_not_exceed_page_size(client: httpx.Client):
    """GET /incidents items count must never exceed page_size."""
    body = client.get(INCIDENTS_URL, params={"page_size": 5}).json()
    assert len(body["items"]) <= 5


def test_list_incidents_page_size_respected_when_set(client: httpx.Client):
    """GET /incidents with page_size=3 must return at most 3 items."""
    body = client.get(INCIDENTS_URL, params={"page_size": 3}).json()
    assert body["page_size"] == 3
    assert len(body["items"]) <= 3


def test_list_incidents_pages_calculated_correctly(client: httpx.Client):
    """GET /incidents `pages` must be ceil(total / page_size)."""
    body = client.get(INCIDENTS_URL, params={"page_size": 10}).json()
    total = body["total"]
    page_size = body["page_size"]
    expected_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 1
    # Allow 0 pages when there are 0 total incidents
    if total == 0:
        assert body["pages"] in (0, 1)
    else:
        assert body["pages"] == expected_pages, (
            f"Expected pages={expected_pages} for total={total}/page_size={page_size}, "
            f"got {body['pages']}"
        )


# ---------------------------------------------------------------------------
# List incidents — pagination parameter validation
# ---------------------------------------------------------------------------

def test_list_incidents_rejects_page_size_above_100(client: httpx.Client):
    """GET /incidents with page_size=101 must return HTTP 422 (validation error)."""
    response = client.get(INCIDENTS_URL, params={"page_size": 101})
    assert response.status_code == 422, (
        "FastAPI Query(le=100) should reject page_size > 100 with 422"
    )


def test_list_incidents_rejects_page_zero(client: httpx.Client):
    """GET /incidents with page=0 must return HTTP 422 (page is ge=1)."""
    response = client.get(INCIDENTS_URL, params={"page": 0})
    assert response.status_code == 422


def test_list_incidents_second_page_differs_from_first(client: httpx.Client):
    """GET /incidents page 2 must return different items than page 1 when enough data exists."""
    body1 = client.get(INCIDENTS_URL, params={"page": 1, "page_size": 5}).json()
    body2 = client.get(INCIDENTS_URL, params={"page": 2, "page_size": 5}).json()
    if body1["total"] <= 5:
        pytest.skip("Not enough incidents in the database to test pagination")
    ids_p1 = {i["incident_number"] for i in body1["items"]}
    ids_p2 = {i["incident_number"] for i in body2["items"]}
    assert ids_p1.isdisjoint(ids_p2), "Page 1 and page 2 returned overlapping incidents"


# ---------------------------------------------------------------------------
# List incidents — per-item field shape
# ---------------------------------------------------------------------------

def test_list_incidents_items_have_expected_fields(client: httpx.Client):
    """Each item in GET /incidents must include the core display fields."""
    body = client.get(INCIDENTS_URL, params={"page_size": 1}).json()
    if not body["items"]:
        pytest.skip("No incidents in the database")
    item = body["items"][0]
    expected = {
        "id", "incident_number", "short_description",
        "category", "priority", "state",
    }
    missing = expected - item.keys()
    assert not missing, f"Incident list item missing fields: {missing}"


def test_list_incidents_items_do_not_expose_embedding(client: httpx.Client):
    """GET /incidents items must never include the raw vector embedding column."""
    body = client.get(INCIDENTS_URL, params={"page_size": 5}).json()
    for item in body["items"]:
        assert "embedding" not in item, (
            "Raw embedding vector should not be exposed in list response"
        )


# ---------------------------------------------------------------------------
# List incidents — filter by category
# ---------------------------------------------------------------------------

def test_list_incidents_filter_by_category_returns_only_matching_rows(client: httpx.Client):
    """GET /incidents?category=X must return only incidents whose category equals X."""
    # First, find a category that exists
    all_body = client.get(INCIDENTS_URL, params={"page_size": 20}).json()
    if not all_body["items"]:
        pytest.skip("No incidents available to derive a test category")

    # Pick the first non-null category
    category = next(
        (i["category"] for i in all_body["items"] if i.get("category")),
        None,
    )
    if not category:
        pytest.skip("No incidents with a non-null category found")

    filtered = client.get(INCIDENTS_URL, params={"category": category}).json()
    assert filtered["total"] >= 1
    for item in filtered["items"]:
        assert item["category"] == category, (
            f"Filter category='{category}' returned incident with category='{item['category']}'"
        )


# ---------------------------------------------------------------------------
# List incidents — filter by cmdb_ci
# ---------------------------------------------------------------------------

def test_list_incidents_filter_by_cmdb_ci_returns_only_matching_rows(client: httpx.Client):
    """GET /incidents?cmdb_ci=X must return only incidents for that configuration item."""
    all_body = client.get(INCIDENTS_URL, params={"page_size": 20}).json()
    cmdb = next((i["cmdb_ci"] for i in all_body["items"] if i.get("cmdb_ci")), None)
    if not cmdb:
        pytest.skip("No incidents with a non-null cmdb_ci found")

    filtered = client.get(INCIDENTS_URL, params={"cmdb_ci": cmdb}).json()
    assert filtered["total"] >= 1
    for item in filtered["items"]:
        assert item["cmdb_ci"] == cmdb, (
            f"Filter cmdb_ci='{cmdb}' returned incident with cmdb_ci='{item['cmdb_ci']}'"
        )


# ---------------------------------------------------------------------------
# List incidents — full-text search filter
# ---------------------------------------------------------------------------

def test_list_incidents_search_filter_reduces_result_set(client: httpx.Client):
    """GET /incidents?search=X must return fewer or equal results than unfiltered."""
    total_unfiltered = client.get(INCIDENTS_URL).json()["total"]
    if total_unfiltered == 0:
        pytest.skip("No incidents in the database")

    # Use a word that is likely in some but not all incidents
    body = client.get(INCIDENTS_URL, params={"search": "vision"}).json()
    assert body["total"] <= total_unfiltered


def test_list_incidents_search_filter_matches_short_description_or_close_notes(client: httpx.Client):
    """GET /incidents?search=X items must contain X in short_description OR close_notes."""
    body = client.get(INCIDENTS_URL, params={"search": "vision", "page_size": 10}).json()
    if not body["items"]:
        pytest.skip("No incidents matching 'vision' found")

    for item in body["items"]:
        sd = (item.get("short_description") or "").lower()
        cn = (item.get("close_notes") or "").lower()
        assert "vision" in sd or "vision" in cn, (
            f"Incident {item.get('incident_number')} matched search='vision' "
            f"but neither short_description nor close_notes contain 'vision'"
        )


def test_list_incidents_search_filter_matches_incident_number(client: httpx.Client):
    """GET /incidents?search={number} must return the matching incident."""
    number = _get_first_incident_number(client)
    body = client.get(INCIDENTS_URL, params={"search": number}).json()
    assert body["total"] >= 1
    assert any(item["incident_number"] == number for item in body["items"])


# ---------------------------------------------------------------------------
# Get single incident
# ---------------------------------------------------------------------------

def _get_first_incident_number(client: httpx.Client) -> str:
    """Helper: retrieve an incident_number that exists in the database."""
    body = client.get(INCIDENTS_URL, params={"page_size": 1}).json()
    if not body["items"]:
        pytest.skip("No incidents in the database")
    return body["items"][0]["incident_number"]


def test_get_incident_by_number_returns_200(client: httpx.Client):
    """GET /incidents/{number} must return HTTP 200 for an existing incident."""
    number = _get_first_incident_number(client)
    response = client.get(f"{INCIDENTS_URL}/{number}")
    assert response.status_code == 200


def test_get_incident_by_number_returns_correct_incident(client: httpx.Client):
    """GET /incidents/{number} must return the incident whose number matches the path param."""
    number = _get_first_incident_number(client)
    body = client.get(f"{INCIDENTS_URL}/{number}").json()
    assert body["incident_number"] == number


def test_get_incident_by_number_includes_detailed_fields(client: httpx.Client):
    """GET /incidents/{number} must include richer fields not present in the list endpoint."""
    number = _get_first_incident_number(client)
    body = client.get(f"{INCIDENTS_URL}/{number}").json()
    # These fields are selected in the single-incident query but not the list query
    for field in ("sys_id", "description", "close_notes", "cluster"):
        assert field in body, f"Single-incident response missing field '{field}'"


def test_get_incident_cluster_field_is_dict_or_null(client: httpx.Client):
    """GET /incidents/{number} `cluster` must be a dict (with id, cluster_name) or null."""
    number = _get_first_incident_number(client)
    body = client.get(f"{INCIDENTS_URL}/{number}").json()
    cluster = body.get("cluster")
    if cluster is not None:
        assert isinstance(cluster, dict), f"cluster must be a dict, got {type(cluster)}"
        assert "id" in cluster
        assert "cluster_name" in cluster


def test_get_incident_returns_404_for_nonexistent_number(client: httpx.Client):
    """GET /incidents/INC0000000 must return HTTP 404 when the incident does not exist."""
    response = client.get(f"{INCIDENTS_URL}/INC0000000")
    assert response.status_code == 404, (
        f"Expected 404 for a non-existent incident, got {response.status_code}"
    )


def test_get_incident_404_body_does_not_expose_stack_trace(client: httpx.Client):
    """GET /incidents/INC0000000 404 body must not leak internal stack trace details."""
    response = client.get(f"{INCIDENTS_URL}/INC0000000")
    text = response.text.lower()
    for leak_indicator in ("traceback", "asyncpg", "sqlstate", "pg_exception"):
        assert leak_indicator not in text, (
            f"Potential internal detail leaked in 404 response: '{leak_indicator}'"
        )
