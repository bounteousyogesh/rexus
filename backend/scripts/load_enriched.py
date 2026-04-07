"""
REX-US — Load Enriched Incidents + Generate Embeddings

Loads enriched JSON data into pgvector DB with richer embeddings.

Embedding text formula:
  Issue: {short_description}
  System: {cmdb_ci} | {category} > {subcategory}
  Root cause: {description (first 300 chars)}
  Initial finding: {first_work_note (first 200 chars)}
  Resolution: {close_notes (first 200 chars)}

Usage:
    python load_enriched.py data/enriched/enriched_training.json --split training
    python load_enriched.py data/enriched/enriched_wave_1.json --split wave_1 --no-embed
"""

import os
import sys
import json
import re
import argparse
import logging
import time
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path, override=True)

import psycopg2
from psycopg2.extras import execute_values
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def clean_for_embedding(text: str) -> str:
    """Remove instance-specific noise from text for embedding."""
    if not text:
        return ""
    text = re.sub(r'\b\d{10}\b', '[ORDER]', text)
    text = re.sub(r'\b[A-Z]{2,3}\s*[-_]?\s*\d{2}\b', '[SITE]', text)
    text = re.sub(r'\$\s*[\d,]+\.?\d*', '$[AMT]', text)
    text = re.sub(r'\bINC\d+\b', '[INC]', text)
    text = re.sub(r'\bPRB\d+\b', '[PRB]', text)
    text = re.sub(r'\bINCTASK\d+\b', '[TASK]', text)
    text = re.sub(r'\b\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\b', '[TS]', text)
    text = re.sub(r'\d{4}-\d{2}-\d{2}', '[DATE]', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:500]  # Cap at 500 chars per field


def extract_first_work_note(work_notes: str) -> str:
    """Extract the first substantive work note (skip automated/short ones)."""
    if not work_notes:
        return ""
    # Work notes are newest-first; we want the earliest substantive one
    notes = re.split(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+-\s+', work_notes)
    # Reverse to get chronological order, skip empty/short
    for note in reversed(notes):
        note = note.strip()
        # Skip automated entries, very short ones, "on it", "updated" type notes
        if len(note) > 50 and not re.match(r'^(on it|updated|\.|\s)*$', note, re.IGNORECASE):
            # Remove the "(Work notes)" prefix
            note = re.sub(r'^[^)]+\(Work notes\)\s*', '', note)
            return note[:300]
    return ""


def build_embedding_text(inc: dict) -> str:
    """Build richer embedding text from enriched incident data."""
    parts = []

    # Core issue
    sd = clean_for_embedding(inc.get('short_description', ''))
    if sd:
        parts.append(f"Issue: {sd}")

    # System context
    cmdb = inc.get('cmdb_ci', '')
    cat = inc.get('category', '')
    subcat = inc.get('subcategory', '')
    if cmdb or cat:
        system_str = f"System: {cmdb}" if cmdb else ""
        if cat:
            system_str += f" | {cat}"
        if subcat:
            system_str += f" > {subcat}"
        parts.append(system_str.strip())

    # Root cause from description
    desc = clean_for_embedding(inc.get('description', ''))
    if desc and len(desc) > 20:
        parts.append(f"Root cause: {desc}")

    # Error category if available
    error_cat = inc.get('u_error_category', '')
    if error_cat:
        parts.append(f"Error: {error_cat}")

    # Correction type
    corr = inc.get('u_correction_type', '')
    if corr:
        parts.append(f"Fix type: {corr}")

    # First work note (investigation trail)
    first_note = extract_first_work_note(inc.get('work_notes', ''))
    if first_note:
        parts.append(f"Investigation: {clean_for_embedding(first_note)}")

    # Close notes summary
    cn = clean_for_embedding(inc.get('close_notes', ''))
    if cn and len(cn) > 10:
        parts.append(f"Resolution: {cn[:200]}")

    return "\n".join(parts)


def get_db():
    from urllib.parse import urlparse, unquote
    url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "").replace("postgresql://", "http://")
    parsed = urlparse(url)
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port,
        database=unquote(parsed.path.lstrip("/").split("?")[0]),
        user=unquote(parsed.username), password=unquote(parsed.password),
    )


def parse_date(val):
    if not val:
        return None
    try:
        return datetime.strptime(val[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        try:
            return datetime.strptime(val[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            return None


def parse_int(val):
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def parse_bool(val):
    if val in (True, 'true', '1', 'yes'):
        return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file", help="Path to enriched JSON file")
    parser.add_argument("--split", required=True, help="Split group: training, wave_1, etc.")
    parser.add_argument("--no-embed", action="store_true", help="Skip embedding generation (for test waves)")
    parser.add_argument("--batch-size", type=int, default=100, help="Embedding batch size")
    args = parser.parse_args()

    with open(args.input_file) as f:
        incidents = json.load(f)

    logger.info(f"Loaded {len(incidents)} incidents from {args.input_file} (split: {args.split})")

    conn = get_db()
    cur = conn.cursor()

    # Insert incidents
    inserted = 0
    for inc in incidents:
        embedding_text = build_embedding_text(inc)

        try:
            cur.execute("""
                INSERT INTO rexus_incidents (
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
                    split_group, embedding_text
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s
                ) ON CONFLICT (incident_number) DO NOTHING
            """, (
                inc.get('number'), inc.get('sys_id'), inc.get('short_description', ''), inc.get('description'),
                inc.get('category'), inc.get('subcategory'), inc.get('priority'), inc.get('severity'), inc.get('impact'), inc.get('urgency'),
                inc.get('state'), inc.get('close_code'),
                inc.get('assignment_group'), inc.get('assigned_to'), inc.get('cmdb_ci'), inc.get('business_service'),
                inc.get('caller_id'), inc.get('location'), inc.get('company'), inc.get('contact_type'), inc.get('opened_by'),
                inc.get('close_notes'), inc.get('u_resolved_by'), inc.get('u_resolution_confirmed_by'),
                inc.get('problem_id') or None, inc.get('parent_incident') or None, inc.get('u_jira_number') or None,
                inc.get('u_order_number') or None, inc.get('u_total_order_amount') or None, inc.get('u_order_type') or None,
                parse_date(inc.get('u_order_date')),
                inc.get('u_financial_impact') or None, parse_bool(inc.get('u_correction')),
                inc.get('u_correction_type') or None, inc.get('u_error_category') or None,
                inc.get('business_duration') or None, parse_int(inc.get('business_stc')),
                inc.get('calendar_duration') or None, parse_int(inc.get('calendar_stc')),
                parse_int(inc.get('reassignment_count')), parse_int(inc.get('reopen_count')),
                parse_bool(inc.get('made_sla')), inc.get('escalation') or None,
                inc.get('work_notes') or None, inc.get('comments') or None,
                parse_date(inc.get('opened_at')), parse_date(inc.get('resolved_at')), parse_date(inc.get('closed_at')),
                args.split, embedding_text,
            ))
            inserted += 1
            if inserted % 1000 == 0:
                conn.commit()
                logger.info(f"  Inserted {inserted}/{len(incidents)}")
        except Exception as e:
            conn.rollback()
            logger.error(f"  Error inserting {inc.get('number')}: {e}")

    conn.commit()
    logger.info(f"Inserted {inserted}/{len(incidents)} incidents")

    # Generate embeddings if requested
    if not args.no_embed:
        logger.info("Generating embeddings...")
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        cur.execute("""
            SELECT id, embedding_text FROM rexus_incidents
            WHERE split_group = %s AND embedding IS NULL AND embedding_text IS NOT NULL
            ORDER BY id
        """, (args.split,))
        rows = cur.fetchall()
        logger.info(f"  {len(rows)} incidents need embeddings")

        batch_size = args.batch_size
        embedded = 0
        start = time.time()

        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            texts = [r[1] for r in batch]
            ids = [r[0] for r in batch]

            try:
                resp = client.embeddings.create(
                    model="text-embedding-3-small",
                    input=texts,
                )
                for j, emb_data in enumerate(resp.data):
                    cur.execute(
                        "UPDATE rexus_incidents SET embedding = %s WHERE id = %s",
                        (emb_data.embedding, ids[j])
                    )
                conn.commit()
                embedded += len(batch)

                if embedded % 500 == 0 or embedded == len(rows):
                    elapsed = time.time() - start
                    rate = embedded / elapsed if elapsed > 0 else 0
                    eta = (len(rows) - embedded) / rate if rate > 0 else 0
                    logger.info(f"  Embedded {embedded}/{len(rows)} ({rate:.0f}/s, ETA {eta:.0f}s)")

            except Exception as e:
                logger.error(f"  Embedding error at batch {i}: {e}")
                conn.rollback()

        elapsed = time.time() - start
        logger.info(f"Embedding complete: {embedded}/{len(rows)} in {elapsed:.0f}s")

    # Verify
    cur.execute("""
        SELECT split_group, COUNT(*) as total,
               COUNT(embedding) as with_embedding,
               COUNT(work_notes) FILTER (WHERE length(work_notes) > 50) as with_notes,
               COUNT(problem_id) FILTER (WHERE problem_id IS NOT NULL) as with_problem
        FROM rexus_incidents
        WHERE split_group = %s
        GROUP BY split_group
    """, (args.split,))
    row = cur.fetchone()
    if row:
        logger.info(f"\n{'='*60}")
        logger.info(f"LOAD COMPLETE — {args.split}")
        logger.info(f"{'='*60}")
        logger.info(f"Total:      {row[1]}")
        logger.info(f"Embedded:   {row[2]}")
        logger.info(f"Work notes: {row[3]}")
        logger.info(f"Problem ID: {row[4]}")

    conn.close()


if __name__ == "__main__":
    main()
