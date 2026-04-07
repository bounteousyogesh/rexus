"""
test_playbooks.py — Tests for GET /api/v1/playbooks, GET /api/v1/playbooks/{id},
                    and POST /api/v1/playbooks/generate/{cluster_id}

Covers:
  - Paginated list with default params and envelope shape
  - Optional `status` filter
  - Get single playbook by ID
  - 404 for non-existent playbook ID
  - Playbook item field shape (grounding_score, content, source_incident_count)
  - Generate endpoint validates cluster existence (404 for unknown cluster)
  - No raw embedding data in any playbook response
"""

import pytest
import httpx


PLAYBOOKS_URL = "/api/v1/playbooks"


# ===========================================================================
# List playbooks — envelope and HTTP status
# ===========================================================================

def test_list_playbooks_returns_200(client: httpx.Client):
    """GET /playbooks must return HTTP 200."""
    response = client.get(PLAYBOOKS_URL)
    assert response.status_code == 200


def test_list_playbooks_envelope_has_required_fields(client: httpx.Client):
    """GET /playbooks response must include total, page, page_size, pages, items."""
    body = client.get(PLAYBOOKS_URL).json()
    required = {"total", "page", "page_size", "pages", "items"}
    missing = required - body.keys()
    assert not missing, f"Playbooks envelope missing fields: {missing}"


def test_list_playbooks_items_is_a_list(client: httpx.Client):
    """GET /playbooks `items` must always be a list."""
    body = client.get(PLAYBOOKS_URL).json()
    assert isinstance(body["items"], list)


def test_list_playbooks_total_is_non_negative(client: httpx.Client):
    """GET /playbooks total must be >= 0."""
    body = client.get(PLAYBOOKS_URL).json()
    assert body["total"] >= 0


def test_list_playbooks_pages_minimum_is_1(client: httpx.Client):
    """GET /playbooks pages uses max(1, ...) formula — must be >= 1."""
    body = client.get(PLAYBOOKS_URL).json()
    assert body["pages"] >= 1


def test_list_playbooks_items_do_not_exceed_page_size(client: httpx.Client):
    """GET /playbooks items count must not exceed page_size."""
    body = client.get(PLAYBOOKS_URL, params={"page_size": 5}).json()
    assert len(body["items"]) <= 5


# ===========================================================================
# List playbooks — item field shape
# ===========================================================================

def test_list_playbooks_items_have_expected_fields(client: httpx.Client):
    """Each playbook item must include standard display fields."""
    body = client.get(PLAYBOOKS_URL, params={"page_size": 1}).json()
    if not body["items"]:
        pytest.skip("No playbooks in the database")
    item = body["items"][0]
    expected = {"id", "title", "cluster_id", "grounding_score", "status", "source_incident_count"}
    missing = expected - item.keys()
    assert not missing, f"Playbook list item missing fields: {missing}"


def test_list_playbooks_items_include_cluster_name(client: httpx.Client):
    """Each playbook list item must include cluster_name (JOIN with rexus_clusters)."""
    body = client.get(PLAYBOOKS_URL, params={"page_size": 3}).json()
    if not body["items"]:
        pytest.skip("No playbooks in the database")
    for item in body["items"]:
        # cluster_name may be None if the cluster was deleted, but key must be present
        assert "cluster_name" in item, "Playbook item missing cluster_name from JOIN"


def test_list_playbooks_grounding_score_is_valid_float(client: httpx.Client):
    """Each playbook item's grounding_score must be float 0.0-1.0 or null."""
    body = client.get(PLAYBOOKS_URL, params={"page_size": 5}).json()
    if not body["items"]:
        pytest.skip("No playbooks in the database")
    for item in body["items"]:
        score = item.get("grounding_score")
        if score is not None:
            assert isinstance(score, (float, int)), f"grounding_score must be numeric"
            assert 0.0 <= float(score) <= 1.0, f"grounding_score out of range: {score}"


def test_list_playbooks_does_not_expose_full_content_in_list(client: httpx.Client):
    """
    GET /playbooks list must NOT include the `content` field (potentially large Markdown).
    Full content is only returned by the single-playbook endpoint.
    """
    body = client.get(PLAYBOOKS_URL, params={"page_size": 3}).json()
    for item in body["items"]:
        assert "content" not in item, (
            "Playbook list item should not include full `content` field — fetch /playbooks/{id}"
        )


# ===========================================================================
# List playbooks — status filter
# ===========================================================================

def test_list_playbooks_status_filter_returns_only_matching_status(client: httpx.Client):
    """GET /playbooks?status=draft must return only playbooks with status='draft'."""
    body = client.get(PLAYBOOKS_URL, params={"status": "draft", "page_size": 20}).json()
    for item in body["items"]:
        assert item["status"] == "draft", (
            f"Playbook {item['id']} has status='{item['status']}' but filter=draft was requested"
        )


def test_list_playbooks_unknown_status_returns_empty_not_error(client: httpx.Client):
    """GET /playbooks?status=nonexistent_status must return 200 with 0 items (not 4xx/5xx)."""
    body = client.get(PLAYBOOKS_URL, params={"status": "nonexistent_xyz"}).json()
    assert body["total"] == 0
    assert body["items"] == []


# ===========================================================================
# Pagination validation
# ===========================================================================

def test_list_playbooks_rejects_page_zero(client: httpx.Client):
    """GET /playbooks?page=0 must return 422."""
    response = client.get(PLAYBOOKS_URL, params={"page": 0})
    assert response.status_code == 422


def test_list_playbooks_rejects_page_size_above_100(client: httpx.Client):
    """GET /playbooks?page_size=101 must return 422."""
    response = client.get(PLAYBOOKS_URL, params={"page_size": 101})
    assert response.status_code == 422


# ===========================================================================
# Get single playbook
# ===========================================================================

def _get_first_playbook_id(client: httpx.Client) -> int:
    """Helper: retrieve an ID of an existing playbook."""
    body = client.get(PLAYBOOKS_URL, params={"page_size": 1}).json()
    if not body["items"]:
        pytest.skip("No playbooks in the database")
    return body["items"][0]["id"]


def test_get_playbook_by_id_returns_200(client: httpx.Client):
    """GET /playbooks/{id} must return 200 for an existing playbook."""
    playbook_id = _get_first_playbook_id(client)
    response = client.get(f"{PLAYBOOKS_URL}/{playbook_id}")
    assert response.status_code == 200


def test_get_playbook_by_id_returns_correct_playbook(client: httpx.Client):
    """GET /playbooks/{id} must return the playbook whose id matches."""
    playbook_id = _get_first_playbook_id(client)
    body = client.get(f"{PLAYBOOKS_URL}/{playbook_id}").json()
    assert body["id"] == playbook_id


def test_get_playbook_detail_includes_content(client: httpx.Client):
    """GET /playbooks/{id} must include the full `content` field (the Markdown playbook)."""
    playbook_id = _get_first_playbook_id(client)
    body = client.get(f"{PLAYBOOKS_URL}/{playbook_id}").json()
    assert "content" in body, "Single playbook response missing 'content' field"


def test_get_playbook_detail_includes_grounding_score(client: httpx.Client):
    """GET /playbooks/{id} must include grounding_score."""
    playbook_id = _get_first_playbook_id(client)
    body = client.get(f"{PLAYBOOKS_URL}/{playbook_id}").json()
    assert "grounding_score" in body


def test_get_playbook_detail_includes_source_incident_count(client: httpx.Client):
    """GET /playbooks/{id} must include source_incident_count (how many incidents it's based on)."""
    playbook_id = _get_first_playbook_id(client)
    body = client.get(f"{PLAYBOOKS_URL}/{playbook_id}").json()
    assert "source_incident_count" in body


def test_get_playbook_detail_includes_cluster_info(client: httpx.Client):
    """GET /playbooks/{id} must include cluster_name and cluster_size from the JOIN."""
    playbook_id = _get_first_playbook_id(client)
    body = client.get(f"{PLAYBOOKS_URL}/{playbook_id}").json()
    for field in ("cluster_name", "cluster_size"):
        assert field in body, f"Playbook detail missing joined field '{field}'"


def test_get_playbook_detail_does_not_expose_embedding(client: httpx.Client):
    """GET /playbooks/{id} must not include raw embedding vector data."""
    playbook_id = _get_first_playbook_id(client)
    body = client.get(f"{PLAYBOOKS_URL}/{playbook_id}").json()
    assert "embedding" not in body


def test_get_playbook_returns_404_for_nonexistent_id(client: httpx.Client):
    """GET /playbooks/999999999 must return 404 when the playbook does not exist."""
    response = client.get(f"{PLAYBOOKS_URL}/999999999")
    assert response.status_code == 404


def test_get_playbook_404_body_does_not_expose_internal_details(client: httpx.Client):
    """GET /playbooks/999999999 404 must not leak DB internals."""
    response = client.get(f"{PLAYBOOKS_URL}/999999999")
    text = response.text.lower()
    for leak in ("traceback", "asyncpg", "sqlstate"):
        assert leak not in text


# ===========================================================================
# POST /playbooks/generate/{cluster_id} — validation only
# ===========================================================================

def test_generate_playbook_returns_404_for_nonexistent_cluster(openai_client: httpx.Client):
    """
    POST /playbooks/generate/999999999 must return 404 — cluster does not exist.
    This validates without spending an OpenAI token since the check is pre-LLM.
    """
    response = openai_client.post(f"{PLAYBOOKS_URL}/generate/999999999")
    assert response.status_code == 404, (
        f"Expected 404 for non-existent cluster, got {response.status_code}"
    )


def test_generate_playbook_accepts_valid_cluster_id_format(openai_client: httpx.Client):
    """
    POST /playbooks/generate/{cluster_id} with a valid existing cluster must
    not return 404 or 422. It may return 200 (generated) or 400 (no incidents).
    This test skips if no clusters are available.
    """
    # Get a cluster ID
    list_body = openai_client.get("/api/v1/clusters", params={"page_size": 1}).json()
    if not list_body["items"]:
        pytest.skip("No clusters in the database")
    cluster_id = list_body["items"][0]["id"]

    response = openai_client.post(f"{PLAYBOOKS_URL}/generate/{cluster_id}")
    # 200 = generated successfully, 400 = no incidents in cluster
    assert response.status_code in (200, 400), (
        f"Expected 200 or 400, got {response.status_code}: {response.text[:200]}"
    )
