"""
test_search.py — Tests for GET /api/v1/search

The search endpoint performs vector similarity search using OpenAI embeddings
(text-embedding-3-small) and a pgvector stored function (rexus_find_similar).

Covers:
  - Valid query returns 200 with correct envelope shape
  - Results include similarity_score, incident_number, short_description, close_notes
  - Short query (< 3 chars) is rejected with 422 (FastAPI min_length=3 validation)
  - `threshold` parameter filters low-confidence results
  - `limit` parameter caps result count
  - Response never exposes embedding vector or work_notes
  - Very high threshold returns fewer or equal results than lower threshold

Note: all tests in this module use `openai_client` (60 s timeout) because
the backend calls the OpenAI embeddings API before querying the database.
"""

import pytest
import httpx


SEARCH_URL = "/api/v1/search"


# ---------------------------------------------------------------------------
# Happy-path: envelope shape
# ---------------------------------------------------------------------------

def test_search_with_valid_query_returns_200(openai_client: httpx.Client):
    """GET /search?q=vision must return HTTP 200."""
    response = openai_client.get(SEARCH_URL, params={"q": "vision order not processing"})
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text[:300]}"
    )


def test_search_response_envelope_has_required_fields(openai_client: httpx.Client):
    """GET /search response must include query, threshold, count, and results."""
    body = openai_client.get(
        SEARCH_URL, params={"q": "pos terminal error"}
    ).json()
    required = {"query", "threshold", "count", "results"}
    missing = required - body.keys()
    assert not missing, f"Search response missing fields: {missing}"


def test_search_response_query_echoes_input(openai_client: httpx.Client):
    """`query` field in response must echo the exact query string sent."""
    q = "GK POS checkout failure"
    body = openai_client.get(SEARCH_URL, params={"q": q}).json()
    assert body["query"] == q


def test_search_response_count_matches_results_length(openai_client: httpx.Client):
    """`count` field must equal len(results) — these must always agree."""
    body = openai_client.get(
        SEARCH_URL, params={"q": "IDoc processing error"}
    ).json()
    assert body["count"] == len(body["results"]), (
        f"count={body['count']} but len(results)={len(body['results'])}"
    )


def test_search_results_is_a_list(openai_client: httpx.Client):
    """`results` must always be a list, even when empty."""
    body = openai_client.get(
        SEARCH_URL, params={"q": "some search query"}
    ).json()
    assert isinstance(body["results"], list)


# ---------------------------------------------------------------------------
# Result item field shape
# ---------------------------------------------------------------------------

def test_search_results_items_have_similarity_scores(openai_client: httpx.Client):
    """Each result item must include `similarity_score` as a float 0.0-1.0."""
    body = openai_client.get(
        SEARCH_URL, params={"q": "vision order sync", "threshold": 0.0, "limit": 5}
    ).json()
    if not body["results"]:
        pytest.skip("No results returned — cannot verify item shape")
    for item in body["results"]:
        assert "similarity_score" in item, "Result item missing similarity_score"
        score = item["similarity_score"]
        assert isinstance(score, (float, int)), f"similarity_score must be numeric, got {type(score)}"
        assert 0.0 <= float(score) <= 1.0, f"similarity_score out of [0, 1]: {score}"


def test_search_results_items_have_incident_number(openai_client: httpx.Client):
    """Each result item must include `incident_number`."""
    body = openai_client.get(
        SEARCH_URL, params={"q": "pos finalize error", "threshold": 0.0, "limit": 5}
    ).json()
    if not body["results"]:
        pytest.skip("No results — cannot verify incident_number field")
    for item in body["results"]:
        assert "incident_number" in item


def test_search_results_items_have_short_description(openai_client: httpx.Client):
    """Each result item must include `short_description`."""
    body = openai_client.get(
        SEARCH_URL, params={"q": "WE19 IDoc resend", "threshold": 0.0, "limit": 5}
    ).json()
    if not body["results"]:
        pytest.skip("No results — cannot verify short_description field")
    for item in body["results"]:
        assert "short_description" in item


def test_search_results_items_have_close_notes(openai_client: httpx.Client):
    """Each result item must include `close_notes` (may be null)."""
    body = openai_client.get(
        SEARCH_URL, params={"q": "order not found in vision", "threshold": 0.0, "limit": 5}
    ).json()
    if not body["results"]:
        pytest.skip("No results — cannot verify close_notes field")
    for item in body["results"]:
        assert "close_notes" in item


# ---------------------------------------------------------------------------
# Security: no sensitive fields in results
# ---------------------------------------------------------------------------

def test_search_results_do_not_expose_work_notes(openai_client: httpx.Client):
    """Search result items must not expose work_notes (PII risk — SEC-014)."""
    body = openai_client.get(
        SEARCH_URL, params={"q": "vision payment error", "threshold": 0.0, "limit": 10}
    ).json()
    for item in body["results"]:
        assert "work_notes" not in item, (
            f"work_notes exposed in search result for {item.get('incident_number')}"
        )


def test_search_results_do_not_expose_embedding_vector(openai_client: httpx.Client):
    """Search result items must not expose the raw embedding vector."""
    body = openai_client.get(
        SEARCH_URL, params={"q": "SAP OMS sync failure", "threshold": 0.0, "limit": 10}
    ).json()
    for item in body["results"]:
        assert "embedding" not in item


# ---------------------------------------------------------------------------
# Validation: short query rejection
# ---------------------------------------------------------------------------

def test_search_rejects_query_shorter_than_3_chars(openai_client: httpx.Client):
    """
    GET /search?q=ab must return HTTP 422.
    The endpoint declares q: str = Query(..., min_length=3) in FastAPI.
    A query shorter than 3 characters is semantically meaningless for vector search
    and triggers FastAPI's built-in length validation before any OpenAI call.
    """
    response = openai_client.get(SEARCH_URL, params={"q": "ab"})
    assert response.status_code == 422, (
        f"Expected 422 for q shorter than 3 chars, got {response.status_code}"
    )


def test_search_rejects_empty_query(openai_client: httpx.Client):
    """GET /search?q= (empty string) must return HTTP 422."""
    response = openai_client.get(SEARCH_URL, params={"q": ""})
    assert response.status_code == 422


def test_search_rejects_missing_q_parameter(openai_client: httpx.Client):
    """GET /search with no `q` query parameter must return HTTP 422."""
    response = openai_client.get(SEARCH_URL)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Parameter: threshold
# ---------------------------------------------------------------------------

def test_search_threshold_echoed_in_response(openai_client: httpx.Client):
    """GET /search `threshold` query param must be echoed in the response envelope."""
    body = openai_client.get(
        SEARCH_URL, params={"q": "vision order sync error", "threshold": 0.55}
    ).json()
    assert abs(body["threshold"] - 0.55) < 0.001, (
        f"Expected threshold=0.55, got {body.get('threshold')}"
    )


def test_search_high_threshold_returns_fewer_results_than_low_threshold(
    openai_client: httpx.Client,
):
    """
    GET /search with threshold=0.90 must return <= results of threshold=0.30.
    A stricter similarity cutoff can only reduce or maintain the result count.
    """
    low_body = openai_client.get(
        SEARCH_URL, params={"q": "vision order not processing", "threshold": 0.30, "limit": 50}
    ).json()
    high_body = openai_client.get(
        SEARCH_URL, params={"q": "vision order not processing", "threshold": 0.90, "limit": 50}
    ).json()
    assert high_body["count"] <= low_body["count"], (
        f"Higher threshold returned MORE results: low={low_body['count']}, high={high_body['count']}"
    )


def test_search_all_result_scores_meet_threshold(openai_client: httpx.Client):
    """All returned items must have similarity_score >= the requested threshold."""
    threshold = 0.50
    body = openai_client.get(
        SEARCH_URL,
        params={"q": "GK POS payment finalize error", "threshold": threshold, "limit": 50}
    ).json()
    for item in body["results"]:
        score = float(item.get("similarity_score", 0))
        assert score >= threshold - 0.01, (  # 0.01 tolerance for float rounding
            f"Result {item.get('incident_number')} has score {score} below threshold {threshold}"
        )


def test_search_threshold_above_1_returns_422(openai_client: httpx.Client):
    """GET /search?threshold=1.5 must return 422 — threshold is Query(ge=0.0, le=1.0)."""
    response = openai_client.get(
        SEARCH_URL, params={"q": "vision error", "threshold": 1.5}
    )
    assert response.status_code == 422


def test_search_threshold_below_0_returns_422(openai_client: httpx.Client):
    """GET /search?threshold=-0.1 must return 422."""
    response = openai_client.get(
        SEARCH_URL, params={"q": "vision error", "threshold": -0.1}
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Parameter: limit
# ---------------------------------------------------------------------------

def test_search_limit_caps_result_count(openai_client: httpx.Client):
    """GET /search?limit=3 must return at most 3 results."""
    body = openai_client.get(
        SEARCH_URL, params={"q": "vision order not syncing", "threshold": 0.0, "limit": 3}
    ).json()
    assert len(body["results"]) <= 3


def test_search_limit_above_50_returns_422(openai_client: httpx.Client):
    """GET /search?limit=51 must return 422 — limit is Query(ge=1, le=50)."""
    response = openai_client.get(
        SEARCH_URL, params={"q": "vision error", "limit": 51}
    )
    assert response.status_code == 422


def test_search_limit_zero_returns_422(openai_client: httpx.Client):
    """GET /search?limit=0 must return 422 — limit is Query(ge=1)."""
    response = openai_client.get(
        SEARCH_URL, params={"q": "vision error", "limit": 0}
    )
    assert response.status_code == 422
