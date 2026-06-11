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
import csv
import asyncio
import logging
from datetime import datetime, date
from pathlib import Path
from pydantic import BaseModel, Field
from fastapi import APIRouter, Query, HTTPException, Request, Depends
from slowapi import Limiter
from slowapi.util import get_remote_address
from backend.api.database import get_pool
from backend.api.utils.llm_provider import embed_text as _embed_text_fn, get_embed_model
from backend.api.utils.token_tracker import track_usage
from backend.api.utils.text_cleaning import clean_for_embedding as _shared_clean_for_embedding
from backend.api.auth import require_admin_or_api_key
from backend.api.utils.incident_groups import group_incidents_by_period
from backend.api.utils.kb_articles import extract_kb_articles, insert_kb_mappings
from backend.api.utils.sync_constants import IncidentNumber, KB_MAPPING_REFRESH_MAX, SYNC_IMPORT_MAX
from backend.services.servicenow_client import ServiceNowClient

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sync"])
limiter = Limiter(key_func=get_remote_address)

# SEC-015: Configurable maximum number of delta incidents fetched from ServiceNow.
# Prevents runaway memory consumption on large backlogs.
_SYNC_DELTA_MAX = int(os.getenv("SYNC_DELTA_MAX", "2000"))

# ── CSV catalog fallback ──────────────────────────────────────────
# Used when the DT Search API is not available (e.g., staging/prod
# before the API is deployed). Falls back to the incident_catalog.csv
# exported from the dev environment.

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_CATALOG = _REPO_ROOT / "data" / "incident_catalog.csv"
# Docker sets CATALOG_PATH=/app/data/incident_catalog.csv; local dev uses repo data/
_CATALOG_PATH = Path(os.getenv("CATALOG_PATH", str(_DEFAULT_CATALOG)))


def _catalog_date_bounds() -> tuple[str | None, str | None]:
    """Return (min_date, max_date) YYYY-MM-DD from the CSV catalog, if present."""
    if not _CATALOG_PATH.exists():
        return None, None
    min_d: str | None = None
    max_d: str | None = None
    with open(_CATALOG_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            opened = (row.get("opened_at") or "")[:10]
            if len(opened) < 10:
                continue
            if min_d is None or opened < min_d:
                min_d = opened
            if max_d is None or opened > max_d:
                max_d = opened
    return min_d, max_d


def _load_from_catalog(
    start_date: str, end_date: str, closed_only: bool,
    category: str | None = None, cmdb_ci: str | None = None,
) -> list[dict]:
    """Load incidents from CSV catalog, filtered by date range."""
    if not _CATALOG_PATH.exists():
        logger.warning(f"CSV catalog not found at {_CATALOG_PATH}")
        return []

    results = []
    with open(_CATALOG_PATH) as f:
        reader = csv.DictReader(f)
        for row in reader:
            opened = row.get("opened_at", "")
            if not opened:
                continue
            # Date filter
            date_str = opened[:10]
            if date_str < start_date or date_str > end_date:
                continue
            # Closed filter
            if closed_only:
                state = row.get("state", "")
                if "Closed" not in state and "Resolved" not in state:
                    continue
            # Category filter
            if category and category.lower() not in (row.get("category", "") or "").lower():
                continue
            # CMDB filter
            if cmdb_ci and cmdb_ci.lower() not in (row.get("cmdb_ci", "") or "").lower():
                continue

            results.append({
                "number": row.get("incident_number", ""),
                "short_description": (row.get("short_description", "") or "")[:80] if "short_description" in row else "",
                "opened_at": opened,
                "sys_created_on": opened,
                "cmdb_ci_display": row.get("cmdb_ci", ""),
                "category": row.get("category", ""),
                "incident_state_display": row.get("state", ""),
            })

    logger.info(f"CSV catalog: {len(results)} incidents for {start_date} → {end_date}")
    return results




# ── PII/generic cleaning for embeddings ─────────────────────
# QUAL-002: Now uses shared utility from backend/api/utils/text_cleaning.py
# with strict=True for the stricter PII scrub used during sync import.


def _clean_for_embedding(text: str) -> str:
    """Delegate to shared text_cleaning utility with strict PII removal."""
    return _shared_clean_for_embedding(text, strict=True)


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

    def parse_date(v):
        """Parse a date string into a datetime.date object (or None)."""
        if not v:
            return None
        if isinstance(v, date):
            return v
        try:
            return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
        except ValueError:
            logger.warning("Could not parse date %r — storing NULL", v)
            return None

    def parse_ts(v):
        """Parse a ServiceNow timestamp string into a datetime object (or None)."""
        if not v:
            return None
        if isinstance(v, datetime):
            return v
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(str(v)[:19], fmt)
            except ValueError:
                continue
        logger.warning("Could not parse timestamp %r — storing NULL", v)
        return None

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
        "u_order_date": parse_date(order.get("u_order_date")),
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
        "opened_at": parse_ts(inc.get("opened_at")),
        "resolved_at": parse_ts(inc.get("u_resolved_at")),
        "closed_at": parse_ts(inc.get("closed_at")),
    }


# ── Endpoints ───────────────────────────────────────────────────

@router.get("/sync/status")
async def sync_status():
    """Overview: how many incidents in SN vs our DB."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        db_count = await conn.fetchval("SELECT COUNT(*) FROM rexus_incidents_v3")
        db_latest = await conn.fetchval("SELECT MAX(opened_at) FROM rexus_incidents_v3")
        db_embedded = await conn.fetchval("SELECT COUNT(*) FROM rexus_incidents_v3 WHERE embedding IS NOT NULL")

    try:
        client = ServiceNowClient()
        # Try DT Search API first, fall back to Table API count
        try:
            closed = await asyncio.to_thread(lambda: client.search_incidents(incident_state="7"))
            sn_closed_count = len(closed) if isinstance(closed, list) else "Unknown"
        except Exception:
            _closed_state = os.getenv("SN_CLOSED_STATE_CODE", "7")
            sn_closed_count = await asyncio.to_thread(client.count_table, "incident", f"state={_closed_state}")
    except Exception as e:
        sn_closed_count = f"Error: {e}"

    catalog_min, catalog_max = _catalog_date_bounds()

    return {
        "database": {
            "total_incidents": db_count,
            "embedded": db_embedded,
            "latest_incident_date": str(db_latest) if db_latest else None,
        },
        "servicenow": {
            "closed_incidents": sn_closed_count,
        },
        "catalog": {
            "path": str(_CATALOG_PATH),
            "available": _CATALOG_PATH.exists(),
            "date_min": catalog_min,
            "date_max": catalog_max,
        },
        "import_max_incidents": SYNC_IMPORT_MAX,
        "refresh_max_incidents": KB_MAPPING_REFRESH_MAX,
    }


@router.get("/sync/delta")
async def sync_delta(
    start_date: str = Query(None, description="Start date YYYY-MM-DD (default: 6 months ago)"),
    end_date: str = Query(None, description="End date YYYY-MM-DD (default: today)"),
    closed_only: bool = Query(True, description="Only closed incidents"),
    category: str = Query(None, description="Category filter"),
    cmdb_ci: str = Query(None, description="CMDB CI filter (display value)"),
    assignment_group: str = Query(None, description="Assignment group filter"),
):
    """
    Find incidents in ServiceNow that are NOT in our database.
    Uses the DT Search API with date range and closed_only filter.
    Max 6 months per API call — automatically splits into monthly chunks if range is larger.
    Groups results by month, week, and day in reverse chronological order.
    """
    pool = await get_pool()

    # Default date range: last 6 months
    if not start_date:
        from dateutil.relativedelta import relativedelta
        start_date = (datetime.now() - relativedelta(months=6)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    client = ServiceNowClient()

    filters = {}
    if category:
        filters["category"] = category
    if cmdb_ci:
        filters["cmdb_ci"] = cmdb_ci
    if assignment_group:
        filters["assignment_group"] = assignment_group

    # Discovery source priority:
    # 1. CSV catalog (always available — exported from dev DB, works offline)
    # 2. DT Search API (may not be available in staging/prod yet)
    #
    # CSV is the primary source because the Search API may not be deployed
    # in all environments. When both are available, CSV gives us historical
    # data and the Search API gives us the latest.

    sn_incidents = []
    source = "none"

    # Try CSV catalog first (always available)
    csv_incidents = _load_from_catalog(start_date, end_date, closed_only, category, cmdb_ci)
    if csv_incidents:
        sn_incidents = csv_incidents
        source = "csv"
        logger.info(f"CSV catalog: {len(csv_incidents)} incidents for {start_date} → {end_date}")

    # Try DT Search API for any incidents not in the CSV (e.g., newer than the export)
    try:
        api_incidents = await asyncio.to_thread(
            lambda: client.search_incidents_by_months(
                start_date=start_date,
                end_date=end_date,
                closed_only=closed_only,
                **filters,
            )
        )
        if api_incidents:
            # Merge: add any API incidents not already in the CSV set
            csv_numbers = {inc.get("number", "") for inc in csv_incidents}
            new_from_api = [inc for inc in api_incidents if inc.get("number", "") not in csv_numbers]
            if new_from_api:
                sn_incidents.extend(new_from_api)
                logger.info(f"DT Search API: added {len(new_from_api)} incidents not in CSV")
            source = "csv+api" if csv_incidents else "api"
    except Exception as search_err:
        logger.info(f"DT Search API not available ({search_err}), using CSV only")

    # Extract incident numbers and basic info
    sn_list = []
    for inc in sn_incidents:
        # Handle both flat and nested response structures
        if isinstance(inc, dict):
            num = inc.get("number", "") or inc.get("incident_number", "")
            if not num:
                continue
            sn_list.append({
                "incident_number": num,
                "short_description": (inc.get("short_description", "") or "")[:80],
                "opened_at": inc.get("opened_at", "") or inc.get("sys_created_on", ""),
                "cmdb_ci": inc.get("cmdb_ci_display", "") or inc.get("cmdb_ci", ""),
                "category": inc.get("category", ""),
                "state": inc.get("incident_state_display", "") or inc.get("incident_state", "") or inc.get("state", ""),
            })

    # Check which of these already exist in our DB
    sn_numbers = [inc["incident_number"] for inc in sn_list]
    if sn_numbers:
        # Batch check in chunks of 500 to avoid query size limits
        existing_set = set()
        for i in range(0, len(sn_numbers), 500):
            batch = sn_numbers[i:i + 500]
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT incident_number FROM rexus_incidents_v3 WHERE incident_number = ANY($1)",
                    batch,
                )
            existing_set.update(r["incident_number"] for r in rows)
    else:
        existing_set = set()

    # Filter out ones we already have
    delta = [inc for inc in sn_list if inc["incident_number"] not in existing_set]

    grouped = group_incidents_by_period(delta)

    catalog_min, catalog_max = _catalog_date_bounds()
    message = None
    if not sn_list:
        if not _CATALOG_PATH.exists():
            message = (
                f"Incident catalog not found at {_CATALOG_PATH}. "
                "Set CATALOG_PATH in .env or ensure data/incident_catalog.csv exists."
            )
        else:
            message = (
                f"No closed incidents in catalog for {start_date} → {end_date}. "
                f"Catalog covers {catalog_min} → {catalog_max} (some months may be missing)."
            )

    return {
        "total_delta": len(delta),
        "total_discovered": len(sn_list),
        "already_in_db": len(existing_set),
        "source": source,
        "message": message,
        "catalog_date_min": catalog_min,
        "catalog_date_max": catalog_max,
        "date_range": {"start": start_date, "end": end_date, "closed_only": closed_only},
        **grouped,
    }


class ImportRequest(BaseModel):
    incident_numbers: list[IncidentNumber] = Field(..., max_length=SYNC_IMPORT_MAX)


@router.post("/sync/import")
@limiter.limit(os.getenv("RATE_LIMIT_SYNC", "5/minute"))
async def sync_import(
    request: Request,
    req: ImportRequest,
    _admin: dict = Depends(require_admin_or_api_key),
):
    """
    Import specific incidents from ServiceNow into our database.
    Uses the custom detailed API (with KB articles), generates embeddings,
    inserts into v3 table, and inserts KB mappings into rexus_kb_article_incident_mapping.

    Requires admin JWT or X-Admin-Key matching REXUS_ADMIN_KEY.

    ARCH-009: Progress is tracked per-incident and returned in the response.
    """
    if not req.incident_numbers:
        raise HTTPException(400, "No incidents to import")

    sn_client = ServiceNowClient()
    embed_model = get_embed_model()
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

            # Use provider-agnostic embed function
            embedding = await _embed_text_fn(embedding_text)
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

            # Track embedding token usage
            emb_tokens = len(embedding_text) // 4
            await track_usage(pool, "embedding", embed_model, emb_tokens, 0,
                              endpoint="/sync/import", incident_number=inc_num)

            kb_list = extract_kb_articles(data)
            has_kb_article = bool(kb_list)
            mapping_inc = (flat.get("number") or inc_num).strip().upper()
            if not kb_list:
                logger.info(
                    "Import %s: no KB articles in SN response (checked kb_articles, attached_knowledge)",
                    mapping_inc,
                )

            # Insert into v3 table and KB mappings (QUAL-012: aligned with analyze.py)
            async with pool.acquire() as conn:
                kb_inserted = await insert_kb_mappings(conn, mapping_inc, kb_list)
                if kb_list and kb_inserted == 0:
                    logger.info(
                        "Import %s: %d KB article(s) from SN but all already in mapping table",
                        mapping_inc,
                        len(kb_list),
                    )
                await conn.execute("""
                    INSERT INTO rexus_incidents_v3 (
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
                        has_kb_article, split_group, embedding_text, embedding
                    ) VALUES (
                        $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,
                        $17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31,
                        $32,$33,$34,$35,$36,$37,$38,$39,$40,$41,$42,$43,$44,$45,
                         $46,$47,$48,$49,
                        'synced', $50, $51
                    ) ON CONFLICT (incident_number) DO UPDATE SET
                        has_kb_article = EXCLUDED.has_kb_article
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
                    has_kb_article,
                    embedding_text, embedding_str,
                )

            imported += 1
            results.append({
                "incident": inc_num,
                "status": "imported",
                "kb_inserted": kb_inserted,
                "kb_from_sn": len(kb_list),
            })

        except Exception as e:
            failed += 1
            logger.error("Failed to import %s: %s", inc_num, e, exc_info=True)
            results.append({"incident": inc_num, "status": "error", "error": str(e)[:500]})

    skipped = total - imported - failed
    logger.info(f"Sync import complete — imported={imported}, skipped={skipped}, failed={failed}")
    return {
        "imported": imported,
        "failed": failed,
        "skipped": skipped,
        "total": total,
        "results": results,
    }