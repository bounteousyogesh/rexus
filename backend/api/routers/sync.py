"""
REX-US — ServiceNow Sync

Connects to configured ServiceNow instance, checks for delta incidents
(closed tickets not in our database), and allows importing them.

Endpoints:
  GET  /sync/status      - Check what's in SN vs our DB
  GET  /sync/delta       - List incidents in SN not in our DB (grouped by month/week)
  POST /sync/import      - Import a batch of incidents (fetch, embed, insert)
"""

import os
import re
import asyncio
import logging
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field
from fastapi import APIRouter, Query, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from openai import AsyncOpenAI

from backend.api.config import OPENAI_API_KEY
from backend.api.database import get_pool
from backend.api.utils.token_tracker import track_usage

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sync"])
limiter = Limiter(key_func=get_remote_address)

# SEC-015: Configurable maximum number of delta incidents fetched from ServiceNow.
# Prevents runaway memory consumption on large backlogs.
_SYNC_DELTA_MAX = int(os.getenv("SYNC_DELTA_MAX", "2000"))

# ARCH-008: Shared AsyncOpenAI singleton for async handlers
_openai_client: AsyncOpenAI | None = None


def _get_sn_client():
    """Lazy-load ServiceNow client."""
    from backend.services.servicenow_client import ServiceNowClient
    return ServiceNowClient()


def _get_openai() -> AsyncOpenAI:
    """Return shared AsyncOpenAI singleton (ARCH-008: use async client in async handlers)."""
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


# ── PII/generic cleaning for v2 embeddings ─────────────────────
# ARCH-005: _clean_for_embedding is intentionally duplicated here (vs analyze.py)
# because it uses a stricter PII scrub (removes more tokens).  If the two
# implementations drift, consider extracting to backend/api/utils/text_cleaning.py.

GENERIC_WORDS = {
    "issue", "issues", "error", "errors", "problem", "problems",
    "fix", "fixed", "fixing", "resolve", "resolved", "resolving",
    "ticket", "incident", "please", "help", "needed", "request",
    "update", "updated", "updating", "closing", "closed",
}


def _clean_for_embedding(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\b\d{10}\b', '', text)
    text = re.sub(r'\b[A-Z]{2,3}\s*[-_]?\s*\d{2}\b', '', text)
    text = re.sub(r'\$\s*[\d,]+\.?\d*', '', text)
    text = re.sub(r'\bINC\d+\b', '', text)
    text = re.sub(r'\bPRB\d+\b', '', text)
    text = re.sub(r'\bINCTASK\d+\b', '', text)
    text = re.sub(r'\b\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\b', '', text)
    text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '', text)
    text = re.sub(r'\b[\w.-]+@[\w.-]+\.\w+\b', '', text)
    words = text.split()
    words = [w for w in words if w.lower().strip(".,;:!?()") not in GENERIC_WORDS]
    return re.sub(r'\s+', ' ', ' '.join(words)).strip()


def _build_embedding_text(inc: dict) -> str:
    """Build v2 embedding text from custom API response."""
    parts = []

    sd = _clean_for_embedding(inc.get("incident", {}).get("short_description", ""))
    if sd:
        parts.append(f"Issue: {sd}")

    cmdb = inc.get("incident", {}).get("cmdb_ci_display", "")
    cat = inc.get("incident", {}).get("category", "")
    subcat = inc.get("incident", {}).get("subcategory", "")
    if cmdb or cat:
        s = f"System: {cmdb}" if cmdb else ""
        if cat:
            s += f" | {cat}"
        if subcat:
            s += f" > {subcat}"
        parts.append(s.strip())

    desc = _clean_for_embedding(inc.get("incident", {}).get("description", ""))
    if desc and len(desc) > 15:
        parts.append(f"Root cause: {desc[:300]}")

    # First work note
    work_notes = inc.get("notes", {}).get("work_notes", [])
    if isinstance(work_notes, list) and work_notes:
        # Get earliest substantive note
        for note in reversed(work_notes):
            val = note.get("value", "")
            if len(val) > 50:
                parts.append(f"Investigation: {_clean_for_embedding(val)[:200]}")
                break

    cn = _clean_for_embedding(inc.get("resolution", {}).get("close_notes", ""))
    if cn and len(cn) > 10:
        parts.append(f"Resolution: {cn[:200]}")

    return "\n".join(parts)


def _flatten_custom_api(data: dict) -> dict:
    """Flatten custom API response into our DB row format."""
    inc = data.get("incident", {})
    res = data.get("resolution", {})
    rel = data.get("related_records", {})
    order = data.get("order_data", {})
    ops = data.get("operational_metrics", {})
    contact = data.get("contact", {})
    notes = data.get("notes", {})

    # Concatenate work notes into a single string (for DB storage)
    wn_list = notes.get("work_notes", [])
    if isinstance(wn_list, list):
        wn_text = "\n\n".join(
            f"{n.get('created_on', '')} - {n.get('created_by', '')} (Work notes)\n{n.get('value', '')}"
            for n in wn_list
        )
    else:
        wn_text = str(wn_list) if wn_list else ""

    comments_list = notes.get("comments", [])
    if isinstance(comments_list, list):
        cm_text = "\n\n".join(
            f"{c.get('created_on', '')} - {c.get('created_by', '')} (Comments)\n{c.get('value', '')}"
            for c in comments_list
        )
    else:
        cm_text = str(comments_list) if comments_list else ""

    def parse_int(v):
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

    def parse_bool(v):
        return v in (True, 'true', '1', 1)

    return {
        "number": inc.get("number"),
        "sys_id": inc.get("sys_id"),
        "short_description": inc.get("short_description", ""),
        "description": inc.get("description"),
        "category": inc.get("category"),
        "subcategory": inc.get("subcategory"),
        "priority": inc.get("priority_display"),
        "severity": ops.get("severity_display"),
        "impact": inc.get("impact_display"),
        "urgency": inc.get("urgency_display"),
        "state": inc.get("incident_state_display"),
        "close_code": res.get("close_code_display"),
        "assignment_group": inc.get("assignment_group_display"),
        "assigned_to": inc.get("assigned_to_display"),
        "cmdb_ci": inc.get("cmdb_ci_display"),
        "business_service": None,
        "caller_id": inc.get("caller_id_display"),
        "location": inc.get("location_display"),
        "company": inc.get("company_display"),
        "contact_type": contact.get("contact_type_display"),
        "opened_by": contact.get("opened_by_display"),
        "close_notes": res.get("close_notes"),
        "u_resolved_by": res.get("u_resolved_by_display"),
        "u_resolution_confirmed_by": res.get("u_resolution_confirmed_by_display"),
        "problem_id": rel.get("problem_id_display"),
        "parent_incident": rel.get("parent_incident_display"),
        "u_jira_number": rel.get("u_jira_number"),
        "u_order_number": order.get("u_order_number"),
        "u_total_order_amount": order.get("u_total_order_amount"),
        "u_order_type": order.get("u_order_type"),
        "u_order_date": order.get("u_order_date") or None,
        "u_financial_impact": order.get("u_financial_impact"),
        "u_correction": parse_bool(inc.get("u_correction")),
        "u_correction_type": order.get("u_correction_type"),
        "u_error_category": order.get("u_error_category"),
        "business_duration": ops.get("business_duration"),
        "business_stc": parse_int(ops.get("business_stc")),
        "calendar_duration": ops.get("calendar_duration"),
        "calendar_stc": None,
        "reassignment_count": parse_int(ops.get("reassignment_count")),
        "reopen_count": parse_int(ops.get("reopen_count")),
        "made_sla": parse_bool(ops.get("made_sla")),
        "escalation": ops.get("escalation_display"),
        "work_notes": wn_text,
        "comments": cm_text,
        "opened_at": inc.get("opened_at"),
        "resolved_at": inc.get("u_resolved_at"),
        "closed_at": inc.get("closed_at"),
    }


# ── Endpoints ───────────────────────────────────────────────────

@router.get("/sync/status")
async def sync_status():
    """Overview: how many incidents in SN vs our DB."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        db_count = await conn.fetchval("SELECT COUNT(*) FROM rexus_incidents_v2")
        db_latest = await conn.fetchval("SELECT MAX(opened_at) FROM rexus_incidents_v2")
        db_embedded = await conn.fetchval("SELECT COUNT(*) FROM rexus_incidents_v2 WHERE embedding IS NOT NULL")

    try:
        client = _get_sn_client()
        sn_closed_count = await asyncio.to_thread(client.count_table, "incident", "state=7")
    except Exception as e:
        sn_closed_count = f"Error: {e}"

    return {
        "database": {
            "total_incidents": db_count,
            "embedded": db_embedded,
            "latest_incident_date": str(db_latest) if db_latest else None,
        },
        "servicenow": {
            "closed_incidents": sn_closed_count,
        },
    }


@router.get("/sync/delta")
async def sync_delta():
    """
    Find closed incidents in ServiceNow that are NOT in our database.
    Groups them by month and week in reverse chronological order.
    Only includes closed tickets (state = Closed Complete or Closed Skipped).
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        db_latest = await conn.fetchval("SELECT MAX(opened_at) FROM rexus_incidents_v2")

    # Query ServiceNow for closed incidents after our latest
    client = _get_sn_client()

    # Build query: closed incidents, opened after our latest date
    if db_latest:
        query = f"state=7^opened_at>{db_latest.strftime('%Y-%m-%d %H:%M:%S')}"
    else:
        query = "state=7"

    # SEC-015: Limit delta fetch to configurable max (default 2000) to prevent
    # runaway memory use when the backlog is large.
    sn_incidents = await asyncio.to_thread(
        lambda: client.query_table(
            "incident",
            query=query + "^ORDERBYDESCopened_at",
            fields=["number", "short_description", "opened_at", "cmdb_ci", "category", "state"],
            limit=_SYNC_DELTA_MAX,
            display_value=True,
        )
    )

    # Check which of these specific SN numbers already exist in DB (targeted query)
    sn_numbers = [inc.get("number", "") for inc in sn_incidents if inc.get("number")]
    if sn_numbers:
        async with pool.acquire() as conn:
            already_present = await conn.fetch(
                "SELECT incident_number FROM rexus_incidents_v2 WHERE incident_number = ANY($1)",
                sn_numbers,
            )
        existing_set = {r["incident_number"] for r in already_present}
    else:
        existing_set = set()

    # Filter out ones we already have
    delta = []
    for inc in sn_incidents:
        num = inc.get("number", "")
        if num and num not in existing_set:
            # Only closed
            state = inc.get("state", "")
            if "Closed" in str(state):
                cmdb = inc.get("cmdb_ci", "")
                if isinstance(cmdb, dict):
                    cmdb = cmdb.get("display_value", "")
                delta.append({
                    "incident_number": num,
                    "short_description": inc.get("short_description", "")[:80],
                    "opened_at": inc.get("opened_at", ""),
                    "cmdb_ci": cmdb,
                    "category": inc.get("category", ""),
                })

    # Group by month and week
    months = {}
    weeks = {}
    for inc in delta:
        opened = inc.get("opened_at", "")
        if opened:
            try:
                dt = datetime.strptime(opened[:10], "%Y-%m-%d")
                month_key = dt.strftime("%Y-%m")
                week_key = f"{dt.year}-W{dt.isocalendar()[1]:02d}"

                if month_key not in months:
                    months[month_key] = []
                months[month_key].append(inc)

                if week_key not in weeks:
                    weeks[week_key] = []
                weeks[week_key].append(inc)
            except ValueError:
                pass

    # Sort reverse chronological
    sorted_months = sorted(months.items(), key=lambda x: x[0], reverse=True)
    sorted_weeks = sorted(weeks.items(), key=lambda x: x[0], reverse=True)

    return {
        "total_delta": len(delta),
        "by_month": [{"month": m, "count": len(incs), "incidents": incs} for m, incs in sorted_months],
        "by_week": [{"week": w, "count": len(incs), "incidents": incs} for w, incs in sorted_weeks],
    }


# SEC-020 FIX: Constrain incident number format (Pydantic v2 Field validators)
IncidentNumber = Annotated[str, Field(min_length=3, max_length=20, pattern=r'^INC\d+$')]


class ImportRequest(BaseModel):
    incident_numbers: list[IncidentNumber] = Field(..., max_length=50)


@router.post("/sync/import")
@limiter.limit(os.getenv("RATE_LIMIT_SYNC", "5/minute"))
async def sync_import(request: Request, req: ImportRequest):
    """
    Import specific incidents from ServiceNow into our database.
    Uses the custom detailed API, generates embeddings, inserts into v2 table.

    SEC-013: This endpoint modifies the knowledge base. In production it should
    be protected by an admin role or API key (e.g. via a FastAPI dependency).
    Currently relies on network-level access controls (internal only).

    ARCH-009: Progress is tracked per-incident and returned in the response.
    """
    if not req.incident_numbers:
        raise HTTPException(400, "No incidents to import")

    sn_client = _get_sn_client()
    openai_client = _get_openai()
    pool = await get_pool()

    results = []
    imported = 0
    failed = 0
    total = len(req.incident_numbers)

    for idx, inc_num in enumerate(req.incident_numbers, start=1):
        logger.info(f"Importing {idx}/{total}: {inc_num}")
        try:
            # Fetch via custom API (offloaded to thread to avoid blocking event loop)
            data = await asyncio.to_thread(sn_client.get_incident_detailed, inc_num)
            if not data:
                results.append({"incident": inc_num, "status": "not_found"})
                failed += 1
                continue

            # Only import closed tickets
            state = data.get("incident", {}).get("incident_state_display", "")
            if "Closed" not in str(state) and "closed" not in str(state).lower():
                results.append({"incident": inc_num, "status": "skipped_not_closed", "state": state})
                continue

            # Flatten to DB format
            flat = _flatten_custom_api(data)

            # Build embedding text
            embedding_text = _build_embedding_text(data)

            # ARCH-008: Use AsyncOpenAI (async client) in this async handler
            emb_resp = await openai_client.embeddings.create(model="text-embedding-3-small", input=embedding_text)
            embedding = emb_resp.data[0].embedding

            # Track embedding token usage
            emb_tokens = len(embedding_text) // 4
            await track_usage(pool, "embedding", "text-embedding-3-small", emb_tokens, 0,
                              endpoint="/sync/import", incident_number=inc_num)

            # Insert into v2 table
            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO rexus_incidents_v2 (
                        incident_number, sys_id, short_description, description,
                        category, subcategory, priority, severity, impact, urgency,
                        state, close_code,
                        assignment_group, assigned_to, cmdb_ci, business_service,
                        caller_id, location, company, contact_type, opened_by,
                        close_notes, u_resolved_by, u_resolution_confirmed_by,
                        problem_id, parent_incident, u_jira_number,
                        u_order_number, u_total_order_amount, u_order_type, u_order_date,
                        u_financial_impact, u_correction, u_correction_type, u_error_category,
                        business_duration, business_stc, calendar_duration, calendar_stc,
                        reassignment_count, reopen_count, made_sla, escalation,
                        work_notes, comments,
                        opened_at, resolved_at, closed_at,
                        split_group, embedding_text, embedding
                    ) VALUES (
                        $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,
                        $17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31,
                        $32,$33,$34,$35,$36,$37,$38,$39,$40,$41,$42,$43,$44,$45,
                        $46::timestamp,$47::timestamp,$48::timestamp,
                        'synced', $49, $50
                    ) ON CONFLICT (incident_number) DO NOTHING
                """,
                    flat["number"], flat["sys_id"], flat["short_description"], flat["description"],
                    flat["category"], flat["subcategory"], flat["priority"], flat["severity"],
                    flat["impact"], flat["urgency"], flat["state"], flat["close_code"],
                    flat["assignment_group"], flat["assigned_to"], flat["cmdb_ci"], flat["business_service"],
                    flat["caller_id"], flat["location"], flat["company"], flat["contact_type"],
                    flat["opened_by"], flat["close_notes"], flat["u_resolved_by"], flat["u_resolution_confirmed_by"],
                    flat["problem_id"], flat["parent_incident"], flat["u_jira_number"],
                    flat["u_order_number"], flat["u_total_order_amount"], flat["u_order_type"], flat["u_order_date"],
                    flat["u_financial_impact"], flat["u_correction"], flat["u_correction_type"], flat["u_error_category"],
                    flat["business_duration"], flat["business_stc"], flat["calendar_duration"], flat["calendar_stc"],
                    flat["reassignment_count"], flat["reopen_count"], flat["made_sla"], flat["escalation"],
                    flat["work_notes"], flat["comments"],
                    flat["opened_at"], flat["resolved_at"], flat["closed_at"],
                    embedding_text, embedding,
                )

            imported += 1
            results.append({"incident": inc_num, "status": "imported"})

        except Exception as e:
            failed += 1
            results.append({"incident": inc_num, "status": "error", "error": str(e)[:100]})

    skipped = total - imported - failed
    logger.info(f"Sync import complete — imported={imported}, skipped={skipped}, failed={failed}")
    return {
        "imported": imported,
        "failed": failed,
        "skipped": skipped,
        "total": total,
        "results": results,
    }
