"""
Shared ServiceNow sync utilities: search mapping, detailed fetch, flattening.

Used by servicenow_sync (manual closed delta import) and new_incident (daily snapshot).
"""

import os
import re
import csv
import asyncio
import logging
from datetime import datetime, date
from pathlib import Path

from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.api.utils.kb_articles import extract_kb_articles, insert_kb_mappings
from backend.api.utils.llm_provider import embed_text as embed_text_fn, get_embed_model
from backend.api.utils.text_cleaning import clean_for_embedding as _shared_clean_for_embedding
from backend.api.utils.token_tracker import track_usage
from backend.services.servicenow_client import ServiceNowClient

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

DETAIL_CONCURRENCY = int(os.getenv("NEW_INCIDENTS_DETAIL_CONCURRENCY", "8"))

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_DEFAULT_CATALOG = _REPO_ROOT / "data" / "incident_catalog.csv"
CATALOG_PATH = Path(os.getenv("CATALOG_PATH", str(_DEFAULT_CATALOG)))

def catalog_date_bounds() -> tuple[str | None, str | None]:
    """Return (min_date, max_date) YYYY-MM-DD from the CSV catalog, if present."""
    if not CATALOG_PATH.exists():
        return None, None
    min_d: str | None = None
    max_d: str | None = None
    with open(CATALOG_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            opened = (row.get("opened_at") or "")[:10]
            if len(opened) < 10:
                continue
            if min_d is None or opened < min_d:
                min_d = opened
            if max_d is None or opened > max_d:
                max_d = opened
    return min_d, max_d

def incident_payload(incident: dict) -> dict:
    """Return the nested ServiceNow incident payload when present."""
    nested = incident.get("incident")
    return nested if isinstance(nested, dict) else {}

def incident_value(incident: dict, *keys: str) -> str:
    """Return the first non-empty value from flat or nested incident fields."""
    nested = incident_payload(incident)
    for key in keys:
        value = incident.get(key) or nested.get(key)
        if value not in (None, ""):
            return str(value)
    return ""

def incident_opened_date(incident: dict) -> str | None:
    """Return the incident opened date as YYYY-MM-DD, if present."""
    opened = incident_value(
        incident,
        "opened_at",
        "opened_on",
        "opened",
        "sys_created_on",
        "created_on",
        "closed_at",
        "closed_on",
    )
    match = re.search(r"\d{4}-\d{2}-\d{2}", opened)
    if not match:
        return None
    date_str = match.group(0)
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None
    return date_str

def is_closed_incident(data: dict) -> bool:
    """Return True when the incident state indicates closed."""
    state = data.get("incident", {}).get("incident_state_display", "")
    return "closed" in str(state).lower()

def filter_incidents_by_opened_date(
    incidents: list[dict],
    start_date: str,
    end_date: str,
) -> list[dict]:
    """Keep only incidents whose opened date falls inside the requested range."""
    return [
        incident
        for incident in incidents
        if (opened_date := incident_opened_date(incident))
        and start_date <= opened_date <= end_date
    ]

def load_from_catalog(
    start_date: str,
    end_date: str,
    closed_only: bool,
    category: str | None = None,
    cmdb_ci: str | None = None,
) -> list[dict]:
    """Load incidents from CSV catalog, filtered by date range."""
    if not CATALOG_PATH.exists():
        logger.warning("CSV catalog not found at %s", CATALOG_PATH)
        return []

    results = []
    with open(CATALOG_PATH) as f:
        reader = csv.DictReader(f)
        for row in reader:
            opened = row.get("opened_at", "")
            if not opened:
                continue
            date_str = opened[:10]
            if date_str < start_date or date_str > end_date:
                continue
            if closed_only:
                state = row.get("state", "")
                if "Closed" not in state and "Resolved" not in state:
                    continue
            if category and category.lower() not in (row.get("category", "") or "").lower():
                continue
            if cmdb_ci and cmdb_ci.lower() not in (row.get("cmdb_ci", "") or "").lower():
                continue

            results.append({
                "number": row.get("incident_number", ""),
                "short_description": (row.get("short_description", "") or "")[:80],
                "opened_at": opened,
                "sys_created_on": opened,
                "cmdb_ci_display": row.get("cmdb_ci", ""),
                "category": row.get("category", ""),
                "incident_state_display": row.get("state", ""),
            })

    logger.info("CSV catalog: %d incidents for %s → %s", len(results), start_date, end_date)
    return results

def map_search_incident(inc: dict, *, default_state: str | None = None) -> dict | None:
    """Map a ServiceNow search row to a basic incident dict (preview / delta)."""
    num = incident_value(inc, "number", "incident_number")
    if not num:
        return None
    state = incident_value(inc, "incident_state_display", "incident_state", "state")
    if not state and default_state:
        state = default_state
    return {
        "incident_number": num,
        "sys_id": incident_value(inc, "sys_id") or None,
        "short_description": incident_value(inc, "short_description")[:80],
        "opened_at": incident_opened_date(inc) or "",
        "cmdb_ci": incident_value(inc, "cmdb_ci_display", "cmdb_ci"),
        "category": incident_value(inc, "category"),
        "state": state,
        "priority": incident_value(inc, "priority_display", "priority") or None,
        "assignment_group": incident_value(inc, "assignment_group_display", "assignment_group") or None,
        "assigned_to": incident_value(inc, "assigned_to_display", "assigned_to") or None,
        "opened_by": incident_value(inc, "opened_by_display", "opened_by") or None,
    }

def clean_for_embedding(text: str) -> str:
    """Delegate to shared text_cleaning utility with strict PII removal."""
    return _shared_clean_for_embedding(text, strict=True)

def build_embedding_text(inc: dict) -> str:
    """Build v2 embedding text from custom API detailed response."""
    parts = []

    sd = clean_for_embedding(inc.get("incident", {}).get("short_description", ""))
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

    desc = clean_for_embedding(inc.get("incident", {}).get("description", ""))
    if desc and len(desc) > 15:
        parts.append(f"Root cause: {desc[:300]}")

    work_notes = inc.get("notes", {}).get("work_notes", [])
    if isinstance(work_notes, list) and work_notes:
        for note in reversed(work_notes):
            val = note.get("value", "")
            if len(val) > 50:
                parts.append(f"Investigation: {clean_for_embedding(val)[:200]}")
                break

    cn = clean_for_embedding(inc.get("resolution", {}).get("close_notes", ""))
    if cn and len(cn) > 10:
        parts.append(f"Resolution: {cn[:200]}")

    return "\n".join(parts)

def flatten_detailed_api(data: dict) -> dict:
    """Flatten detailed API response into rexus_incidents_v3 row format."""
    inc = data.get("incident", {})
    res = data.get("resolution", {})
    rel = data.get("related_records", {})
    order = data.get("order_data", {})
    ops = data.get("operational_metrics", {})
    contact = data.get("contact", {})
    notes = data.get("notes", {})

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
        return v in (True, "true", "1", 1)

    def parse_date(v):
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

# Columns shared by rexus_incidents_v3 and rexus_incidents_new (before snapshot metadata).
INCIDENT_ROW_COLUMNS = (
    "incident_number", "sys_id", "short_description", "description",
    "category", "subcategory", "priority", "severity", "impact", "urgency",
    "state", "close_code",
    "assignment_group", "assigned_to", "cmdb_ci", "business_service",
    "caller_id", "location", "company", "contact_type", "opened_by",
    "close_notes", "u_resolved_by", "u_resolution_confirmed_by",
    "problem_id", "parent_incident", "u_jira_number",
    "u_order_number", "u_total_order_amount", "u_order_type", "u_order_date",
    "u_financial_impact", "u_correction", "u_correction_type", "u_error_category",
    "business_duration", "business_stc", "calendar_duration", "calendar_stc",
    "reassignment_count", "reopen_count", "made_sla", "escalation",
    "work_notes", "comments",
    "opened_at", "resolved_at", "closed_at",
    "has_kb_article", "split_group", "embedding_text", "embedding",
)

def _insert_sql(table: str) -> str:
    placeholders = ", ".join(f"${i}" for i in range(1, len(INCIDENT_ROW_COLUMNS) + 1))
    return f"INSERT INTO {table} ({', '.join(INCIDENT_ROW_COLUMNS)}) VALUES ({placeholders})"

UPSERT_V3_SQL = f"""
INSERT INTO rexus_incidents_v3 ({", ".join(INCIDENT_ROW_COLUMNS)})
VALUES ({", ".join(f"${i}" for i in range(1, len(INCIDENT_ROW_COLUMNS) + 1))})
ON CONFLICT (incident_number) DO UPDATE SET
    {", ".join(f"{col} = EXCLUDED.{col}" for col in INCIDENT_ROW_COLUMNS if col != "incident_number")},
    updated_at = CURRENT_TIMESTAMP
RETURNING (xmax = 0) AS inserted
"""

UPSERT_SNAPSHOT_SQL = f"""
INSERT INTO rexus_incidents_new ({", ".join(INCIDENT_ROW_COLUMNS)}, sync_date)
VALUES ({", ".join(f"${i}" for i in range(1, len(INCIDENT_ROW_COLUMNS) + 1))}, ${len(INCIDENT_ROW_COLUMNS) + 1})
ON CONFLICT (incident_number, sync_date) DO UPDATE SET
    {", ".join(f"{col} = EXCLUDED.{col}" for col in INCIDENT_ROW_COLUMNS if col != "incident_number")},
    updated_at = CURRENT_TIMESTAMP,
    version = rexus_incidents_new.version + 1,
    synced_at = CURRENT_TIMESTAMP
RETURNING (xmax = 0) AS inserted
"""

def incident_row_values(row: dict) -> tuple:
    """Return INSERT values for INCIDENT_ROW_COLUMNS."""
    return tuple(row.get(col) for col in INCIDENT_ROW_COLUMNS)

def map_detailed_to_row(data: dict, *, default_state: str | None = None) -> dict | None:
    """Map detailed API payload to a shared incident row dict."""
    flat = flatten_detailed_api(data)
    if not flat.get("number"):
        return None
    row = {("incident_number" if key == "number" else key): value for key, value in flat.items()}
    row["short_description"] = row.get("short_description") or ""
    if default_state is not None:
        row["state"] = row.get("state") or default_state
    return row

async def enrich_incident_row(
    pool,
    conn,
    data: dict,
    *,
    endpoint: str,
    default_state: str | None = None,
) -> tuple[dict | None, int, int]:
    """Build a full incident row with KB mappings and embedding.

    Returns (row, kb_inserted, kb_from_sn).
    """
    row = map_detailed_to_row(data, default_state=default_state)
    if not row:
        return None, 0, 0

    kb_list = extract_kb_articles(data)
    kb_from_sn = len(kb_list)
    row["has_kb_article"] = bool(kb_list)
    mapping_inc = row["incident_number"].strip().upper()
    kb_inserted = 0
    if mapping_inc:
        kb_inserted = await insert_kb_mappings(conn, mapping_inc, kb_list)

    embedding_text = build_embedding_text(data)
    embedding = await embed_text_fn(embedding_text)
    row["embedding_text"] = embedding_text
    row["embedding"] = "[" + ",".join(str(x) for x in embedding) + "]"
    row["split_group"] = "synced"
    await track_usage(
        pool,
        "embedding",
        get_embed_model(),
        len(embedding_text) // 4,
        0,
        endpoint=endpoint,
        incident_number=row["incident_number"],
    )
    return row, kb_inserted, kb_from_sn

async def upsert_incident_v3_returning(conn, row: dict) -> bool:
    result = await conn.fetchrow(UPSERT_V3_SQL, *incident_row_values(row))
    return result["inserted"]

async def upsert_incident_v3(conn, row: dict) -> None:
    await upsert_incident_v3_returning(conn, row)

async def upsert_incident_snapshot(conn, row: dict, sync_date: date) -> bool:
    result = await conn.fetchrow(UPSERT_SNAPSHOT_SQL, *incident_row_values(row), sync_date)
    return result["inserted"]

async def batch_upsert_snapshots(
    conn, incidents: list[dict], sync_date: date,
) -> tuple[int, int]:
    inserted = updated = 0
    for row in incidents:
        if await upsert_incident_snapshot(conn, row, sync_date):
            inserted += 1
        else:
            updated += 1
    return inserted, updated

async def fetch_incident_detailed(
    client: ServiceNowClient,
    incident_number: str,
    *,
    include_kb_articles: bool = True,
) -> dict | None:
    """Fetch one incident via GET /incident/{identifier}/detailed."""
    data = await asyncio.to_thread(
        client.get_incident_detailed,
        incident_number,
        include_kb_articles,
    )
    return data or None

async def fetch_incidents_detailed(
    incident_numbers: list[str],
    *,
    include_kb_articles: bool = False,
    max_incidents: int | None = None,
) -> list[dict]:
    """Fetch detailed API payloads for multiple incidents (concurrent)."""
    if not incident_numbers:
        return []

    limit = max_incidents if max_incidents is not None else len(incident_numbers)
    numbers = [num.strip() for num in incident_numbers[:limit] if num and num.strip()]
    if not numbers:
        return []

    client = ServiceNowClient()
    sem = asyncio.Semaphore(DETAIL_CONCURRENCY)

    async def fetch_bounded(num: str) -> dict | None:
        async with sem:
            return await fetch_incident_detailed(
                client, num, include_kb_articles=include_kb_articles,
            )

    results = await asyncio.gather(*(fetch_bounded(num) for num in numbers))
    return [row for row in results if row]
