"""
REX-US — Enriched Incident Fetcher

Fetches full incident data from ServiceNow using the DT Detailed API:
  GET /api/ditci/v1/servicenow/incident/{number}/detailed

Returns structured response with sections: incident, notes, resolution,
order_data, contact, operational_metrics, related_records, etc.

Saves enriched data as JSON, ready for embedding generation.

Usage:
    python enrich_incidents.py --split training --batch-size 50
    python enrich_incidents.py --split wave_1
    python enrich_incidents.py --split all
    python enrich_incidents.py --split all --resume  # resume from last checkpoint
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


def get_db():
    url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "").replace("postgresql://", "http://")
    parsed = urlparse(url)
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port,
        database=unquote(parsed.path.lstrip("/").split("?")[0]),
        user=unquote(parsed.username), password=unquote(parsed.password),
    )


def fetch_batch(client, incident_numbers, checkpoint_file=None, existing=None):
    """
    Fetch incidents one at a time using the DT Detailed API.
    Saves checkpoint every 50 incidents for resume support.
    """
    all_results = existing or {}
    failed = []
    total = len(incident_numbers)

    for i, inc_num in enumerate(incident_numbers):
        if inc_num in all_results:
            continue

        try:
            data = client.get_incident_detailed(inc_num)
            if data:
                all_results[inc_num] = data
            else:
                logger.warning(f"  {i+1}/{total} {inc_num}: not found in ServiceNow")
                failed.append(inc_num)
        except Exception as e:
            logger.error(f"  {i+1}/{total} {inc_num}: ERROR — {e}")
            failed.append(inc_num)
            time.sleep(1)  # back off on error

        if (i + 1) % 10 == 0 or i + 1 == total:
            logger.info(f"  Fetched {i+1}/{total} ({len(all_results)} successful, {len(failed)} failed)")

        # Checkpoint every 50 incidents
        if checkpoint_file and (i + 1) % 50 == 0:
            with open(checkpoint_file, 'w') as f:
                json.dump({"fetched": list(all_results.keys()), "failed": failed}, f)
            logger.info(f"  Checkpoint saved: {len(all_results)} fetched")

    return all_results, failed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="training", help="Split group: training, wave_1, ..., all")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--output-dir", default="data/enriched", help="Output directory")
    args = parser.parse_args()

    # Get incident numbers for the requested split
    conn = get_db()
    cur = conn.cursor()

    if args.split == "all":
        cur.execute("SELECT incident_number FROM rexus_incidents ORDER BY opened_at")
    else:
        cur.execute("SELECT incident_number FROM rexus_incidents WHERE split_group = %s ORDER BY opened_at",
                    (args.split,))

    incident_numbers = [row[0] for row in cur.fetchall()]
    conn.close()

    if not incident_numbers:
        logger.error(f"No incidents found for split '{args.split}'")
        return

    logger.info(f"Found {len(incident_numbers)} incidents for split '{args.split}'")

    # Output setup
    output_dir = Path(__file__).parent.parent.parent / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"enriched_{args.split}.json"
    checkpoint_file = output_dir / f"checkpoint_{args.split}.json"

    # Resume from checkpoint if requested
    existing = {}
    if args.resume and checkpoint_file.exists():
        with open(checkpoint_file) as f:
            ckpt = json.load(f)
        already_done = set(ckpt.get("fetched", []))
        logger.info(f"Resuming — {len(already_done)} already fetched")

        # Load existing output file if it exists
        if output_file.exists():
            with open(output_file) as f:
                prev_data = json.load(f)
            if isinstance(prev_data, list):
                for item in prev_data:
                    num = item.get("incident", {}).get("number", "")
                    if num:
                        existing[num] = item
            elif isinstance(prev_data, dict):
                existing = prev_data
            logger.info(f"Loaded {len(existing)} from existing output file")

    # Initialize ServiceNow client
    client = ServiceNowClient()
    logger.info("ServiceNow client initialized (using DT Detailed API)")

    # Fetch
    start = time.time()
    enriched, failed = fetch_batch(client, incident_numbers, checkpoint_file, existing)
    elapsed = time.time() - start

    logger.info(f"Fetch complete: {len(enriched)}/{len(incident_numbers)} in {elapsed:.0f}s "
               f"({elapsed/len(incident_numbers):.2f}s per incident)")

    # Save to file
    with open(output_file, 'w') as f:
        json.dump(list(enriched.values()), f, indent=2, default=str)
    logger.info(f"Saved to {output_file}")

    # Save failed list
    if failed:
        failed_file = output_dir / f"failed_{args.split}.json"
        with open(failed_file, 'w') as f:
            json.dump(failed, f, indent=2)
        logger.info(f"Failed incidents ({len(failed)}) saved to {failed_file}")

    # Clean up checkpoint on success
    if checkpoint_file.exists() and not failed:
        checkpoint_file.unlink()

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info(f"ENRICHMENT COMPLETE — {args.split}")
    logger.info(f"{'='*60}")
    logger.info(f"Incidents fetched: {len(enriched)}/{len(incident_numbers)}")
    logger.info(f"Failed: {len(failed)}")
    logger.info(f"Time: {elapsed:.0f}s ({elapsed/60:.1f}min)")
    logger.info(f"Rate: {elapsed/len(incident_numbers):.1f}s per incident")
    logger.info(f"Output: {output_file}")

    # Field fill rates from the structured response
    if enriched:
        sample = list(enriched.values())
        checks = {
            "work_notes": lambda d: len(d.get("notes", {}).get("work_notes", []) or []) > 0,
            "comments": lambda d: len(d.get("notes", {}).get("comments", []) or []) > 0,
            "close_notes": lambda d: bool(d.get("resolution", {}).get("close_notes")),
            "problem_id": lambda d: bool(d.get("related_records", {}).get("problem_id_display")),
            "u_jira_number": lambda d: bool(d.get("vendor", {}).get("u_jira_number") or d.get("related_records", {}).get("u_jira_number")),
            "u_order_number": lambda d: bool(d.get("order_data", {}).get("u_order_number")),
            "u_error_category": lambda d: bool(d.get("order_data", {}).get("u_error_category")),
            "business_duration": lambda d: bool(d.get("operational_metrics", {}).get("business_duration")),
        }
        logger.info(f"Key field fill rates:")
        for field, check in checks.items():
            count = sum(1 for d in sample if check(d))
            pct = count * 100 // len(sample) if sample else 0
            logger.info(f"  {field}: {pct}% ({count}/{len(sample)})")


if __name__ == "__main__":
    main()
