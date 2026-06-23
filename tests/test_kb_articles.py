"""
Unit tests for KB article helpers (sync + analyze resolution).
"""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.api.utils.kb_articles import (
    apply_kb_playbook_to_focused,
    build_kb_playbook_summary,
    enrich_kb_articles_from_servicenow,
    extract_kb_articles,
    fetch_kb_article_summary_text,
    insert_kb_mappings,
    load_kb_article_pdf,
    normalize_kb_article,
    pick_kb_for_analysis,
    _format_kb_playbook_static,
    _html_to_plain_text,
    _score_kb_candidates_from_similar,
)


def test_extract_kb_articles_from_top_level():
    data = {
        "kb_articles": [
            {"number": "KB001", "short_description": "Test article", "sys_id": "abc"},
        ],
    }
    articles = extract_kb_articles(data)
    assert len(articles) == 1
    assert articles[0]["number"] == "KB001"
    assert articles[0]["short_description"] == "Test article"


def test_extract_kb_articles_from_incident_nested():
    data = {
        "incident": {
            "kb_articles": [{"number": "KB002", "short_description": "Nested"}],
        },
    }
    articles = extract_kb_articles(data)
    assert len(articles) == 1
    assert articles[0]["number"] == "KB002"


def test_extract_kb_articles_from_attached_knowledge():
    data = {
        "attached_knowledge": [
            {"knowledge_article_number": "KB003", "title": "Attached KB"},
        ],
    }
    articles = extract_kb_articles(data)
    assert len(articles) == 1
    assert articles[0]["number"] == "KB003"
    assert articles[0]["short_description"] == "Attached KB"


def test_normalize_kb_article_mapping_shape():
    art = normalize_kb_article({
        "knowledge_article_number": "kb003",
        "kb_description": "From mapping",
    })
    assert art is not None
    assert art["number"] == "KB003"
    assert art["short_description"] == "From mapping"
    assert art["source"] == "servicenow"


def test_score_kb_candidates_picks_highest_similarity():
    similar = [
        {"incident_number": "INC300", "similarity_score": 0.92},
        {"incident_number": "INC301", "similarity_score": 0.80},
    ]
    mappings = {
        "INC300": [{"knowledge_article_number": "KB200", "kb_description": "A"}],
        "INC301": [{"knowledge_article_number": "KB201", "kb_description": "B"}],
    }
    ranked = _score_kb_candidates_from_similar(similar, mappings)
    assert ranked[0][0] == 0.92
    assert ranked[0][1] == "INC300"
    assert ranked[0][2]["knowledge_article_number"] == "KB200"


@pytest.mark.asyncio
async def test_pick_kb_skips_incoming_incident_mapping():
    """Incoming INC mapping is ignored; KB must come from a similar incident."""
    similar = [{"incident_number": "INC300", "similarity_score": 0.88}]

    with patch(
        "backend.api.utils.kb_articles.get_kb_mappings_for_incidents",
        new_callable=AsyncMock,
    ) as mock_batch:
        mock_batch.return_value = {
            "INC100": [{"knowledge_article_number": "KB100", "kb_description": "Own INC"}],
            "INC300": [{"knowledge_article_number": "KB300", "kb_description": "Similar"}],
        }
        articles, meta = await pick_kb_for_analysis("INC100", [], similar)

    assert len(articles) == 1
    assert articles[0]["number"] == "KB300"
    assert meta["kb_source"] == "similar"
    assert meta["kb_source_incident"] == "INC300"


@pytest.mark.asyncio
async def test_load_kb_article_pdf_logs_servicenow_source(caplog):
    import logging

    caplog.set_level(logging.WARNING, logger="backend.api.utils.kb_articles")
    pdf_bytes = b"%PDF-1.4 fake"

    with patch(
        "backend.api.utils.kb_articles.fetch_kb_pdf_from_servicenow",
        return_value=pdf_bytes,
    ):
        result = await load_kb_article_pdf("KB100")

    assert result == pdf_bytes
    assert "PDF fetched from ServiceNow" in caplog.text
    assert "KB100" in caplog.text


@pytest.mark.asyncio
async def test_load_kb_article_pdf_logs_database_source(caplog):
    import logging

    caplog.set_level(logging.WARNING, logger="backend.api.utils.kb_articles")
    b64_pdf = base64.b64encode(b"%PDF-1.4 from-db").decode("ascii")

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={"kb_data": b64_pdf})
    mock_acquire = MagicMock()
    mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_acquire.__aexit__ = AsyncMock(return_value=None)
    mock_pool = MagicMock()
    mock_pool.acquire.return_value = mock_acquire

    with patch(
        "backend.api.utils.kb_articles.fetch_kb_pdf_from_servicenow",
        return_value=None,
    ), patch(
        "backend.api.utils.kb_articles.get_pool",
        AsyncMock(return_value=mock_pool),
    ):
        result = await load_kb_article_pdf("KB200")

    assert result is not None
    assert result.startswith(b"%PDF")
    assert "PDF fetched from database" in caplog.text
    assert "KB200" in caplog.text


@pytest.mark.asyncio
async def test_pick_kb_similar_highest_match_percent():
    similar = [
        {"incident_number": "INC300", "similarity_score": 0.92},
        {"incident_number": "INC301", "similarity_score": 0.80},
    ]

    with patch(
        "backend.api.utils.kb_articles.get_kb_mappings_for_incidents",
        new_callable=AsyncMock,
    ) as mock_batch:
        mock_batch.return_value = {
            "INC300": [{"knowledge_article_number": "KB200", "kb_description": "Similar KB"}],
            "INC301": [{"knowledge_article_number": "KB201", "kb_description": "Lower"}],
        }
        articles, meta = await pick_kb_for_analysis("INC999", [], similar)

    assert len(articles) == 1
    assert articles[0]["number"] == "KB200"
    assert articles[0]["match_percent"] == 92.0
    assert articles[0]["matched_via_incident"] == "INC300"
    assert meta["kb_source"] == "similar"
    assert meta["kb_source_incident"] == "INC300"
    assert meta["kb_match_percent"] == 92.0


def test_html_to_plain_text_strips_tags():
    html = "<p>Step one</p><br/><p>Step <b>two</b></p>"
    assert "Step one" in _html_to_plain_text(html)
    assert "Step two" in _html_to_plain_text(html)


def test_format_kb_playbook_static_includes_article_number():
    md = _format_kb_playbook_static(
        {
            "number": "KB0020233",
            "short_description": "Mandatory Credit Card",
            "matched_via_incident": "INC300",
            "match_percent": 88.0,
        },
        "Use the payment form to capture card details.",
    )
    assert "KB0020233" in md
    assert "INC300" in md
    assert "Mandatory Credit Card" in md


@pytest.mark.asyncio
async def test_fetch_kb_article_summary_text_from_sn_html():
    with patch(
        "backend.api.utils.kb_articles.fetch_kb_article_text",
        new_callable=AsyncMock,
        return_value="",
    ), patch(
        "backend.api.utils.kb_articles._fetch_kb_metadata_sync",
        return_value={"text": "<p>Refund procedure</p>"},
    ):
        text = await fetch_kb_article_summary_text("KB100", {})
    assert "Refund procedure" in text


@pytest.mark.asyncio
async def test_build_kb_playbook_summary_uses_static_when_short():
    with patch(
        "backend.api.utils.kb_articles.fetch_kb_article_summary_text",
        new_callable=AsyncMock,
        return_value="Short KB note.",
    ):
        playbook, used_full = await build_kb_playbook_summary(
            {"number": "KB001", "short_description": "Title"},
            pool=None,
        )
    assert playbook is not None
    assert "KB001" in playbook
    assert used_full is True


@pytest.mark.asyncio
async def test_apply_kb_playbook_to_focused_replaces_playbook():
    focused = {
        "playbook": "## Old LLM playbook",
        "grounding_score": 0.7,
        "kb_articles": [
            {
                "number": "KB200",
                "short_description": "Similar KB",
                "matched_via_incident": "INC300",
                "match_percent": 90.0,
            },
        ],
    }
    with patch(
        "backend.api.utils.kb_articles.build_kb_playbook_summary",
        new_callable=AsyncMock,
        return_value=("## Playbook: Similar KB\n\n**Summary:** Steps.", True),
    ):
        await apply_kb_playbook_to_focused(focused, pool=None)

    assert focused["playbook_source"] == "knowledge_article"
    assert "Similar KB" in focused["playbook"]
    assert focused["grounding_score"] >= 0.88


@pytest.mark.asyncio
async def test_enrich_kb_articles_attaches_pdf_base64():
    """Analyze flow: enrich adds pdf_base64 when PDF bytes are loaded for the KB number."""
    fake_pdf = b"%PDF-1.4 test"

    with (
        patch(
            "backend.api.utils.kb_articles._fetch_kb_metadata_sync",
            return_value={"number": "KB001", "short_description": "Title"},
        ),
        patch(
            "backend.api.utils.kb_articles.load_kb_article_pdf_cached",
            new_callable=AsyncMock,
            return_value=fake_pdf,
        ),
    ):
        enriched = await enrich_kb_articles_from_servicenow(
            [{"number": "KB001", "short_description": "From mapping", "source": "mapping_table"}],
        )

    assert len(enriched) == 1
    assert enriched[0]["has_pdf"] is True
    assert enriched[0]["pdf_base64"]
    assert enriched[0]["number"] == "KB001"


@pytest.mark.asyncio
async def test_insert_kb_mappings():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[{"?column?": 1}])
    kb_list = [{"number": "KB001", "short_description": "Desc"}]
    count = await insert_kb_mappings(conn, "INC001", kb_list)
    assert count == 1
    conn.fetch.assert_awaited_once()
    args = conn.fetch.await_args[0]
    assert "ON CONFLICT" in args[0]
    assert "NOT EXISTS" not in args[0]
    assert args[1] == "INC001"
    assert args[2] == ["KB001"]
    assert args[3] == ["Desc"]


@pytest.mark.asyncio
async def test_insert_kb_mappings_skips_duplicate():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    kb_list = [{"number": "KB001", "short_description": "Desc"}]
    count = await insert_kb_mappings(conn, "inc001", kb_list)
    assert count == 0
    conn.fetch.assert_awaited_once()
