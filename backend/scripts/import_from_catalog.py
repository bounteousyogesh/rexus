"""
REX-US — Import Incidents from Catalog

Uses the incident_catalog.csv (exported from dev DB) to fetch incident
details from ServiceNow's DT Detailed API and import into the knowledge base.

The catalog has incident numbers + dates. This script:
1. Reads the catalog CSV
2. Filters by date range (user-specified)
3. Checks which ones are already in the DB
4. Fetches details via DT Detailed API (one at a time)
5. Generates embeddings and inserts into rexus_incidents_v3

This is the stopgap for production where the DT Search API only returns
6 months of data. The catalog gives us the full incident history.

Usage:
    # Import all incidents from April 2024 onwards
    python import_from_catalog.py --from 2024-04-01

    # Import a specific date range
    python import_from_catalog.py --from 2024-04-01 --to 2025-03-31

    # Import with resume support (picks up where it left off)
    python import_from_catalog.py --from 2024-04-01 --resume

    # Dry run — show what would be imported without fetching
    python import_from_catalog.py --from 2024-04-01 --dry-run
"""

import os
import sys
import csv
import json
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path, override=True)

import psycopg2
from urllib.parse import urlparse, unquote

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from backend.services.servicenow_client import ServiceNowClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CATALOG_PATH = Path(__file__).parent.parent.parent / "data" / "incident_catalog.csv"


def get_db():
    url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "").replace("postgresql://", "http://")
    parsed = urlparse(url)
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port,
        database=unquote(parsed.path.lstrip("/").split("?")[0]),
        user=unquote(parsed.username), password=unquote(parsed.password),
    )


def main():
    parser = argparse.ArgumentParser(description="Import incidents from catalog CSV via DT Detailed API")
    parser.add_argument("--from", dest="from_date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="to_date", default=None, help="End date (YYYY-MM-DD). Default: today")
    parser.add_argument("--catalog", default=str(CATALOG_PATH), help="Path to incident_catalog.csv")
    parser.add_argument("--resume", action="store_true", help="Skip incidents already in DB")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be imported without fetching")
    parser.add_argument("--limit", type=int, default=None, help="Max incidents to import")
    args = parser.parse_args()

    from_date = datetime.strptime(args.from_date, "%Y-%m-%d")
    to_date = datetime.strptime(args.to_date, "%Y-%m-%d") if args.to_date else datetime.now()

    # 1. Read catalog
    if not Path(args.catalog).exists():
        logger.error(f"Catalog not found: {args.catalog}")
        logger.error("Export it first: run the export query from the dev DB")
        return

    with open(args.catalog) as f:
        reader = csv.DictReader(f)
        catalog = list(reader)

    logger.info(f"Catalog: {len(catalog)} total incidents")

    # 2. Filter by date range
    filtered = []
    for row in catalog:
        opened = row.get("opened_at", "")
        if not opened:
            continue
        try:
            dt = datetime.strptime(opened[:10], "%Y-%m-%d")
            if from_date <= dt <= to_date:
                filtered.append(row)
        except ValueError:
            continue

    logger.info(f"Date range {args.from_date} → {args.to_date or 'today'}: {len(filtered)} incidents")

    if not filtered:
        logger.info("No incidents in this date range")
        return

    # 3. Check which are already in DB
    conn = get_db()
    cur = conn.cursor()

    inc_numbers = [r["incident_number"] for r in filtered]
    # Batch check
    existing = set()
    for i in range(0, len(inc_numbers), 500):
        batch = inc_numbers[i:i + 500]
        placeholders = ",".join(["%s"] * len(batch))
        cur.execute(f"SELECT incident_number FROM rexus_incidents_v3 WHERE incident_number IN ({placeholders})", batch)
        existing.update(r[0] for r in cur.fetchall())

    to_import = [r for r in filtered if r["incident_number"] not in existing]
    logger.info(f"Already in DB: {len(existing)}, New to import: {len(to_import)}")

    if args.limit:
        to_import = to_import[:args.limit]
        logger.info(f"Limited to: {len(to_import)}")

    if args.dry_run:
        logger.info("DRY RUN — would import:")
        for row in to_import[:20]:
            logger.info(f"  {row['incident_number']} | {row['opened_at'][:10]} | {row.get('cmdb_ci', '')[:20]} | {row.get('category', '')}")
        if len(to_import) > 20:
            logger.info(f"  ... and {len(to_import) - 20} more")
        conn.close()
        return

    if not to_import:
        logger.info("Nothing to import — all incidents already in DB")
        conn.close()
        return

    # 4. Import via DT Detailed API
    try:
        sn_client = ServiceNowClient()
    except ValueError as e:
        logger.error(f"ServiceNow client error: {e}")
        conn.close()
        return

    # Use OpenAI for embeddings
    from openai import OpenAI
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Import the text cleaning and embedding builder from sync
    from backend.api.utils.text_cleaning import clean_for_embedding

    imported = 0
    failed = 0
    start_time = time.time()

    for idx, row in enumerate(to_import):
        inc_num = row["incident_number"]
        try:
            # Fetch from SN
            data = sn_client.get_incident_detailed(inc_num)
            if not data:
                logger.warning(f"  {idx+1}/{len(to_import)} {inc_num}: not found in SN")
                failed += 1
                continue

            # Build embedding text (reuse sync.py logic)
            inc = data.get("incident", {})
            res = data.get("resolution", {})
            notes = data.get("notes", {})

            parts = []
            sd = clean_for_embedding(inc.get("short_description", ""), strict=True)
            if sd:
                parts.append(f"Issue: {sd}")

            cmdb = inc.get("cmdb_ci_display", "")
            cat = inc.get("category", "")
            if cmdb or cat:
                s = f"System: {cmdb}" if cmdb else ""
                if cat:
                    s += f" | {cat}"
                parts.append(s.strip())

            desc = clean_for_embedding(inc.get("description", "") or "", strict=True)
            if desc and len(desc) > 15:
                parts.append(f"Root cause: {desc[:300]}")

            work_notes = notes.get("work_notes", [])
            if isinstance(work_notes, list) and work_notes:
                for note in reversed(work_notes):
                    val = note.get("value", "")
                    if len(val) > 50:
                        parts.append(f"Investigation: {clean_for_embedding(val, strict=True)[:200]}")
                        break

            cn = clean_for_embedding(res.get("close_notes", "") or "", strict=True)
            if cn and len(cn) > 10:
                parts.append(f"Resolution: {cn[:200]}")

            embedding_text = "\n".join(parts)

            # Generate embedding
            emb_resp = openai_client.embeddings.create(model="text-embedding-3-small", input=embedding_text)
            embedding = emb_resp.data[0].embedding

            # Flatten for insert
            order = data.get("order_data", {})
            contact = data.get("contact", {})
            ops = data.get("operational_metrics", {})
            rel = data.get("related_records", {})

            wn_list = notes.get("work_notes", [])
            wn_text = "\n\n".join(
                f"{n.get('created_on', '')} - {n.get('created_by', '')} (Work notes)\n{n.get('value', '')}"
                for n in (wn_list if isinstance(wn_list, list) else [])
            )

            comments_list = notes.get("comments", [])
            cm_text = "\n\n".join(
                f"{c.get('created_on', '')} - {c.get('created_by', '')} (Comments)\n{c.get('value', '')}"
                for c in (comments_list if isinstance(comments_list, list) else [])
            )

            # Insert
            cur.execute("""
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
                    business_duration, calendar_duration,
                    work_notes, comments,
                    opened_at, resolved_at, closed_at,
                    split_group, embedding_text, embedding
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'training',%s,%s
                ) ON CONFLICT (incident_number) DO NOTHING
            """, (
                inc.get("number"), inc.get("sys_id"), inc.get("short_description"), inc.get("description"),
                inc.get("category"), inc.get("subcategory"), inc.get("priority_display"), ops.get("severity_display"),
                inc.get("impact_display"), inc.get("urgency_display"),
                inc.get("incident_state_display"), res.get("close_code_display"),
                inc.get("assignment_group_display"), inc.get("assigned_to_display"), inc.get("cmdb_ci_display"), None,
                inc.get("caller_id_display"), inc.get("location_display"), inc.get("company_display"),
                contact.get("contact_type_display"), contact.get("opened_by_display"),
                res.get("close_notes"), res.get("u_resolved_by_display"), res.get("u_resolution_confirmed_by_display"),
                rel.get("problem_id_display"), rel.get("parent_incident_display"), rel.get("u_jira_number"),
                order.get("u_order_number"), order.get("u_total_order_amount"), order.get("u_order_type"),
                order.get("u_order_date") or None,
                order.get("u_financial_impact"), order.get("u_correction_type"), order.get("u_correction_type"),
                order.get("u_error_category"),
                ops.get("business_duration"), ops.get("calendar_duration"),
                wn_text, cm_text,
                inc.get("opened_at"), inc.get("u_resolved_at"), inc.get("closed_at"),
                embedding_text, embedding,
            ))
            conn.commit()
            imported += 1

            if (idx + 1) % 10 == 0 or idx + 1 == len(to_import):
                elapsed = time.time() - start_time
                rate = (idx + 1) / elapsed * 60 if elapsed > 0 else 0
                logger.info(f"  {idx+1}/{len(to_import)}: imported={imported} failed={failed} ({rate:.0f}/min)")

        except Exception as e:
            logger.error(f"  {idx+1}/{len(to_import)} {inc_num}: ERROR — {e}")
            failed += 1
            conn.rollback()

    elapsed = time.time() - start_time
    logger.info(f"\nIMPORT COMPLETE")
    logger.info(f"  Imported: {imported}")
    logger.info(f"  Failed: {failed}")
    logger.info(f"  Time: {elapsed/60:.1f} min")
    logger.info(f"  Rate: {len(to_import)/elapsed*60:.0f} incidents/min" if elapsed > 0 else "")

    conn.close()


if __name__ == "__main__":
    main()
