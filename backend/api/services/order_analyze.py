"""
Sales Order Analyze — local DB lookup + LLM summarization.

Finds incidents that explicitly reference a sales order number in
rexus_incidents_v3 / rexus_incidents_new, extracts INCTASK / PRB / alt orders,
and generates two-line summaries + cross-incident summary via the order prompt.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from backend.api.models.analyze import (
    OrderAnalyzeResponse,
    OrderAnalyzeSummary,
    OrderIncidentCard,
)
from backend.api.utils.llm_provider import chat_complete, get_chat_model
from backend.api.utils.token_tracker import track_usage

logger = logging.getLogger(__name__)

_ORDER_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "order_analyze.txt"
_MAX_INCIDENTS = 40
_MAX_WORK_NOTES_FOR_LLM = 4000
_MAX_DESCRIPTION_FOR_LLM = 1500

_INCTASK_RE = re.compile(r"\bINCTASK\d+\b", re.IGNORECASE)
_PRB_RE = re.compile(r"\bPRB\d{5,}\b", re.IGNORECASE)
# Alternate sales-order-like tokens: 8–12 digit runs (exclude queried SO later)
_ALT_ORDER_RE = re.compile(r"\b(\d{8,12})\b")


def _load_order_prompt(order_number: str) -> str:
    raw = _ORDER_PROMPT_PATH.read_text(encoding="utf-8")
    return (
        raw.replace("{{SO_NUMBER}}", order_number)
        .replace("{{5073352821}}", order_number)
    )


def _sanitize_field(text: str, max_len: int = 2000) -> str:
    if not text:
        return ""
    return str(text)[:max_len]


def _combined_text(row: dict[str, Any]) -> str:
    parts = [
        row.get("short_description") or "",
        row.get("description") or "",
        row.get("work_notes") or "",
        row.get("close_notes") or "",
        row.get("comments") or "",
    ]
    return "\n".join(parts)


def _so_appears_verbatim(order_number: str, row: dict[str, Any]) -> bool:
    """Eligibility: SO in short_description, description, or work_notes, or equals u_order_number."""
    so = order_number.strip()
    if not so:
        return False
    u_order = (row.get("u_order_number") or "").strip()
    if u_order == so:
        return True
    for field in ("short_description", "description", "work_notes"):
        val = row.get(field) or ""
        if so in val:
            return True
    return False


def extract_inc_tasks(text: str) -> list[str]:
    found = sorted(set(m.upper() for m in _INCTASK_RE.findall(text or "")))
    return found


def extract_problem_refs(row: dict[str, Any], text: str) -> list[str]:
    refs: set[str] = set()
    pid = (row.get("problem_id") or "").strip()
    if pid:
        # Column may be "PRB0012345" or display text containing it
        for m in _PRB_RE.findall(pid):
            refs.add(m.upper())
        if re.match(r"^PRB\d+$", pid, re.IGNORECASE):
            refs.add(pid.upper())
    for m in _PRB_RE.findall(text or ""):
        refs.add(m.upper())
    return sorted(refs)


def extract_alternate_orders(order_number: str, text: str) -> list[str]:
    so = order_number.strip()
    alts: set[str] = set()
    for m in _ALT_ORDER_RE.findall(text or ""):
        if m != so:
            alts.add(m)
    return sorted(alts)


async def _table_columns(conn, table: str) -> set[str]:
    rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        """,
        table,
    )
    return {r["column_name"] for r in rows}


def _select_expr(col: str, cols: set[str], pg_type: str = "text") -> str:
    if col in cols:
        return col
    return f"NULL::{pg_type} AS {col}"


def _build_order_where(cols: set[str]) -> tuple[str, list[str]]:
    """Build WHERE clause and which params are needed: 'so' and/or 'pattern'."""
    clauses: list[str] = []
    kinds: list[str] = []
    if "u_order_number" in cols:
        clauses.append(f"u_order_number = ${len(kinds) + 1}")
        kinds.append("so")
    if "short_description" in cols:
        clauses.append(f"short_description ILIKE ${len(kinds) + 1}")
        kinds.append("pattern")
    if "description" in cols:
        clauses.append(f"description ILIKE ${len(kinds) + 1}")
        kinds.append("pattern")
    if "work_notes" in cols:
        clauses.append(f"work_notes ILIKE ${len(kinds) + 1}")
        kinds.append("pattern")
    if not clauses:
        return "FALSE", []
    return " OR ".join(clauses), kinds


async def _fetch_table_for_order(
    conn,
    table: str,
    cols: set[str],
    so: str,
    pattern: str,
    source_priority: int,
) -> list[dict[str, Any]]:
    where, param_kinds = _build_order_where(cols)
    source_label = "v3" if table.endswith("_v3") else "new"
    sql = f"""
        SELECT
            incident_number,
            {_select_expr("state", cols)},
            {_select_expr("short_description", cols)},
            {_select_expr("description", cols)},
            {_select_expr("work_notes", cols)},
            {_select_expr("close_notes", cols)},
            {_select_expr("comments", cols)},
            {_select_expr("problem_id", cols)},
            {_select_expr("u_order_number", cols)},
            {_select_expr("opened_at", cols, "timestamp")},
            {_select_expr("closed_at", cols, "timestamp")},
            '{source_label}' AS source_table,
            {source_priority} AS source_priority
        FROM {table}
        WHERE {where}
    """
    params = [so if kind == "so" else pattern for kind in param_kinds]
    rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows]


async def fetch_incidents_for_order(conn, order_number: str) -> list[dict[str, Any]]:
    """
    Query v3 + new tables for rows that may reference the order.
    Column lists are introspected so slim snapshot tables (e.g. rexus_incidents_new)
    without description/work_notes still work.
    """
    so = order_number.strip()
    pattern = f"%{so}%"

    all_rows: list[dict[str, Any]] = []

    v3_cols = await _table_columns(conn, "rexus_incidents_v3")
    all_rows.extend(
        await _fetch_table_for_order(conn, "rexus_incidents_v3", v3_cols, so, pattern, 1)
    )

    new_exists = await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'rexus_incidents_new'
        )
        """
    )
    if new_exists:
        new_cols = await _table_columns(conn, "rexus_incidents_new")
        all_rows.extend(
            await _fetch_table_for_order(conn, "rexus_incidents_new", new_cols, so, pattern, 2)
        )

    def _sort_key(row: dict[str, Any]) -> str:
        opened = row.get("opened_at")
        if opened is None:
            return ""
        return opened.isoformat() if hasattr(opened, "isoformat") else str(opened)

    all_rows.sort(key=_sort_key, reverse=True)
    return all_rows[: _MAX_INCIDENTS * 3]


def dedupe_and_filter(order_number: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep eligible incidents; prefer v3 over new; prefer richer work_notes."""
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not _so_appears_verbatim(order_number, row):
            continue
        num = (row.get("incident_number") or "").strip().upper()
        if not num:
            continue
        existing = best.get(num)
        if existing is None:
            best[num] = row
            continue
        # Prefer longer work_notes, then v3 (source_priority 1)
        existing_notes = len(existing.get("work_notes") or "")
        new_notes = len(row.get("work_notes") or "")
        if new_notes > existing_notes:
            best[num] = row
        elif new_notes == existing_notes and (row.get("source_priority") or 99) < (
            existing.get("source_priority") or 99
        ):
            best[num] = row

    result = list(best.values())
    result.sort(key=lambda r: r.get("opened_at") or "", reverse=True)
    return result[:_MAX_INCIDENTS]


def build_extracted_cards(order_number: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic extractions + fields for LLM enrichment."""
    cards: list[dict[str, Any]] = []
    for row in rows:
        text = _combined_text(row)
        tasks = extract_inc_tasks(text)
        opened = row.get("opened_at")
        cards.append({
            "incident_number": (row.get("incident_number") or "").strip().upper(),
            "status": (row.get("state") or "").strip() or "Unknown",
            "short_description": (row.get("short_description") or "").strip(),
            "opened_at": opened.isoformat() if hasattr(opened, "isoformat") else (str(opened) if opened else None),
            "inc_tasks": tasks,
            "alternate_orders": extract_alternate_orders(order_number, text),
            "problem_refs": extract_problem_refs(row, text),
            # Server-side only for LLM — stripped before response
            "_short_description": _sanitize_field(row.get("short_description") or "", 500),
            "_description": _sanitize_field(row.get("description") or "", _MAX_DESCRIPTION_FOR_LLM),
            "_work_notes": _sanitize_field(row.get("work_notes") or "", _MAX_WORK_NOTES_FOR_LLM),
            "_close_notes": _sanitize_field(row.get("close_notes") or "", 1000),
        })
    return cards


def _fallback_two_line(card: dict[str, Any]) -> list[str]:
    sd = (card.get("short_description") or "").strip()
    close = (card.get("_close_notes") or "").strip()
    line1 = sd[:220] if sd else "No short description available."
    line2 = (close[:220] if close else "See work notes for investigation details.")
    return [line1, line2]


def _parse_llm_json(content: str) -> Optional[dict]:
    if not content:
        return None
    text = content.strip()
    # Strip markdown fences if present
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find outermost object
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


async def generate_order_summaries(
    pool,
    order_number: str,
    cards: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], OrderAnalyzeSummary]:
    """Call LLM with order prompt + incident payloads; return enriched cards + summary."""
    if not cards:
        return [], OrderAnalyzeSummary()

    rules = _load_order_prompt(order_number)
    payload_incidents = []
    for c in cards:
        payload_incidents.append({
            "incident_number": c["incident_number"],
            "status": c["status"],
            "short_description": c.get("_short_description", ""),
            "description": c.get("_description", ""),
            "work_notes": c.get("_work_notes", ""),
            "close_notes": c.get("_close_notes", ""),
            "inc_tasks": c.get("inc_tasks") or [],
            "alternate_orders": c.get("alternate_orders") or [],
            "problem_refs": c.get("problem_refs") or [],
        })

    system = (
        "You are a Support Analyst assistant for Discount Tire ServiceNow incidents. "
        "Follow the canonical rules exactly. Respond with ONLY valid JSON matching this schema:\n"
        "{\n"
        '  "incidents": [\n'
        "    {\n"
        '      "incident_number": "INC...",\n'
        '      "two_line_summary": ["line1", "line2"]\n'
        "    }\n"
        "  ],\n"
        '  "summary": {\n'
        '    "analysis": "...",\n'
        '    "accounting_actions": "...",\n'
        '    "payment_activities": "...",\n'
        '    "solutions": "...",\n'
        '    "system_states": "..."\n'
        "  }\n"
        "}\n"
        "Do not return citations, sources, trace markers, or links. "
        "Include a two_line_summary for every provided incident_number."
    )
    user = (
        f"{rules}\n\n"
        f"Eligible incidents already filtered for verbatim sales order {order_number}:\n"
        f"{json.dumps(payload_incidents, default=str)}\n\n"
        "Produce the JSON response now."
    )

    try:
        resp = await chat_complete(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=3500,
            temperature=0.1,
        )
        content = resp.choices[0].message.content or ""
        try:
            await track_usage(
                pool,
                "completion",
                get_chat_model(),
                getattr(resp.usage, "prompt_tokens", 0) or 0,
                getattr(resp.usage, "completion_tokens", 0) or 0,
                endpoint="/analyze/order",
            )
        except Exception as e:
            logger.warning("token track failed for /analyze/order: %s", e)

        parsed = _parse_llm_json(content)
        summary = OrderAnalyzeSummary()
        summaries_by_inc: dict[str, list[str]] = {}
        if parsed:
            for item in parsed.get("incidents") or []:
                if not isinstance(item, dict):
                    continue
                num = (item.get("incident_number") or "").strip().upper()
                tls = item.get("two_line_summary") or []
                if isinstance(tls, str):
                    tls = [p.strip() for p in tls.split("\n") if p.strip()][:2]
                if isinstance(tls, list):
                    summaries_by_inc[num] = [str(x).strip() for x in tls if str(x).strip()][:2]
            s = parsed.get("summary") or {}
            if isinstance(s, dict):
                summary = OrderAnalyzeSummary(
                    analysis=str(s.get("analysis") or "").strip(),
                    accounting_actions=str(s.get("accounting_actions") or "").strip(),
                    payment_activities=str(s.get("payment_activities") or "").strip(),
                    solutions=str(s.get("solutions") or "").strip(),
                    system_states=str(s.get("system_states") or "").strip(),
                )
    except Exception as e:
        logger.exception("Order analyze LLM failed: %s", e)
        summaries_by_inc = {}
        summary = OrderAnalyzeSummary(
            analysis="Summary generation is temporarily unavailable. Incident details below are from local records.",
        )

    enriched: list[dict[str, Any]] = []
    for c in cards:
        tls = summaries_by_inc.get(c["incident_number"]) or _fallback_two_line(c)
        if len(tls) < 2:
            tls = (tls + _fallback_two_line(c))[:2]
        out = {k: v for k, v in c.items() if not k.startswith("_")}
        out["two_line_summary"] = tls
        # Ensure empty tasks show as empty list; UI will display "No INC task found"
        out["inc_tasks"] = c.get("inc_tasks") or []
        enriched.append(out)

    return enriched, summary


async def analyze_order(pool, order_number: str) -> OrderAnalyzeResponse:
    so = order_number.strip()
    async with pool.acquire() as conn:
        rows = await fetch_incidents_for_order(conn, so)

    eligible = dedupe_and_filter(so, rows)
    if not eligible:
        return OrderAnalyzeResponse(
            order_number=so,
            incident_count=0,
            message=f"No related incidents found for sales order {so}.",
            incidents=[],
            summary=OrderAnalyzeSummary(),
        )

    cards = build_extracted_cards(so, eligible)
    enriched, summary = await generate_order_summaries(pool, so, cards)
    incident_models = [OrderIncidentCard(**c) for c in enriched]

    return OrderAnalyzeResponse(
        order_number=so,
        incident_count=len(incident_models),
        message=f"Found {len(incident_models)} eligible incident(s) for sales order {so}.",
        incidents=incident_models,
        summary=summary,
    )
