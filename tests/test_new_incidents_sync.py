"""Tests for GET/POST /api/v1/sync/new-incidents/*"""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.api.models.sync import NewIncidentsRunRequest
from backend.api.routers.sync.new_incident import (
    _analyze_and_comment,
    _db_stats,
    _get_new_incidents,
    _mark_incident_analyzed,
    new_incidents_run,
)
from backend.api.routers.sync.sync import (
    INCIDENT_ROW_COLUMNS,
    UPSERT_SNAPSHOT_SQL,
    batch_upsert_snapshots,
    map_detailed_to_row,
)
from backend.services.servicenow_client import ServiceNowClient

PREVIEW_URL = "/api/v1/sync/new-incidents/preview"
RUN_URL = "/api/v1/sync/new-incidents/run"

def _mock_pool(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    acquire = MagicMock()
    acquire.__aenter__ = AsyncMock(return_value=conn)
    acquire.__aexit__ = AsyncMock(return_value=None)
    pool.acquire.return_value = acquire
    return pool

def _detailed_payload(opened_date: str | None = None) -> dict:
    opened_date = opened_date or date.today().strftime("%Y-%m-%d")
    return {
        "incident": {
            "number": "INC2387407",
            "sys_id": "8fc1bc749718a290fffebee6f053af63",
            "short_description": "Disk utilization high",
            "opened_at": f"{opened_date} 14:50:00",
            "cmdb_ci_display": "GK POS",
            "category": "Software",
            "incident_state_display": "New",
            "priority_display": "5 - Low",
            "assignment_group_display": "Information Center",
            "assigned_to_display": "Jane Analyst",
        },
        "resolution": {},
        "related_records": {},
        "order_data": {},
        "operational_metrics": {},
        "contact": {"opened_by_display": "John Caller"},
        "notes": {},
    }

def test_get_new_incidents_calls_search_api_with_dates_only():
    client = ServiceNowClient(
        instance_url="https://example.service-now.com",
        client_id="client-id",
        client_secret="client-secret",
    )
    today = date.today().strftime("%Y-%m-%d")
    with patch.object(client, "search_incidents", return_value=[]) as search_mock:
        assert client.get_new_incidents() == []
    search_mock.assert_called_once_with(
        start_date=f"{today} 00:00:00",
        end_date=f"{today} 23:59:59",
    )


def test_get_new_incidents_filters_non_new_state():
    client = ServiceNowClient(
        instance_url="https://example.service-now.com",
        client_id="client-id",
        client_secret="client-secret",
    )
    raw = [
        {"number": "INC0000001", "incident_state_display": "New"},
        {"number": "INC0000002", "incident_state_display": "In Progress"},
    ]
    with patch.object(client, "search_incidents", return_value=raw):
        assert len(client.get_new_incidents()) == 2


@pytest.mark.asyncio
async def test_get_new_incidents_router_filters_non_new_state(monkeypatch):
    raw = [
        {"number": "INC0000001", "incident_state_display": "New"},
        {"number": "INC0000002", "incident_state_display": "In Progress"},
    ]
    monkeypatch.setattr(
        "backend.api.routers.sync.new_incident.ServiceNowClient",
        lambda: MagicMock(get_new_incidents=lambda *a, **k: raw),
    )
    monkeypatch.setattr(
        "backend.api.routers.sync.new_incident.asyncio.to_thread",
        AsyncMock(side_effect=lambda fn, *args, **kwargs: fn(*args) if callable(fn) else fn),
    )

    incidents = await _get_new_incidents()
    assert len(incidents) == 1
    assert incidents[0]["incident_number"] == "INC0000001"


@pytest.mark.asyncio
async def test_get_new_incidents_router_maps_search_results(monkeypatch):
    raw = [{
        "number": "INC0000001",
        "short_description": "Disk full",
        "opened_at": f"{date.today().isoformat()} 10:00:00",
        "incident_state_display": "New",
    }]
    monkeypatch.setattr(
        "backend.api.routers.sync.new_incident.ServiceNowClient",
        lambda: MagicMock(get_new_incidents=lambda *a, **k: raw),
    )
    monkeypatch.setattr(
        "backend.api.routers.sync.new_incident.asyncio.to_thread",
        AsyncMock(side_effect=lambda fn, *args, **kwargs: fn(*args) if callable(fn) else fn),
    )

    incidents = await _get_new_incidents()
    assert len(incidents) == 1
    assert incidents[0]["incident_number"] == "INC0000001"
    assert incidents[0]["state"] == "New"

def test_map_detailed_to_row():
    today = date.today().strftime("%Y-%m-%d")
    mapped = map_detailed_to_row(_detailed_payload(today), default_state="New")
    assert mapped["category"] == "Software"
    assert mapped["assigned_to"] == "Jane Analyst"
    assert mapped["opened_by"] == "John Caller"
    assert mapped["cmdb_ci"] == "GK POS"
    assert mapped["description"] is None
    assert mapped["state"] == "New"
    assert mapped["opened_at"] == datetime.strptime(f"{today} 14:50:00", "%Y-%m-%d %H:%M:%S")

def test_snapshot_upsert_sql_includes_incident_columns():
    for col in (
        "assigned_to", "opened_by", "assignment_group", "has_kb_article",
        "embedding", "embedding_text", "description", "work_notes",
    ):
        assert col in UPSERT_SNAPSHOT_SQL
    assert "sync_date" in UPSERT_SNAPSHOT_SQL
    assert len(INCIDENT_ROW_COLUMNS) == 52

@pytest.mark.asyncio
async def test_batch_upsert_counts_insert_and_update():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(side_effect=[{"inserted": True}, {"inserted": False}])
    sample = [
        {"incident_number": "INC0000001", "short_description": "A", "state": "New", "has_kb_article": False},
        {"incident_number": "INC0000002", "short_description": "B", "state": "New", "has_kb_article": True},
    ]
    inserted, updated = await batch_upsert_snapshots(conn, sample, date(2026, 7, 2))
    assert inserted == 1
    assert updated == 1

@pytest.mark.asyncio
async def test_mark_incident_analyzed_updates_row():
    conn = AsyncMock()
    pool = _mock_pool(conn)

    await _mark_incident_analyzed(pool, "INC0000001")

    conn.execute.assert_awaited_once()
    sql = conn.execute.await_args.args[0]
    assert "is_analyzed = TRUE" in sql
    assert "sync_date" not in sql.lower()
    assert conn.execute.await_args.args[1:] == ("INC0000001",)

@pytest.mark.asyncio
async def test_analyze_and_comment_marks_analyzed_on_success(monkeypatch):
    payload = _detailed_payload()
    analyze_mock = AsyncMock(return_value={"confidence_score": 0.85})
    monkeypatch.setattr(
        "backend.api.routers.sync.new_incident._build_ticket_json_from_sn",
        AsyncMock(return_value={"number": "INC2387407"}),
    )
    monkeypatch.setattr(
        "backend.api.routers.sync.new_incident.analyze_ticket.__wrapped__",
        analyze_mock,
    )
    monkeypatch.setattr(
        "backend.api.routers.sync.new_incident.asyncio.to_thread",
        AsyncMock(return_value=True),
    )
    mark_mock = AsyncMock()
    monkeypatch.setattr(
        "backend.api.routers.sync.new_incident._mark_incident_analyzed",
        mark_mock,
    )

    posted, failed = await _analyze_and_comment(
        MagicMock(),
        MagicMock(),
        [payload],
        pool=MagicMock(),
    )

    assert posted == 1
    assert failed == 0
    mark_mock.assert_awaited_once()
    assert mark_mock.await_args.args[1] == "INC2387407"

@pytest.mark.asyncio
async def test_new_incidents_run_uses_detailed_fetch(monkeypatch):
    today = date.today().strftime("%Y-%m-%d")
    detailed_row = {
        "incident_number": "INC0000001",
        "sys_id": "sys1",
        "short_description": "Test",
        "opened_at": f"{today} 10:00:00",
        "cmdb_ci": "GK POS",
        "category": "Software",
        "state": "New",
        "priority": "3 - Moderate",
        "assignment_group": "Service Desk",
        "assigned_to": "Jane Analyst",
        "opened_by": "John Caller",
        "has_kb_article": True,
        "embedding": "[0.1]",
        "embedding_text": "Issue: Test",
        "split_group": "synced",
    }
    fetch_mock = AsyncMock(return_value=[_detailed_payload(today)])
    monkeypatch.setattr(
        "backend.api.routers.sync.new_incident.fetch_incidents_detailed",
        fetch_mock,
    )
    monkeypatch.setattr(
        "backend.api.routers.sync.new_incident.enrich_incident_row",
        AsyncMock(return_value=(detailed_row, 1, 1)),
    )
    analyze_comment_mock = AsyncMock(return_value=(1, 0))
    monkeypatch.setattr(
        "backend.api.routers.sync.new_incident._analyze_and_comment",
        analyze_comment_mock,
    )
    monkeypatch.setattr(
        "backend.api.schedulers.new_incident.refresh_next_run_async",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "backend.api.routers.sync.new_incident.ServiceNowClient",
        lambda: MagicMock(),
    )

    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=True)
    conn.execute = AsyncMock()
    conn.fetchrow = AsyncMock(side_effect=[
        {"inserted": True},
        {"db_count": 1, "last_synced_at": datetime(2026, 7, 2, 12, 0)},
    ])
    monkeypatch.setattr(
        "backend.api.routers.sync.new_incident.get_pool",
        AsyncMock(return_value=_mock_pool(conn)),
    )

    result = await new_incidents_run.__wrapped__(
        request=MagicMock(),
        req=NewIncidentsRunRequest(incident_numbers=["INC0000001"]),
    )
    assert result["inserted"] == 1
    assert result["total"] == 1
    assert result["comments_posted"] == 1
    assert result["comments_failed"] == 0
    fetch_mock.assert_awaited_once()
    assert fetch_mock.await_args.kwargs["include_kb_articles"] is True
    analyze_comment_mock.assert_awaited_once()

def _get_or_skip(client: httpx.Client, method: str, url: str, **kwargs) -> httpx.Response:
    try:
        return client.request(method, url, **kwargs)
    except httpx.ConnectError:
        pytest.skip("Backend not reachable")

def test_preview_and_run_integration(client: httpx.Client):
    preview = _get_or_skip(client, "GET", PREVIEW_URL, timeout=20.0)
    if preview.status_code == 502:
        pytest.skip("ServiceNow not configured")
    assert preview.status_code == 200
    incidents = preview.json().get("incidents", [])
    numbers = [inc["incident_number"] for inc in incidents]

    response = _get_or_skip(
        client,
        "POST",
        RUN_URL,
        json={"incident_numbers": numbers},
        timeout=120.0,
    )
    assert response.status_code == 200
