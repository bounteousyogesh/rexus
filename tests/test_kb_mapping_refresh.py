"""
test_kb_mapping_refresh.py — Tests for GET/POST /api/v1/kb-mappings/refresh*

Unit tests cover grouping, run_kb_mapping_refresh column updates (mocked SN + DB).
HTTP tests cover preview structure and POST validation (live backend).
"""

from unittest.mock import AsyncMock, MagicMock, patch

from datetime import datetime

import httpx
import pytest

from backend.api.utils.incident_groups import group_incidents_by_period
from backend.api.utils.kb_articles import insert_kb_mappings
from backend.api.utils.sync_constants import KB_MAPPING_REFRESH_MAX
from backend.services.kb_mapping_refresh import run_kb_mapping_refresh

REFRESH_PREVIEW_URL = "/api/v1/kb-mappings/refresh/preview"
REFRESH_POST_URL = "/api/v1/kb-mappings/refresh"


# ===========================================================================
# Unit: group_incidents_by_period
# ===========================================================================

def test_group_incidents_by_period_groups_and_sorts_reverse_chronological():
    incidents = [
        {
            "incident_number": "INC0000001",
            "short_description": "Older",
            "opened_at": "2024-01-15",
            "cmdb_ci": "POS",
            "category": "Software",
            "has_kb_article": None,
        },
        {
            "incident_number": "INC0000002",
            "short_description": "Newer",
            "opened_at": "2025-03-10",
            "cmdb_ci": "Vision",
            "category": "Hardware",
            "has_kb_article": True,
        },
    ]
    grouped = group_incidents_by_period(incidents)

    assert grouped["by_month"][0]["month"] == "2025-03"
    assert grouped["by_month"][1]["month"] == "2024-01"
    assert grouped["by_month"][0]["count"] == 1
    assert grouped["by_month"][0]["incidents"][0]["incident_number"] == "INC0000002"

    assert grouped["by_day"][0]["day"] == "2025-03-10"
    assert grouped["by_week"][0]["week"].startswith("2025-W")


def _legacy_sync_delta_grouping(incidents: list[dict]) -> dict:
    """Inline grouping logic previously in GET /sync/delta."""
    months: dict[str, list] = {}
    weeks: dict[str, list] = {}
    days: dict[str, list] = {}
    for inc in incidents:
        opened = inc.get("opened_at", "")
        if opened:
            try:
                dt = datetime.strptime(opened[:10], "%Y-%m-%d")
                month_key = dt.strftime("%Y-%m")
                week_key = f"{dt.year}-W{dt.isocalendar()[1]:02d}"
                day_key = dt.strftime("%Y-%m-%d")

                months.setdefault(month_key, []).append(inc)
                weeks.setdefault(week_key, []).append(inc)
                days.setdefault(day_key, []).append(inc)
            except ValueError:
                pass

    sorted_months = sorted(months.items(), key=lambda x: x[0], reverse=True)
    sorted_weeks = sorted(weeks.items(), key=lambda x: x[0], reverse=True)
    sorted_days = sorted(days.items(), key=lambda x: x[0], reverse=True)

    return {
        "by_month": [{"month": m, "count": len(incs), "incidents": incs} for m, incs in sorted_months],
        "by_week": [{"week": w, "count": len(incs), "incidents": incs} for w, incs in sorted_weeks],
        "by_day": [{"day": d, "count": len(incs), "incidents": incs} for d, incs in sorted_days],
    }


def test_group_incidents_by_period_matches_legacy_sync_delta_grouping():
    incidents = [
        {
            "incident_number": "INC0000001",
            "short_description": "Jan incident",
            "opened_at": "2024-01-15",
            "cmdb_ci": "POS",
            "category": "Software",
        },
        {
            "incident_number": "INC0000002",
            "short_description": "Mar incident",
            "opened_at": "2025-03-10",
            "cmdb_ci": "Vision",
            "category": "Hardware",
        },
        {
            "incident_number": "INC0000003",
            "short_description": "Invalid date",
            "opened_at": "not-a-date",
            "cmdb_ci": "POS",
            "category": "Software",
        },
    ]
    assert group_incidents_by_period(incidents) == _legacy_sync_delta_grouping(incidents)


# ===========================================================================
# Unit: insert_kb_mappings ON CONFLICT
# ===========================================================================

@pytest.mark.asyncio
async def test_insert_kb_mappings_uses_on_conflict_and_counts_inserted():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[{"?column?": 1}])
    kb_list = [
        {"number": "KB001", "short_description": "New"},
        {"number": "KB002", "short_description": "Existing"},
    ]
    count = await insert_kb_mappings(conn, "INC001", kb_list)
    assert count == 1
    conn.fetch.assert_awaited_once()
    sql = conn.fetch.await_args.args[0]
    assert "ON CONFLICT" in sql
    assert "DO NOTHING" in sql
    assert "unnest" in sql


# ===========================================================================
# Unit: run_kb_mapping_refresh dedupe
# ===========================================================================

@pytest.mark.asyncio
async def test_run_kb_mapping_refresh_dedupes_incident_numbers():
    sn_client = MagicMock()
    sn_client.get_incident_detailed.return_value = None
    conn = AsyncMock()
    conn.execute = AsyncMock()
    pool = _mock_pool(conn)

    result = await run_kb_mapping_refresh(
        pool,
        sn_client,
        ["INC0000100", "inc0000100", "INC0000100", "  INC0000200  "],
    )

    assert result["summary"]["candidates"] == 2
    assert sn_client.get_incident_detailed.call_count == 2
    called = [c.args[0] for c in sn_client.get_incident_detailed.call_args_list]
    assert called == ["INC0000100", "INC0000200"]
    assert len(result["results"]) == 2
    pool.acquire.assert_called_once()


# ===========================================================================
# Unit: run_kb_mapping_refresh has_kb_article updates
# ===========================================================================

def _mock_pool(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    acquire = MagicMock()
    acquire.__aenter__ = AsyncMock(return_value=conn)
    acquire.__aexit__ = AsyncMock(return_value=None)
    pool.acquire.return_value = acquire
    return pool


@pytest.mark.asyncio
async def test_run_kb_mapping_refresh_mapped_sets_has_kb_true():
    sn_client = MagicMock()
    sn_client.get_incident_detailed.return_value = {
        "kb_articles": [{"number": "KB001", "short_description": "Fix"}],
    }
    conn = AsyncMock()
    conn.execute = AsyncMock()
    pool = _mock_pool(conn)

    with patch(
        "backend.services.kb_mapping_refresh.insert_kb_mappings",
        new_callable=AsyncMock,
        return_value=1,
    ):
        result = await run_kb_mapping_refresh(pool, sn_client, ["INC0000100"])

    assert result["results"][0]["status"] == "mapped"
    assert result["results"][0]["kb_from_sn"] == 1
    assert result["summary"]["with_kb"] == 1
    update_calls = [
        c for c in conn.execute.call_args_list
        if "has_kb_article" in str(c.args[0])
    ]
    assert len(update_calls) == 1
    assert update_calls[0].args[1:] == ("INC0000100", True)


@pytest.mark.asyncio
async def test_run_kb_mapping_refresh_no_kb_sets_has_kb_false():
    sn_client = MagicMock()
    sn_client.get_incident_detailed.return_value = {"incident": {"number": "INC0000200"}}
    conn = AsyncMock()
    conn.execute = AsyncMock()
    pool = _mock_pool(conn)

    result = await run_kb_mapping_refresh(pool, sn_client, ["INC0000200"])

    assert result["results"][0]["status"] == "no_kb"
    assert result["summary"]["no_kb"] == 1
    conn.execute.assert_awaited_once()
    assert conn.execute.await_args.args[1:] == ("INC0000200", False)


@pytest.mark.asyncio
async def test_run_kb_mapping_refresh_not_found_leaves_has_kb_unchanged():
    sn_client = MagicMock()
    sn_client.get_incident_detailed.return_value = None
    conn = AsyncMock()
    conn.execute = AsyncMock()
    pool = _mock_pool(conn)

    result = await run_kb_mapping_refresh(pool, sn_client, ["INC0000300"])

    assert result["results"][0]["status"] == "not_found"
    assert result["summary"]["not_found"] == 1
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_kb_mapping_refresh_error_leaves_has_kb_unchanged():
    sn_client = MagicMock()
    sn_client.get_incident_detailed.side_effect = RuntimeError("SN timeout")
    conn = AsyncMock()
    conn.execute = AsyncMock()
    pool = _mock_pool(conn)

    result = await run_kb_mapping_refresh(pool, sn_client, ["INC0000400"])

    assert result["results"][0]["status"] == "error"
    assert result["summary"]["errors"] == 1
    conn.execute.assert_not_awaited()


# ===========================================================================
# GET /kb-mappings/refresh/preview
# ===========================================================================

def test_kb_mapping_refresh_preview_returns_200(client: httpx.Client):
    response = client.get(REFRESH_PREVIEW_URL)
    assert response.status_code == 200, response.text[:300]


def test_kb_mapping_refresh_preview_contains_grouped_structure(client: httpx.Client):
    body = client.get(REFRESH_PREVIEW_URL).json()
    for field in ("filter", "total", "by_month", "by_week", "by_day"):
        assert field in body, f"preview response missing '{field}'"
    assert body["filter"]["has_kb_article"] == "not_synced"
    assert isinstance(body["total"], int)
    assert body["total"] >= 0


def test_kb_mapping_refresh_preview_not_synced_filter_excludes_synced_rows(client: httpx.Client):
    all_body = client.get(REFRESH_PREVIEW_URL, params={"has_kb_article": "all"}).json()
    not_synced_body = client.get(REFRESH_PREVIEW_URL).json()
    assert not_synced_body["filter"]["has_kb_article"] == "not_synced"
    assert not_synced_body["total"] <= all_body["total"]

    def collect_has_kb(body: dict) -> list:
        values = []
        for group in body.get("by_month", []):
            for inc in group.get("incidents", []):
                values.append(inc.get("has_kb_article"))
        return values

    for has_kb in collect_has_kb(not_synced_body):
        assert has_kb is None, f"not_synced filter returned has_kb_article={has_kb!r}"


def test_kb_mapping_refresh_preview_accepts_kb_article_filter(client: httpx.Client):
    for kb_filter in ("all", "synced", "not_synced"):
        response = client.get(REFRESH_PREVIEW_URL, params={"has_kb_article": kb_filter})
        assert response.status_code == 200
        assert response.json()["filter"]["has_kb_article"] == kb_filter


def test_kb_mapping_refresh_preview_by_month_entries_have_expected_fields(client: httpx.Client):
    body = client.get(REFRESH_PREVIEW_URL).json()
    for entry in body["by_month"][:3]:
        for field in ("month", "count", "incidents"):
            assert field in entry


# ===========================================================================
# POST /kb-mappings/refresh — validation
# ===========================================================================

def test_kb_mapping_refresh_post_rejects_empty_incident_list(client: httpx.Client):
    response = client.post(REFRESH_POST_URL, json={"incident_numbers": []})
    assert response.status_code == 400


def test_kb_mapping_refresh_post_rejects_more_than_max_incidents(client: httpx.Client):
    too_many = [f"INC{i:07d}" for i in range(1, KB_MAPPING_REFRESH_MAX + 2)]
    response = client.post(REFRESH_POST_URL, json={"incident_numbers": too_many})
    assert response.status_code == 422


def test_kb_mapping_refresh_post_missing_incident_numbers_returns_422(client: httpx.Client):
    response = client.post(REFRESH_POST_URL, json={"wrong_field": ["INC0000001"]})
    assert response.status_code == 422


def test_kb_mapping_refresh_post_returns_summary_and_results(client: httpx.Client):
    response = client.post(
        REFRESH_POST_URL,
        json={"incident_numbers": ["INC0000001"]},
        timeout=30.0,
    )
    if response.status_code == 500:
        pytest.skip("ServiceNow not configured — KB mapping refresh returned 500")
    assert response.status_code == 200
    body = response.json()
    assert "summary" in body
    assert "results" in body
    assert isinstance(body["results"], list)
    for field in ("candidates", "with_kb", "no_kb", "not_found", "errors"):
        assert field in body["summary"]