"""
KB article incident mapping refresh from ServiceNow.

Used by POST /api/v1/kb-mappings/refresh.
"""

import asyncio
import logging
from dataclasses import dataclass

from backend.api.utils.kb_articles import extract_kb_articles, insert_kb_mappings

logger = logging.getLogger(__name__)

_SN_CONCURRENCY = 8

_UPDATE_HAS_KB_SQL = """
    UPDATE rexus_incidents_v3
    SET has_kb_article = $2
    WHERE UPPER(TRIM(incident_number)) = $1
"""


@dataclass
class KbMappingRefreshSummary:
    candidates: int = 0
    with_kb: int = 0
    kb_rows_inserted: int = 0
    kb_rows_existing: int = 0
    no_kb: int = 0
    not_found: int = 0
    errors: int = 0


def summary_to_dict(summary: KbMappingRefreshSummary) -> dict:
    """Serialize a KB mapping refresh summary for API responses."""
    return {
        "candidates": summary.candidates,
        "with_kb": summary.with_kb,
        "kb_rows_inserted": summary.kb_rows_inserted,
        "kb_rows_existing": summary.kb_rows_existing,
        "no_kb": summary.no_kb,
        "not_found": summary.not_found,
        "errors": summary.errors,
    }


def _dedupe_incident_numbers(incident_numbers: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for inc_num in incident_numbers:
        inc = inc_num.strip().upper()
        if not inc or inc in seen:
            continue
        seen.add(inc)
        deduped.append(inc)
    return deduped


def _summary_from_results(candidates: int, results: list[dict]) -> KbMappingRefreshSummary:
    summary = KbMappingRefreshSummary(candidates=candidates)
    for result in results:
        status = result["status"]
        if status == "mapped":
            summary.with_kb += 1
            kb_from_sn = result.get("kb_from_sn", 0)
            kb_inserted = result.get("kb_inserted", 0)
            summary.kb_rows_inserted += kb_inserted
            summary.kb_rows_existing += kb_from_sn - kb_inserted
        elif status == "no_kb":
            summary.no_kb += 1
        elif status == "not_found":
            summary.not_found += 1
        elif status == "error":
            summary.errors += 1
    return summary


async def run_kb_mapping_refresh(pool, sn_client, incident_numbers: list[str]) -> dict:
    """Refresh KB mappings and update has_kb_article per incident."""
    unique_numbers = _dedupe_incident_numbers(incident_numbers)
    total = len(unique_numbers)
    semaphore = asyncio.Semaphore(_SN_CONCURRENCY)
    db_lock = asyncio.Lock()

    async with pool.acquire() as conn:

        async def process_one(i: int, inc: str) -> dict:
            try:
                async with semaphore:
                    data = await asyncio.to_thread(sn_client.get_incident_detailed, inc, True)
                if not data:
                    logger.warning("[%d/%d] %s not found in ServiceNow", i, total, inc)
                    return {"incident": inc, "status": "not_found"}

                kb_list = extract_kb_articles(data)
                if not kb_list:
                    async with db_lock:
                        await conn.execute(_UPDATE_HAS_KB_SQL, inc, False)
                    logger.info("[%d/%d] %s no KB in SN", i, total, inc)
                    return {"incident": inc, "status": "no_kb"}

                async with db_lock:
                    inserted = await insert_kb_mappings(conn, inc, kb_list)
                    await conn.execute(_UPDATE_HAS_KB_SQL, inc, True)

                logger.info(
                    "[%d/%d] %s ok kb_from_sn=%d inserted=%d already_mapped=%d",
                    i,
                    total,
                    inc,
                    len(kb_list),
                    inserted,
                    len(kb_list) - inserted,
                )
                return {
                    "incident": inc,
                    "status": "mapped",
                    "kb_from_sn": len(kb_list),
                    "kb_inserted": inserted,
                }
            except Exception as e:
                logger.error("[%d/%d] %s error: %s", i, total, inc, e)
                return {"incident": inc, "status": "error", "error": str(e)[:500]}

        results = list(await asyncio.gather(*[
            process_one(i, inc) for i, inc in enumerate(unique_numbers, start=1)
        ]))

    summary = _summary_from_results(total, results)
    return {"summary": summary_to_dict(summary), "results": results}