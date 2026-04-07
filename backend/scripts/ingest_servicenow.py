"""
REX-US — ServiceNow Incident Ingestion

Pulls real Vision/GK POS/Finance incidents from DT's ServiceNow dev instance
(production replica pre-Dec 25, 2025) and stores them locally as JSON for
subsequent embedding and database loading.

Usage:
    # Load .env first
    export $(grep -v '^#' ../../.env | xargs)
    python ingest_servicenow.py
    python ingest_servicenow.py --max 500    # limit for testing
    python ingest_servicenow.py --with-notes  # also fetch work notes (slower)
"""

import os
import sys
import json
import re
import argparse
import logging
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
# Load .env from repo root (REX-US/.env)
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path, override=True)

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from services.servicenow_client import ServiceNowClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Output directory
OUTPUT_DIR = Path(__file__).parent.parent.parent / "rexus" / "data"
if not OUTPUT_DIR.exists():
    # If running from rexus/backend/scripts, go up differently
    OUTPUT_DIR = Path(__file__).parent.parent / "data"


def clean_text(text: str) -> str:
    """Normalize text for embedding — remove instance-specific identifiers."""
    if not text:
        return ""
    text = re.sub(r"\b\d{10}\b", "[ORDER]", text)
    text = re.sub(r"\b\d{9}\b", "[ORDER]", text)
    text = re.sub(r"\b[A-Z]{3}\s+\d{2}\b", "[SITE]", text)
    text = re.sub(r"site:[A-Z]{3}\s+\d{2}", "site:[SITE]", text)
    text = re.sub(r"\b[A-Z]{3}_\d{2}\s*-\s*\d{4}\b", "[LOCATION]", text)
    text = re.sub(r"\$\s*[\d,]+\.?\d*", "$[AMOUNT]", text)
    text = re.sub(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", "[TIMESTAMP]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_display_value(field) -> str:
    """Extract display_value from ServiceNow field (may be dict or string)."""
    if isinstance(field, dict):
        return field.get("display_value", "") or ""
    return str(field) if field else ""


def detect_systems(text: str) -> list:
    """Detect which systems are mentioned in incident text."""
    systems = []
    text_upper = text.upper()
    if "GK" in text_upper or "GKPOS" in text_upper or "POS" in text_upper:
        systems.append("GKPOS")
    if "SAP" in text_upper or "ECC" in text_upper or "IDOC" in text_upper or "FINANCE POSTING" in text_upper:
        systems.append("SAP_ECC")
    if "HYBRIS" in text_upper or "ECOMM" in text_upper:
        systems.append("HYBRIS")
    if "MULESOFT" in text_upper:
        systems.append("MULESOFT")
    return systems


def build_embedding_text(inc: dict) -> str:
    """Build the text that will be embedded — combines key fields."""
    parts = []

    sd = clean_text(inc.get("short_description", ""))
    if sd:
        parts.append(f"Issue: {sd}")

    cat = inc.get("category", "")
    subcat = inc.get("subcategory", "")
    if cat:
        parts.append(f"Category: {cat}" + (f" / {subcat}" if subcat else ""))

    desc = clean_text(inc.get("description", "") or "")
    if desc:
        parts.append(f"Description: {desc}")

    cn = clean_text(inc.get("close_notes", "") or "")
    if cn:
        parts.append(f"Resolution: {cn}")

    cmdb = extract_display_value(inc.get("cmdb_ci", ""))
    if cmdb:
        parts.append(f"System: {cmdb}")

    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Ingest ServiceNow incidents")
    parser.add_argument("--max", type=int, default=None, help="Max incidents to fetch")
    parser.add_argument("--with-notes", action="store_true", help="Also fetch work notes (slower)")
    parser.add_argument("--output", type=str, default=None, help="Output JSON path")
    args = parser.parse_args()

    # Initialize client
    client = ServiceNowClient()

    # Query: Real Vision/GK POS/Finance incidents before Dec 25 2025
    # Exclude "RANDOM TEST DATA" prefixed incidents
    query = (
        "opened_at<2025-12-25"
        "^short_descriptionLIKEVision"
        "^ORshort_descriptionLIKEfinance posting"
        "^ORshort_descriptionLIKEMissing Order"
        "^ORshort_descriptionLIKEGK POS"
        "^ORshort_descriptionLIKEIDOC"
        "^short_descriptionNOT LIKErandom test"
        "^close_notesISNOTEMPTY"
        "^ORDERBYDESCopened_at"
    )

    # Count first
    total = client.count_table("incident", query)
    logger.info(f"Total matching incidents: {total}")

    if args.max:
        logger.info(f"Limiting to {args.max} incidents")

    # Fetch incidents
    incidents_raw = client.fetch_incidents_batch(
        query=query,
        batch_size=200,
        max_total=args.max,
    )

    logger.info(f"Processing {len(incidents_raw)} incidents...")

    # Transform and enrich
    incidents = []
    for raw in incidents_raw:
        inc = {
            "incident_number": raw.get("number", ""),
            "sys_id": raw.get("sys_id", ""),
            "short_description": raw.get("short_description", ""),
            "description": raw.get("description", "") or "",
            "category": raw.get("category", ""),
            "subcategory": raw.get("subcategory", ""),
            "priority": raw.get("priority", ""),
            "state": raw.get("state", ""),
            "close_notes": raw.get("close_notes", "") or "",
            "close_code": raw.get("close_code", "") or "",
            "assignment_group": extract_display_value(raw.get("assignment_group", "")),
            "assigned_to": extract_display_value(raw.get("assigned_to", "")),
            "cmdb_ci": extract_display_value(raw.get("cmdb_ci", "")),
            "business_service": extract_display_value(raw.get("business_service", "")),
            "opened_at": raw.get("opened_at", ""),
            "resolved_at": raw.get("resolved_at", "") or "",
            "closed_at": raw.get("closed_at", "") or "",
            "problem_id": extract_display_value(raw.get("problem_id", "")),
            "parent_incident": extract_display_value(raw.get("parent_incident", "")),
            "cleaned_text": clean_text(raw.get("short_description", "")),
            "embedding_text": build_embedding_text(raw),
            "systems_involved": detect_systems(
                (raw.get("short_description", "") or "") + " " +
                (raw.get("description", "") or "") + " " +
                (raw.get("close_notes", "") or "") + " " +
                extract_display_value(raw.get("cmdb_ci", ""))
            ),
        }

        # Compute time to resolve
        if inc["opened_at"] and inc["resolved_at"]:
            try:
                opened = datetime.strptime(inc["opened_at"], "%Y-%m-%d %H:%M:%S")
                resolved = datetime.strptime(inc["resolved_at"], "%Y-%m-%d %H:%M:%S")
                inc["time_to_resolve_hours"] = round((resolved - opened).total_seconds() / 3600, 2)
            except ValueError:
                inc["time_to_resolve_hours"] = None
        else:
            inc["time_to_resolve_hours"] = None

        incidents.append(inc)

    # Optionally fetch work notes (much slower — one API call per incident)
    if args.with_notes:
        logger.info("Fetching work notes for each incident (this will take a while)...")
        for i, inc in enumerate(incidents):
            if inc["sys_id"]:
                notes = client.fetch_work_notes(inc["sys_id"])
                inc["work_notes"] = notes
                if (i + 1) % 50 == 0:
                    logger.info(f"  Work notes progress: {i+1}/{len(incidents)}")
            else:
                inc["work_notes"] = []

    # Stats
    has_close = sum(1 for i in incidents if i["close_notes"])
    has_desc = sum(1 for i in incidents if i["description"])
    has_cmdb = sum(1 for i in incidents if i["cmdb_ci"])
    has_problem = sum(1 for i in incidents if i["problem_id"])

    embed_lengths = [len(i["embedding_text"]) for i in incidents]
    embed_lengths.sort()

    logger.info(f"\n{'='*60}")
    logger.info(f"INGESTION COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Total incidents:     {len(incidents)}")
    logger.info(f"Has close notes:     {has_close}/{len(incidents)} ({has_close*100//max(len(incidents),1)}%)")
    logger.info(f"Has description:     {has_desc}/{len(incidents)} ({has_desc*100//max(len(incidents),1)}%)")
    logger.info(f"Has CMDB CI:         {has_cmdb}/{len(incidents)} ({has_cmdb*100//max(len(incidents),1)}%)")
    logger.info(f"Has problem ID:      {has_problem}/{len(incidents)} ({has_problem*100//max(len(incidents),1)}%)")
    logger.info(f"Embedding text avg:  {sum(embed_lengths)//max(len(embed_lengths),1)} chars / ~{sum(embed_lengths)//max(len(embed_lengths),1)//4} tokens")
    logger.info(f"Embedding text max:  {embed_lengths[-1] if embed_lengths else 0} chars / ~{(embed_lengths[-1] if embed_lengths else 0)//4} tokens")

    # Save
    output_dir = Path(args.output).parent if args.output else OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output or str(output_dir / f"sn_incidents_{len(incidents)}.json")

    with open(output_path, "w") as f:
        json.dump(incidents, f, indent=2, default=str)

    logger.info(f"Saved to: {output_path}")
    logger.info(f"File size: {os.path.getsize(output_path) / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
