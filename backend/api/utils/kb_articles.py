"""
Shared KB / knowledge article helpers for sync and analyze.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
from typing import Any

from backend.api.database import get_pool
from backend.api.utils.pdf_parser import extract_plain_text_from_pdf_bytes

logger = logging.getLogger(__name__)

MAX_KB_TEXT_FOR_SUMMARY = 14_000
MAX_KB_TEXT_FOR_LLM_PROMPT = 8_000


def build_kb_url(number: str) -> str:
    """Construct a public ServiceNow KB article view URL."""
    instance = os.getenv("SERVICENOW_INSTANCE", "").rstrip("/")
    if not instance or not number:
        return ""
    return f"{instance}/kb_view.do?sysparm_article={number}"


def _kb_number_from_item(ka: dict) -> str:
    """Resolve KB article number from ServiceNow detailed/search/attached_knowledge shapes."""
    for key in (
        "number",
        "knowledge_article_number",
        "kb_number",
        "article_number",
        "article",
        "number_display",
        "knowledge_article_number_display",
    ):
        val = ka.get(key)
        if val is not None and str(val).strip():
            return str(val).strip().upper()
    return ""


def _kb_description_from_item(ka: dict) -> str:
    for key in ("short_description", "kb_description", "title", "description", "display_value"):
        val = ka.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _collect_kb_raw_lists(data: dict) -> list[list]:
    """Gather KB article arrays from all known locations in a ServiceNow response."""
    lists: list[list] = []
    for key in ("kb_articles", "attached_knowledge"):
        raw = data.get(key)
        if isinstance(raw, list) and raw:
            lists.append(raw)
    inc = data.get("incident")
    if isinstance(inc, dict):
        for key in ("kb_articles", "attached_knowledge"):
            raw = inc.get(key)
            if isinstance(raw, list) and raw:
                lists.append(raw)
    return lists


def extract_kb_articles(data: dict) -> list[dict]:
    """Pull KB articles from a ServiceNow response (detailed or search shape)."""
    out: list[dict] = []
    seen: set[str] = set()
    for raw_list in _collect_kb_raw_lists(data):
        for ka in raw_list:
            if not isinstance(ka, dict):
                continue
            number = _kb_number_from_item(ka)
            if not number or number in seen:
                continue
            seen.add(number)
            out.append({
                "sys_id": ka.get("sys_id", ""),
                "number": number,
                "short_description": _kb_description_from_item(ka),
                "kb_category_display": ka.get("kb_category_display", ""),
                "attached_on": ka.get("attached_on", ""),
                "url": build_kb_url(number),
            })
    return out


def normalize_kb_article(ka: dict) -> dict | None:
    """Normalize KB article dicts from ServiceNow, ticket JSON, or the mapping table."""
    number = (ka.get("number") or ka.get("knowledge_article_number") or "").strip().upper()
    if not number:
        return None
    return {
        "sys_id": ka.get("sys_id", ""),
        "number": number,
        "short_description": ka.get("short_description") or ka.get("kb_description") or "",
        "kb_category_display": ka.get("kb_category_display", ""),
        "attached_on": ka.get("attached_on", ""),
        "url": ka.get("url") or build_kb_url(number),
        "source": ka.get("source", "servicenow"),
    }


async def get_kb_article_fallbacks(incident_number: str) -> list[dict]:
    """Load KB article mappings from rexus_kb_article_incident_mapping."""
    if not incident_number:
        return []

    incident_number = incident_number.strip().upper()

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT knowledge_article_number, kb_description
                   FROM rexus_kb_article_incident_mapping
                   WHERE UPPER(TRIM(incident_number)) = $1
                   ORDER BY knowledge_article_number""",
                incident_number,
            )
    except Exception as e:
        logger.warning("KB article fallback lookup failed for %s: %s", incident_number, e)
        return []

    articles: list[dict] = []
    for row in rows:
        number = row["knowledge_article_number"]
        articles.append({
            "sys_id": "",
            "number": number,
            "short_description": row["kb_description"] or "",
            "kb_category_display": "",
            "attached_on": "",
            "url": build_kb_url(number),
            "source": "mapping_table",
        })
    return articles


async def get_kb_mappings_for_incidents(incident_numbers: list[str]) -> dict[str, list[dict]]:
    """Batch-load mapping rows keyed by uppercased incident number."""
    if not incident_numbers:
        return {}

    normalized = list({n.strip().upper() for n in incident_numbers if n and n.strip()})
    if not normalized:
        return {}

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT incident_number, knowledge_article_number, kb_description
                   FROM rexus_kb_article_incident_mapping
                   WHERE UPPER(TRIM(incident_number)) = ANY($1::text[])
                   ORDER BY incident_number, knowledge_article_number""",
                normalized,
            )
    except Exception as e:
        logger.warning("KB batch mapping lookup failed: %s", e)
        return {}

    result: dict[str, list[dict]] = {}
    for row in rows:
        inc = row["incident_number"].strip().upper()
        result.setdefault(inc, []).append({
            "knowledge_article_number": row["knowledge_article_number"],
            "kb_description": row["kb_description"] or "",
        })
    return result


async def resolve_kb_articles(
    ticket_kb: list,
    incident_number: str,
    pdf_cache: dict[str, bytes | None] | None = None,
) -> list[dict]:
    """Merge KB articles from ticket JSON with mapping table; optionally attach PDFs."""
    articles: list[dict] = []
    seen: set[str] = set()

    for ka in ticket_kb:
        if not isinstance(ka, dict):
            continue
        normalized = normalize_kb_article(ka)
        if normalized and normalized["number"] not in seen:
            seen.add(normalized["number"])
            articles.append(normalized)

    if incident_number:
        for ka in await get_kb_article_fallbacks(incident_number):
            if ka["number"] not in seen:
                seen.add(ka["number"])
                articles.append(ka)

    if pdf_cache is not None:
        for art in articles:
            number = (art.get("number") or "").strip().upper()
            if not number:
                art.pop("pdf_base64", None)
                art["has_pdf"] = False
                continue
            pdf_bytes = await load_kb_article_pdf_cached(number, pdf_cache)
            if pdf_bytes:
                art["pdf_base64"] = base64.b64encode(pdf_bytes).decode("ascii")
                art["has_pdf"] = True
            else:
                art.pop("pdf_base64", None)
                art["has_pdf"] = False

    return articles


def _score_kb_candidates_from_similar(
    incident_details: list[dict],
    mappings: dict[str, list[dict]],
) -> list[tuple[float, str, dict]]:
    """
    Rank KB articles by highest similar-incident match (similarity_score).
    Returns list of (score, source_incident, mapping_row) sorted descending.
    """
    best: dict[str, tuple[float, str, dict]] = {}

    for inc in incident_details:
        inc_num = (inc.get("incident_number") or "").strip().upper()
        if not inc_num:
            continue
        score = float(inc.get("similarity_score") or 0)
        for row in mappings.get(inc_num, []):
            kb_num = (row.get("knowledge_article_number") or "").strip().upper()
            if not kb_num:
                continue
            prev = best.get(kb_num)
            if prev is None or score > prev[0]:
                best[kb_num] = (score, inc_num, row)

    ranked = sorted(best.values(), key=lambda x: -x[0])
    return ranked


def _normalize_ticket_kb_list(ticket_kb: list) -> list[dict]:
    """Dedupe and normalize KB articles from ticket_json.kb_articles."""
    articles: list[dict] = []
    seen: set[str] = set()
    for ka in ticket_kb:
        if not isinstance(ka, dict):
            continue
        normalized = normalize_kb_article(ka)
        if normalized and normalized["number"] not in seen:
            seen.add(normalized["number"])
            articles.append(normalized)
    return articles


async def pick_kb_for_analysis(
    incoming_number: str | None,
    ticket_kb: list,
    incident_details: list[dict],
) -> tuple[list[dict], dict[str, Any]]:
    """
    Pick KB for analyze: use all articles on the incoming ticket when present;
    otherwise highest vector similarity among similar incidents with KB mappings.
    """
    meta: dict[str, Any] = {}

    incident_articles = _normalize_ticket_kb_list(ticket_kb)
    if incident_articles:
        meta["kb_source"] = "incident"
        return incident_articles, meta

    incoming = (incoming_number or "").strip().upper()

    similar_details = [
        inc for inc in incident_details
        if (inc.get("incident_number") or "").strip().upper() != incoming
    ] if incoming else list(incident_details)

    similar_numbers = [
        (inc.get("incident_number") or "").strip().upper()
        for inc in similar_details
        if inc.get("incident_number")
    ]
    if not similar_numbers:
        return [], meta

    mappings = await get_kb_mappings_for_incidents(similar_numbers)
    ranked = _score_kb_candidates_from_similar(similar_details, mappings)
    if not ranked:
        return [], meta

    score, source_incident, row = ranked[0]
    match_percent = round(min(score, 1.0) * 100, 1)
    normalized = normalize_kb_article({
        "knowledge_article_number": row["knowledge_article_number"],
        "kb_description": row["kb_description"],
        "source": "mapping_table",
    })
    if not normalized:
        return [], meta

    normalized["match_percent"] = match_percent
    normalized["matched_via_incident"] = source_incident
    meta["kb_source"] = "similar"
    meta["kb_source_incident"] = source_incident
    meta["kb_match_percent"] = match_percent

    return [normalized], meta


def _merge_sn_kb_metadata(article: dict, sn_data: dict) -> None:
    """Merge ServiceNow knowledge article fields into a normalized article dict."""
    if not sn_data:
        return
    if sn_data.get("sys_id"):
        article["sys_id"] = sn_data["sys_id"]
    sn_num = _kb_number_from_item(sn_data) if isinstance(sn_data, dict) else ""
    if sn_num:
        article["number"] = sn_num
    desc = _kb_description_from_item(sn_data)
    if desc:
        article["short_description"] = desc
    if sn_data.get("kb_category_display"):
        article["kb_category_display"] = sn_data["kb_category_display"]
    if sn_data.get("kb_title"):
        article["kb_title"] = sn_data["kb_title"]
    article["source"] = "servicenow"


async def enrich_kb_articles_from_servicenow(
    articles: list[dict],
    pdf_cache: dict[str, bytes | None] | None = None,
) -> list[dict]:
    """Fetch each KB article from ServiceNow and attach metadata + PDF when available."""
    if not articles:
        return []

    cache = pdf_cache if pdf_cache is not None else {}
    enriched: list[dict] = []

    for art in articles:
        number = (art.get("number") or "").strip().upper()
        if not number:
            continue
        merged = dict(art)
        try:
            sn_data = await asyncio.to_thread(_fetch_kb_metadata_sync, number)
            _merge_sn_kb_metadata(merged, sn_data or {})
        except Exception as e:
            logger.warning("ServiceNow KB metadata fetch failed for %s: %s", number, e)

        pdf_bytes = await load_kb_article_pdf_cached(number, cache)
        if pdf_bytes:
            merged["pdf_base64"] = base64.b64encode(pdf_bytes).decode("ascii")
            merged["has_pdf"] = True
        else:
            merged.pop("pdf_base64", None)
            merged["has_pdf"] = False

        if not merged.get("url"):
            merged["url"] = build_kb_url(number)
        enriched.append(merged)

    return enriched


def _fetch_kb_metadata_sync(kb_number: str) -> dict | None:
    from backend.services.servicenow_client import ServiceNowClient

    try:
        client = ServiceNowClient()
    except ValueError:
        return None
    data = client.get_knowledge_article(kb_number)
    return data if isinstance(data, dict) else None


def fetch_kb_pdf_from_servicenow(kb_number: str) -> bytes | None:
    """Sync: load KB PDF from ServiceNow."""
    from backend.services.servicenow_client import ServiceNowClient

    try:
        sn_client = ServiceNowClient()
    except ValueError:
        return None

    data = sn_client.get_knowledge_article(kb_number)
    if not data:
        return None

    pdf_meta = data.get("pdf")
    if not isinstance(pdf_meta, dict):
        return None
    pdf_b64 = pdf_meta.get("base64")
    if not pdf_b64:
        return None

    try:
        pdf_bytes = base64.b64decode(pdf_b64, validate=True)
        if pdf_bytes.startswith(b"%PDF"):
            return pdf_bytes
    except Exception:
        return None
    return None


async def load_kb_article_pdf(kb_number: str) -> bytes | None:
    """KB article PDF: ServiceNow API first, kb_articles table fallback."""
    kb_number = kb_number.strip().upper()
    if not kb_number:
        return None

    sn_pdf = await asyncio.to_thread(fetch_kb_pdf_from_servicenow, kb_number)
    if sn_pdf:
        logger.warning("KB article %s PDF fetched from ServiceNow", kb_number)
        return sn_pdf

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT kb_data FROM kb_articles
                   WHERE UPPER(TRIM(kb_article_no)) = $1""",
                kb_number,
            )
        if row and row["kb_data"]:
            pdf_bytes = base64.b64decode(row["kb_data"], validate=True)
            if pdf_bytes.startswith(b"%PDF"):
                logger.warning("KB article %s PDF fetched from database (kb_articles table)", kb_number)
                return pdf_bytes
    except ValueError:
        raise
    except Exception as e:
        logger.warning("KB article %s database PDF lookup failed: %s", kb_number, e)
    return None


async def load_kb_article_pdf_cached(
    kb_number: str,
    pdf_cache: dict[str, bytes | None],
) -> bytes | None:
    key = kb_number.strip().upper()
    if not key:
        return None
    if key not in pdf_cache:
        pdf_cache[key] = await load_kb_article_pdf(key)
    return pdf_cache[key]


async def fetch_kb_article_text(
    kb_number: str,
    pdf_cache: dict[str, bytes | None],
) -> str:
    """Plain text from cached KB article PDF bytes."""
    pdf_bytes = await load_kb_article_pdf_cached(kb_number, pdf_cache)
    if not pdf_bytes:
        return ""
    extracted = await asyncio.to_thread(extract_plain_text_from_pdf_bytes, pdf_bytes)
    if not extracted.strip():
        return ""
    return extracted[:MAX_KB_TEXT_FOR_SUMMARY]


def _html_to_plain_text(html: str) -> str:
    """Best-effort strip of ServiceNow kb_knowledge HTML body."""
    if not html:
        return ""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


async def fetch_kb_article_summary_text(
    kb_number: str,
    pdf_cache: dict[str, bytes | None],
) -> str:
    """Plain text for playbook: PDF extract first, then ServiceNow kb_knowledge HTML body."""
    text = await fetch_kb_article_text(kb_number, pdf_cache)
    if text.strip():
        return text

    try:
        sn_data = await asyncio.to_thread(_fetch_kb_metadata_sync, kb_number)
    except Exception as e:
        logger.warning("KB summary SN fetch failed for %s: %s", kb_number, e)
        sn_data = None

    if isinstance(sn_data, dict):
        raw = sn_data.get("text") or ""
        if raw:
            plain = _html_to_plain_text(str(raw))
            if plain:
                return plain[:MAX_KB_TEXT_FOR_SUMMARY]
    return ""


def _format_kb_playbook_static(article: dict, body: str) -> str:
    """Markdown playbook from KB metadata + source text (no LLM)."""
    number = article.get("number", "")
    title = article.get("short_description") or article.get("kb_title") or number
    url = article.get("url", "")
    matched = article.get("matched_via_incident", "")
    match_pct = article.get("match_percent")
    link = f"[{number}]({url})" if url and number else (number or "Knowledge Article")

    match_line = ""
    if matched and match_pct is not None:
        match_line = f"**Matched via:** {matched} ({match_pct:.0f}% similarity to similar incident)\n\n"
    elif matched:
        match_line = f"**Matched via:** {matched}\n\n"

    return (
        f"## Playbook: {title}\n\n"
        f"**Knowledge Article:** {link}\n\n"
        f"{match_line}"
        f"### Summary\n\n"
        f"{body.strip()[:4000]}"
    )


async def _llm_summarize_kb_playbook(
    article: dict,
    source_text: str,
    pool: Any,
) -> str | None:
    """Condense KB source text into a concise engineer playbook."""
    from backend.api.utils.llm_provider import chat_complete, get_chat_model
    from backend.api.utils.token_tracker import track_usage

    number = article.get("number", "")
    title = article.get("short_description") or article.get("kb_title") or number
    matched = article.get("matched_via_incident", "")
    match_pct = article.get("match_percent")
    match_hint = (
        f"Linked from similar incident {matched} ({match_pct:.0f}% match)."
        if matched and match_pct is not None
        else (f"Linked from similar incident {matched}." if matched else "")
    )

    prompt = f"""Summarize this knowledge article into a concise support playbook (max 400 words).

Knowledge article: {number} — {title}
{match_hint}

SOURCE:
{source_text[:MAX_KB_TEXT_FOR_LLM_PROMPT]}

Use this EXACT structure:

## Playbook: {title}

**Knowledge Article:** {number}

**Summary:** 2-4 sentences describing the issue and resolution approach.

**Step-by-Step:**
1. First actionable step
2. Continue with ordered steps

**If That Doesn't Work:** Alternatives or escalation from the article only.

RULES: Only use facts from SOURCE. Reference [{number}] where helpful. Be brief and actionable."""

    model = get_chat_model()
    resp = await chat_complete(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a technical writer for support engineers. "
                    "Summarize knowledge base articles faithfully — no invented steps."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=1200,
        temperature=0.1,
    )
    content = (resp.choices[0].message.content or "").strip()
    if not content:
        return None

    if pool:
        usage = resp.usage
        await track_usage(
            pool,
            "completion",
            model,
            usage.prompt_tokens,
            usage.completion_tokens,
            endpoint="/analyze-kb-playbook",
        )
    return content


async def build_kb_playbook_summary(
    article: dict,
    *,
    pool: Any = None,
) -> tuple[str | None, bool]:
    """
    Build playbook markdown from a KB article when number exists.
    Returns (playbook_text, used_full_article_body).
    """
    number = (article.get("number") or "").strip().upper()
    if not number:
        return None, False

    cache: dict[str, bytes | None] = {}
    body = await fetch_kb_article_summary_text(number, cache)
    used_full = bool(body.strip())

    if not used_full:
        body = (article.get("short_description") or article.get("kb_title") or "").strip()
        if not body:
            return None, False

    if len(body) > 300 and pool is not None:
        try:
            llm_summary = await _llm_summarize_kb_playbook(article, body, pool)
            if llm_summary:
                return llm_summary, used_full
        except Exception as e:
            logger.warning("KB playbook LLM summary failed for %s: %s", number, e)

    return _format_kb_playbook_static(article, body), used_full


async def apply_kb_playbook_to_focused(
    focused_playbook: dict,
    *,
    pool: Any = None,
) -> None:
    """Replace playbook body with KB article summary when a KB number is present."""
    articles = focused_playbook.get("kb_articles") or []
    if not articles:
        return

    art = articles[0]
    if not (art.get("number") or "").strip():
        return

    playbook, used_full = await build_kb_playbook_summary(art, pool=pool)
    if not playbook:
        return

    focused_playbook["playbook"] = playbook
    focused_playbook["playbook_source"] = "knowledge_article"
    if used_full:
        focused_playbook["grounding_score"] = max(
            float(focused_playbook.get("grounding_score") or 0),
            0.88,
        )


async def kb_articles_have_extractable_text(
    kb_articles: list[dict],
    pdf_cache: dict[str, bytes | None],
) -> bool:
    """True if at least one article has non-empty PDF text."""
    for art in kb_articles:
        number = (art.get("number") or "").strip().upper()
        if not number:
            continue
        text = await fetch_kb_article_text(number, pdf_cache)
        if text.strip():
            return True
    return False


async def insert_kb_mappings(conn, incident_number: str, kb_list: list[dict]) -> int:
    """
    Insert KB rows for an incident from ServiceNow (sync import).
    Skips pairs that already exist. Returns count of newly inserted rows.
    """
    if not incident_number or not kb_list:
        return 0

    inc = incident_number.strip().upper()
    numbers: list[str] = []
    descriptions: list[str | None] = []
    for ka in kb_list:
        if not isinstance(ka, dict):
            continue
        number = (
            ka.get("number")
            or ka.get("knowledge_article_number")
            or _kb_number_from_item(ka)
        )
        if isinstance(number, str):
            number = number.strip().upper()
        else:
            number = ""
        if not number:
            continue
        desc = ka.get("short_description") or ka.get("kb_description") or _kb_description_from_item(ka)
        numbers.append(number)
        descriptions.append(desc)

    if not numbers:
        return 0

     try:
        rows = await conn.fetch(
            """INSERT INTO rexus_kb_article_incident_mapping
                   (incident_number, knowledge_article_number, kb_description)
               SELECT $1, ka_num, ka_desc
               FROM unnest($2::text[], $3::text[]) AS t(ka_num, ka_desc)
               ON CONFLICT (incident_number, knowledge_article_number) DO NOTHING
               RETURNING 1""",
            inc,
            numbers,
            descriptions,
        )
    except Exception as e:
        logger.error("%s: error mapping KA article(s) [%s]: %s", inc, ", ".join(numbers), e, exc_info=True,)
        raise
    return len(rows)