"""
REX-US — Enriched Incident Fetcher

Fetches full incident data from ServiceNow API including:
- All standard + custom fields (52 fields)
- Work notes (from incident record directly)
- Structured fields: u_jira_number, u_order_number, business_duration, etc.

Saves enriched data as JSON, ready for embedding generation.

Usage:
    python enrich_incidents.py --split training --batch-size 200
    python enrich_incidents.py --split wave_1 --batch-size 200
    python enrich_incidents.py --split all --batch-size 200
"""

import os
import sys
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

# Fields to fetch from ServiceNow — the full enriched set
ENRICHED_FIELDS = [
    # Identity
    'sys_id', 'number', 'short_description', 'description',
    # Classification
    'category', 'subcategory', 'priority', 'severity', 'impact', 'urgency',
    'state', 'incident_state',
    # Assignment
    'assignment_group', 'assigned_to', 'cmdb_ci', 'business_service',
    'caller_id', 'location', 'company', 'contact_type',
    'opened_by', 'closed_by',
    # Resolution
    'close_notes', 'close_code',
    'u_resolution_confirmed_by', 'u_resolved_by',
    'resolution_code',
    # Dates
    'opened_at', 'resolved_at', 'closed_at',
    # Duration metrics
    'business_duration', 'business_stc', 'calendar_duration', 'calendar_stc',
    # Operational
    'reassignment_count', 'reopen_count',
    'made_sla', 'escalation',
    # Problem & related
    'problem_id', 'parent_incident', 'caused_by',
    # Order data (DT custom)
    'u_order_number', 'u_total_order_amount', 'u_order_type', 'u_order_date',
    'u_financial_impact', 'u_correction', 'u_correction_type', 'u_error_category',
    # JIRA
    'u_jira_number',
    # Project
    'u_related_project',
    # Work notes (concatenated from record)
    'work_notes', 'comments',
]


def get_db():
    url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "").replace("postgresql://", "http://")
    parsed = urlparse(url)
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port,
        database=unquote(parsed.path.lstrip("/").split("?")[0]),
        user=unquote(parsed.username), password=unquote(parsed.password),
    )


def flatten_display_value(val):
    """Extract display_value from ServiceNow response objects."""
    if isinstance(val, dict):
        return val.get('display_value', '')
    return val


def fetch_batch(client, incident_numbers, batch_size=50):
    """Fetch incidents in sub-batches using sysparm_query with IN clause."""
    all_results = {}

    for i in range(0, len(incident_numbers), batch_size):
        batch = incident_numbers[i:i + batch_size]
        query = "numberIN" + ",".join(batch)

        try:
            results = client.query_table(
                'incident',
                query=query,
                fields=ENRICHED_FIELDS,
                limit=batch_size,
                display_value=True,
            )

            for r in results:
                flat = {}
                for k, v in r.items():
                    flat[k] = flatten_display_value(v)
                num = flat.get('number', '')
                if num:
                    all_results[num] = flat

        except Exception as e:
            logger.error(f"  Batch fetch error at offset {i}: {e}")
            # Retry individually
            for inc_num in batch:
                try:
                    results = client.query_table(
                        'incident',
                        query=f'number={inc_num}',
                        fields=ENRICHED_FIELDS,
                        limit=1,
                        display_value=True,
                    )
                    if results:
                        flat = {k: flatten_display_value(v) for k, v in results[0].items()}
                        all_results[flat.get('number', inc_num)] = flat
                except Exception as e2:
                    logger.error(f"    Individual fetch failed for {inc_num}: {e2}")

        if (i + batch_size) % 500 == 0 or i + batch_size >= len(incident_numbers):
            logger.info(f"  Fetched {min(i + batch_size, len(incident_numbers))}/{len(incident_numbers)} "
                       f"({len(all_results)} successful)")

    return all_results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="training", help="Split group to fetch: training, wave_1, wave_2, ..., all")
    parser.add_argument("--batch-size", type=int, default=50, help="API batch size")
    parser.add_argument("--output-dir", default="data/enriched", help="Output directory")
    args = parser.parse_args()

    # Get incident numbers for the requested split
    conn = get_db()
    cur = conn.cursor()

    if args.split == "all":
        cur.execute("SELECT incident_number FROM rexus_data_split ORDER BY row_rank")
    else:
        cur.execute("SELECT incident_number FROM rexus_data_split WHERE split_group = %s ORDER BY row_rank",
                    (args.split,))

    incident_numbers = [row[0] for row in cur.fetchall()]
    conn.close()

    if not incident_numbers:
        logger.error(f"No incidents found for split '{args.split}'")
        return

    logger.info(f"Fetching {len(incident_numbers)} incidents for split '{args.split}'")

    # Initialize ServiceNow client
    client = ServiceNowClient()
    logger.info("ServiceNow client initialized")

    # Fetch in batches
    start = time.time()
    enriched = fetch_batch(client, incident_numbers, batch_size=args.batch_size)
    elapsed = time.time() - start

    logger.info(f"Fetch complete: {len(enriched)}/{len(incident_numbers)} in {elapsed:.0f}s "
               f"({elapsed/len(incident_numbers):.2f}s per incident)")

    # Save to file
    output_dir = Path(__file__).parent.parent.parent / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"enriched_{args.split}.json"

    with open(output_file, 'w') as f:
        json.dump(list(enriched.values()), f, indent=2, default=str)

    logger.info(f"Saved to {output_file}")

    # Summary stats
    fields_filled = {}
    for inc in enriched.values():
        for k, v in inc.items():
            if k not in fields_filled:
                fields_filled[k] = 0
            if v and str(v).strip() and str(v) not in ('None', '0', 'false'):
                fields_filled[k] += 1

    logger.info(f"\n{'='*60}")
    logger.info(f"ENRICHMENT COMPLETE — {args.split}")
    logger.info(f"{'='*60}")
    logger.info(f"Incidents fetched: {len(enriched)}/{len(incident_numbers)}")
    logger.info(f"Time: {elapsed:.0f}s ({elapsed/60:.1f}min)")
    logger.info(f"Key field fill rates:")
    for field in ['work_notes', 'description', 'u_jira_number', 'u_order_number',
                  'problem_id', 'business_duration', 'reassignment_count', 'u_correction_type']:
        count = fields_filled.get(field, 0)
        pct = count * 100 // len(enriched) if enriched else 0
        logger.info(f"  {field}: {pct}% ({count}/{len(enriched)})")


if __name__ == "__main__":
    main()
