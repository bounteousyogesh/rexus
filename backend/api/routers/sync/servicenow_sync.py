"""
ServiceNow manual sync: discover via search (or CSV), import via detailed API.

Endpoints:
  GET  /sync/status  - DB vs ServiceNow snapshot
  GET  /sync/delta   - Incidents in SN not yet in rexus_incidents_v3
  POST /sync/import  - Detailed API fetch, embed, insert into v3
"""

import os
import asyncio
import logging
from datetime import datetime

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Query, HTTPException, Request

from backend.api.database import get_pool
from backend.api.models.sync import ImportRequest
from backend.api.utils.incident_groups import group_incidents_by_period
from backend.api.utils.sync_constants import KB_MAPPING_REFRESH_MAX, SYNC_IMPORT_MAX
from backend.services.servicenow_client import ServiceNowClient

from .sync import (
    CATALOG_PATH,
    catalog_date_bounds,
    enrich_incident_row,
    filter_incidents_by_opened_date,
    fetch_incident_detailed,
    is_closed_incident,
    limiter,
    load_from_catalog,
    map_search_incident,
    upsert_incident_v3,
)

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/sync/status")
async def sync_status():
    """Overview: how many incidents in SN vs our DB."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        db_count = await conn.fetchval("SELECT COUNT(*) FROM rexus_incidents_v3")
        db_latest = await conn.fetchval("SELECT MAX(opened_at) FROM rexus_incidents_v3")
        db_embedded = await conn.fetchval(
            "SELECT COUNT(*) FROM rexus_incidents_v3 WHERE embedding IS NOT NULL"
        )

    try:
        client = ServiceNowClient()
        try:
            closed = await asyncio.to_thread(lambda: client.search_incidents(incident_state="7"))
            sn_closed_count = len(closed) if isinstance(closed, list) else "Unknown"
        except Exception:
            closed_state = os.getenv("SN_CLOSED_STATE_CODE", "7")
            sn_closed_count = await asyncio.to_thread(
                client.count_table, "incident", f"state={closed_state}",
            )
    except Exception as e:
        sn_closed_count = f"Error: {e}"

    catalog_min, catalog_max = catalog_date_bounds()

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
            "path": str(CATALOG_PATH),
            "available": CATALOG_PATH.exists(),
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
    Find incidents in ServiceNow not yet in rexus_incidents_v3.
    Discovery uses search API (basic fields); import uses detailed API separately.
    """
    pool = await get_pool()

    if not start_date:
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

    sn_incidents: list[dict] = []
    source = "none"

    csv_incidents = load_from_catalog(start_date, end_date, closed_only, category, cmdb_ci)
    if csv_incidents:
        sn_incidents = csv_incidents
        source = "csv"
        logger.info("CSV catalog: %d incidents for %s → %s", len(csv_incidents), start_date, end_date)

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
            csv_numbers = {inc.get("number", "") for inc in csv_incidents}
            new_from_api = [inc for inc in api_incidents if inc.get("number", "") not in csv_numbers]
            if new_from_api:
                sn_incidents.extend(new_from_api)
                logger.info("DT Search API: added %d incidents not in CSV", len(new_from_api))
            source = "csv+api" if csv_incidents else "api"
    except Exception as search_err:
        logger.info("DT Search API not available (%s), using CSV only", search_err)

    sn_incidents = filter_incidents_by_opened_date(sn_incidents, start_date, end_date)

    sn_list = []
    for inc in sn_incidents:
        if not isinstance(inc, dict):
            continue
        mapped = map_search_incident(inc)
        if mapped:
            sn_list.append(mapped)

    sn_numbers = [inc["incident_number"] for inc in sn_list]
    if sn_numbers:
        existing_set: set[str] = set()
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

    delta = [inc for inc in sn_list if inc["incident_number"] not in existing_set]
    grouped = group_incidents_by_period(delta)

    catalog_min, catalog_max = catalog_date_bounds()
    message = None
    if not sn_list:
        if not CATALOG_PATH.exists():
            message = (
                f"Incident catalog not found at {CATALOG_PATH}. "
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

@router.post("/sync/import")
@limiter.limit(os.getenv("RATE_LIMIT_SYNC", "5/minute"))
async def sync_import(request: Request, req: ImportRequest):
    """
    Import incidents into rexus_incidents_v3 via detailed API (with KB articles and embeddings).
    """
    if not req.incident_numbers:
        raise HTTPException(400, "No incidents to import")

    sn_client = ServiceNowClient()
    pool = await get_pool()

    results = []
    imported = 0
    failed = 0
    total = len(req.incident_numbers)

    for idx, inc_num in enumerate(req.incident_numbers, start=1):
        logger.info("Importing %d/%d: %s", idx, total, inc_num)
        try:
            data = await fetch_incident_detailed(sn_client, inc_num, include_kb_articles=True)
            if not data:
                results.append({"incident": inc_num, "status": "not_found"})
                failed += 1
                continue

            if not is_closed_incident(data):
                state = data.get("incident", {}).get("incident_state_display", "")
                results.append({"incident": inc_num, "status": "skipped_not_closed", "state": state})
                continue

            async with pool.acquire() as conn:
                row, kb_inserted, kb_from_sn = await enrich_incident_row(
                    pool, conn, data, endpoint="/sync/import",
                )
                if not row:
                    results.append({"incident": inc_num, "status": "not_found"})
                    failed += 1
                    continue
                if not kb_from_sn:
                    logger.info(
                        "Import %s: no KB articles in SN response (checked kb_articles, attached_knowledge)",
                        row["incident_number"],
                    )
                elif kb_inserted == 0:
                    logger.info(
                        "Import %s: %d KB article(s) from SN but all already in mapping table",
                        row["incident_number"],
                        kb_from_sn,
                    )
                await upsert_incident_v3(conn, row)

            imported += 1
            results.append({
                "incident": inc_num,
                "status": "imported",
                "kb_inserted": kb_inserted,
                "kb_from_sn": kb_from_sn,
            })

        except Exception as e:
            failed += 1
            logger.error("Failed to import %s: %s", inc_num, e, exc_info=True)
            results.append({"incident": inc_num, "status": "error", "error": str(e)[:500]})

    skipped = total - imported - failed
    logger.info("Sync import complete — imported=%d, skipped=%d, failed=%d", imported, skipped, failed)
    return {
        "imported": imported,
        "failed": failed,
        "skipped": skipped,
        "total": total,
        "results": results,
    }
