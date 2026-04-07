"""
test_clusters.py — Tests for GET /api/v1/clusters and GET /api/v1/clusters/{id}

Covers:
  - Paginated list with default params and envelope shape
  - min_size filter
  - sort_by parameter (incident_count, avg_resolution_hours, cluster_name)
  - sort_by with invalid value returns 422
  - Get single cluster by ID
  - 404 for non-existent cluster ID
  - Cluster detail includes top_incidents list and playbook field
  - No raw embedding data in any response
"""

import pytest
import httpx


CLUSTERS_URL = "/api/v1/clusters"


# ===========================================================================
# List clusters — envelope and HTTP status
# ===========================================================================

def test_list_clusters_returns_200(client: httpx.Client):
    """GET /clusters must return HTTP 200."""
    response = client.get(CLUSTERS_URL)
    assert response.status_code == 200


def test_list_clusters_envelope_has_required_fields(client: httpx.Client):
    """GET /clusters response must include total, page, page_size, pages, items."""
    body = client.get(CLUSTERS_URL).json()
    required = {"total", "page", "page_size", "pages", "items"}
    missing = required - body.keys()
    assert not missing, f"Clusters envelope missing fields: {missing}"


def test_list_clusters_items_is_a_list(client: httpx.Client):
    """GET /clusters `items` must be a list."""
    body = client.get(CLUSTERS_URL).json()
    assert isinstance(body["items"], list)


def test_list_clusters_default_page_is_1(client: httpx.Client):
    """GET /clusters default page must be 1."""
    body = client.get(CLUSTERS_URL).json()
    assert body["page"] == 1


def test_list_clusters_default_page_size_is_20(client: httpx.Client):
    """GET /clusters default page_size must be 20."""
    body = client.get(CLUSTERS_URL).json()
    assert body["page_size"] == 20


def test_list_clusters_items_count_does_not_exceed_page_size(client: httpx.Client):
    """GET /clusters items count must never exceed page_size."""
    body = client.get(CLUSTERS_URL, params={"page_size": 5}).json()
    assert len(body["items"]) <= 5


def test_list_clusters_total_is_non_negative(client: httpx.Client):
    """GET /clusters total must be >= 0."""
    body = client.get(CLUSTERS_URL).json()
    assert body["total"] >= 0


# ===========================================================================
# List clusters — item field shape
# ===========================================================================

def test_list_clusters_items_have_expected_fields(client: httpx.Client):
    """Each cluster item must include the core display fields."""
    body = client.get(CLUSTERS_URL, params={"page_size": 1}).json()
    if not body["items"]:
        pytest.skip("No clusters in the database")
    item = body["items"][0]
    expected = {
        "id", "cluster_name", "incident_count",
        "dominant_category", "avg_resolution_hours",
    }
    missing = expected - item.keys()
    assert not missing, f"Cluster item missing fields: {missing}"


def test_list_clusters_items_do_not_expose_embedding(client: httpx.Client):
    """GET /clusters items must not contain raw embedding vectors."""
    body = client.get(CLUSTERS_URL, params={"page_size": 5}).json()
    for item in body["items"]:
        assert "embedding" not in item


def test_list_clusters_incident_count_is_positive_integer(client: httpx.Client):
    """Each cluster item's incident_count must be a positive integer."""
    body = client.get(CLUSTERS_URL, params={"page_size": 5}).json()
    if not body["items"]:
        pytest.skip("No clusters in the database")
    for item in body["items"]:
        assert isinstance(item["incident_count"], int)
        assert item["incident_count"] >= 1


# ===========================================================================
# List clusters — min_size filter
# ===========================================================================

def test_list_clusters_min_size_filter_excludes_small_clusters(client: httpx.Client):
    """GET /clusters?min_size=X must return only clusters with incident_count >= X."""
    min_size = 5
    body = client.get(CLUSTERS_URL, params={"min_size": min_size, "page_size": 20}).json()
    for item in body["items"]:
        assert item["incident_count"] >= min_size, (
            f"Cluster '{item['cluster_name']}' has incident_count={item['incident_count']} "
            f"but min_size={min_size} was requested"
        )


def test_list_clusters_min_size_1_returns_all_clusters(client: httpx.Client):
    """GET /clusters?min_size=1 is the default and must return all clusters."""
    total_default = client.get(CLUSTERS_URL).json()["total"]
    total_min1 = client.get(CLUSTERS_URL, params={"min_size": 1}).json()["total"]
    assert total_min1 == total_default


def test_list_clusters_high_min_size_returns_fewer_clusters(client: httpx.Client):
    """GET /clusters?min_size=1000 must return <= clusters than min_size=1."""
    low_total = client.get(CLUSTERS_URL, params={"min_size": 1}).json()["total"]
    high_total = client.get(CLUSTERS_URL, params={"min_size": 1000}).json()["total"]
    assert high_total <= low_total


# ===========================================================================
# List clusters — sort_by parameter
# ===========================================================================

def test_list_clusters_sort_by_incident_count_is_accepted(client: httpx.Client):
    """GET /clusters?sort_by=incident_count must return 200."""
    response = client.get(CLUSTERS_URL, params={"sort_by": "incident_count"})
    assert response.status_code == 200


def test_list_clusters_sort_by_avg_resolution_hours_is_accepted(client: httpx.Client):
    """GET /clusters?sort_by=avg_resolution_hours must return 200."""
    response = client.get(CLUSTERS_URL, params={"sort_by": "avg_resolution_hours"})
    assert response.status_code == 200


def test_list_clusters_sort_by_cluster_name_is_accepted(client: httpx.Client):
    """GET /clusters?sort_by=cluster_name must return 200."""
    response = client.get(CLUSTERS_URL, params={"sort_by": "cluster_name"})
    assert response.status_code == 200


def test_list_clusters_sort_by_invalid_value_returns_422(client: httpx.Client):
    """
    GET /clusters?sort_by=malicious_value must return 422.
    The sort_by param uses pattern='^(incident_count|avg_resolution_hours|cluster_name)$'
    to prevent SQL injection via ORDER BY.
    """
    response = client.get(CLUSTERS_URL, params={"sort_by": "1; DROP TABLE rexus_clusters--"})
    assert response.status_code == 422, (
        f"Expected 422 for invalid sort_by, got {response.status_code}"
    )


def test_list_clusters_sorted_by_incident_count_is_descending(client: httpx.Client):
    """GET /clusters?sort_by=incident_count items must be in descending incident_count order."""
    body = client.get(CLUSTERS_URL, params={"sort_by": "incident_count", "page_size": 10}).json()
    if len(body["items"]) < 2:
        pytest.skip("Not enough clusters to verify sort order")
    counts = [i["incident_count"] for i in body["items"] if i["incident_count"] is not None]
    assert counts == sorted(counts, reverse=True), (
        f"Clusters not in descending incident_count order: {counts}"
    )


# ===========================================================================
# Pagination validation
# ===========================================================================

def test_list_clusters_rejects_page_zero(client: httpx.Client):
    """GET /clusters?page=0 must return 422."""
    response = client.get(CLUSTERS_URL, params={"page": 0})
    assert response.status_code == 422


def test_list_clusters_rejects_page_size_above_100(client: httpx.Client):
    """GET /clusters?page_size=101 must return 422."""
    response = client.get(CLUSTERS_URL, params={"page_size": 101})
    assert response.status_code == 422


# ===========================================================================
# Get single cluster detail
# ===========================================================================

def _get_first_cluster_id(client: httpx.Client) -> int:
    """Helper: retrieve an ID of an existing cluster."""
    body = client.get(CLUSTERS_URL, params={"page_size": 1}).json()
    if not body["items"]:
        pytest.skip("No clusters in the database")
    return body["items"][0]["id"]


def test_get_cluster_by_id_returns_200(client: httpx.Client):
    """GET /clusters/{id} must return 200 for an existing cluster."""
    cluster_id = _get_first_cluster_id(client)
    response = client.get(f"{CLUSTERS_URL}/{cluster_id}")
    assert response.status_code == 200


def test_get_cluster_by_id_returns_correct_cluster(client: httpx.Client):
    """GET /clusters/{id} must return the cluster whose id matches the path param."""
    cluster_id = _get_first_cluster_id(client)
    body = client.get(f"{CLUSTERS_URL}/{cluster_id}").json()
    assert body["id"] == cluster_id


def test_get_cluster_detail_includes_top_incidents(client: httpx.Client):
    """GET /clusters/{id} must include `top_incidents` list."""
    cluster_id = _get_first_cluster_id(client)
    body = client.get(f"{CLUSTERS_URL}/{cluster_id}").json()
    assert "top_incidents" in body, "Cluster detail missing top_incidents"
    assert isinstance(body["top_incidents"], list)


def test_get_cluster_detail_includes_playbook_field(client: httpx.Client):
    """GET /clusters/{id} must include `playbook` field (dict or null)."""
    cluster_id = _get_first_cluster_id(client)
    body = client.get(f"{CLUSTERS_URL}/{cluster_id}").json()
    assert "playbook" in body, "Cluster detail missing playbook field"
    playbook = body["playbook"]
    if playbook is not None:
        assert isinstance(playbook, dict)
        for field in ("id", "title", "grounding_score", "status"):
            assert field in playbook, f"Playbook summary missing field '{field}'"


def test_get_cluster_detail_top_incidents_have_incident_number(client: httpx.Client):
    """Top incidents in cluster detail must include incident_number."""
    cluster_id = _get_first_cluster_id(client)
    body = client.get(f"{CLUSTERS_URL}/{cluster_id}").json()
    if not body.get("top_incidents"):
        pytest.skip("No incidents mapped to this cluster")
    for inc in body["top_incidents"]:
        assert "incident_number" in inc


def test_get_cluster_detail_top_incidents_do_not_expose_work_notes(client: httpx.Client):
    """SEC-014: Cluster detail top_incidents must not include work_notes."""
    cluster_id = _get_first_cluster_id(client)
    body = client.get(f"{CLUSTERS_URL}/{cluster_id}").json()
    for inc in body.get("top_incidents", []):
        assert "work_notes" not in inc, (
            f"SEC-014: work_notes exposed in cluster {cluster_id} top_incidents"
        )


def test_get_cluster_returns_404_for_nonexistent_id(client: httpx.Client):
    """GET /clusters/999999999 must return 404 when the cluster does not exist."""
    response = client.get(f"{CLUSTERS_URL}/999999999")
    assert response.status_code == 404


def test_get_cluster_404_body_does_not_expose_internal_details(client: httpx.Client):
    """GET /clusters/999999999 404 must not leak stack trace or DB details."""
    response = client.get(f"{CLUSTERS_URL}/999999999")
    text = response.text.lower()
    for leak in ("traceback", "asyncpg", "sqlstate", "pg_exception"):
        assert leak not in text, f"Internal detail '{leak}' leaked in 404 response"
