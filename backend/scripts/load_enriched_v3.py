"""
REX-US — Load Enriched Incidents v3

v3 change: Include additional comments in embedding text.
This captures IDoc error text, Initial Finding, error category,
and other details that distinguish sub-patterns within "Vision SO... Incorrect".

Usage:
    python load_enriched_v3.py data/enriched/enriched_training.json --split training
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
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# Generic words to strip
GENERIC_WORDS = {
    "issue", "issues", "error", "errors", "problem", "problems",
    "fix", "fixed", "fixing", "resolve", "resolved", "resolving",
    "ticket", "incident", "please", "help", "needed", "request",
    "update", "updated", "updating", "closing", "closed",
}


def strip_ids(text):
    if not text:
        return ""
    text = re.sub(r'\b\d{10,16}\b', '', text)  # order IDs, IDoc numbers
    text = re.sub(r'\b[A-Z]{2,3}\s*[-_]?\s*\d{2}\b', '', text)  # site codes
    text = re.sub(r'\$\s*[\d,]+\.?\d*', '', text)  # dollar amounts
    text = re.sub(r'\bINC\d+\b', '', text)
    text = re.sub(r'\bPRB\d+\b', '', text)
    text = re.sub(r'\bINCTASK\d+\b', '', text)
    text = re.sub(r'\b\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\b', '', text)
    text = re.sub(r'\d{4}-\d{2}-\d{2}', '', text)
    text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '', text)  # phone
    text = re.sub(r'\b[\w.-]+@[\w.-]+\.\w+\b', '', text)  # email
    text = re.sub(r'Customer\s+Name\s*:\s*\S+(\s+\S+)?', '', text, flags=re.I)
    text = re.sub(r'Customer\s+Phone\s*(Number)?\s*:\s*\S+', '', text, flags=re.I)
    return text


def strip_generic(text):
    words = text.split()
    return " ".join(w for w in words if w.lower().strip(".,;:!?()") not in GENERIC_WORDS)


def clean(text):
    text = strip_ids(text)
    text = strip_generic(text)
    return re.sub(r'\s+', ' ', text).strip()


def extract_from_comments(comments):
    """Extract key details from additional comments — IDoc text, Initial Finding, error info."""
    if not comments or len(comments) < 20:
        return ""

    extracts = []

    # IDoc Text (the critical differentiator)
    m = re.search(r'IDoc\s*Text\s*:\s*(.+?)(?:\n|$)', comments, re.I)
    if m:
        extracts.append(f"IDoc: {m.group(1).strip()}")

    # Initial Finding
    m = re.search(r'Initial\s*(?:analysis\s*)?[Ff]inding[s]?\s*:\s*(.+?)(?:\n|$)', comments, re.I)
    if m and len(m.group(1).strip()) > 3:
        extracts.append(f"Finding: {m.group(1).strip()}")

    # Error Category
    m = re.search(r'Error\s*Category\s*:\s*(.+?)(?:\n|$)', comments, re.I)
    if m and len(m.group(1).strip()) > 2:
        extracts.append(f"Error: {m.group(1).strip()}")

    # POS Event
    m = re.search(r'POS\s*Event\s*:\s*(.+?)(?:\n|$)', comments, re.I)
    if m and len(m.group(1).strip()) > 1:
        extracts.append(f"POS Event: {m.group(1).strip()}")

    # Issue line from email comments
    m = re.search(r'Issue[-:\s]+(.+?)(?:\n|$)', comments, re.I)
    if m and len(m.group(1).strip()) > 10:
        extracts.append(f"Issue detail: {clean(m.group(1).strip())[:150]}")

    return " | ".join(extracts)


def extract_first_work_note(work_notes):
    if not work_notes:
        return ""
    notes = re.split(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+-\s+', work_notes)
    for note in reversed(notes):
        note = note.strip()
        if len(note) > 50 and not re.match(r'^(on it|updated|wip|\.|\s)*$', note, re.I):
            note = re.sub(r'^[^)]+\(Work notes\)\s*', '', note)
            return note[:300]
    return ""


def build_embedding_text_v3(inc):
    """v3 embedding: v2 + additional comments (IDoc text, Initial Finding, etc.)."""
    parts = []

    # Short description
    sd = clean(inc.get('short_description', ''))
    if sd:
        parts.append(f"Issue: {sd}")

    # System context
    cmdb = inc.get('cmdb_ci', '')
    cat = inc.get('category', '')
    subcat = inc.get('subcategory', '')
    if cmdb or cat:
        s = f"System: {cmdb}" if cmdb else ""
        if cat: s += f" | {cat}"
        if subcat: s += f" > {subcat}"
        parts.append(s.strip())

    # Description
    desc = clean(inc.get('description', ''))
    if desc and len(desc) > 15:
        parts.append(f"Root cause: {desc[:300]}")

    # NEW in v3: Extract key details from additional comments
    comments = inc.get('comments', '')
    comment_details = extract_from_comments(comments)
    if comment_details:
        parts.append(f"Details: {comment_details}")

    # Error category (structured field)
    error_cat = inc.get('u_error_category', '')
    if error_cat:
        parts.append(f"Error category: {error_cat}")

    # Correction type
    corr = inc.get('u_correction_type', '')
    if corr:
        parts.append(f"Fix type: {corr}")

    # First work note
    first_note = extract_first_work_note(inc.get('work_notes', ''))
    if first_note:
        parts.append(f"Investigation: {clean(first_note)[:200]}")

    # Close notes
    cn = clean(inc.get('close_notes', ''))
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
    if not val: return None
    try: return datetime.strptime(val[:19], "%Y-%m-%d %H:%M:%S")
    except:
        try: return datetime.strptime(val[:10], "%Y-%m-%d")
        except: return None

def parse_int(val):
    try: return int(val)
    except: return None

def parse_bool(val):
    return val in (True, 'true', '1', 'yes')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file")
    parser.add_argument("--split", required=True)
    parser.add_argument("--no-embed", action="store_true")
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()

    with open(args.input_file) as f:
        incidents = json.load(f)
    logger.info(f"Loaded {len(incidents)} incidents for v3 embedding")

    conn = get_db()
    cur = conn.cursor()

    # Create v3 table
    cur.execute("CREATE TABLE IF NOT EXISTS rexus_incidents_v3 (LIKE rexus_incidents INCLUDING ALL)")
    conn.commit()

    # Show v2 vs v3 embedding comparison for a few incidents
    logger.info("\n=== v2 vs v3 EMBEDDING COMPARISON ===")
    for inc in incidents[:3]:
        comments = inc.get('comments', '')
        v3_details = extract_from_comments(comments)
        if v3_details:
            logger.info(f"  {inc.get('number')}: +Details: {v3_details[:80]}")

    # Insert
    inserted = 0
    for inc in incidents:
        embedding_text = build_embedding_text_v3(inc)
        try:
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
                    business_duration, business_stc, calendar_duration, calendar_stc,
                    reassignment_count, reopen_count, made_sla, escalation,
                    work_notes, comments,
                    opened_at, resolved_at, closed_at,
                    split_group, embedding_text
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s
                ) ON CONFLICT (incident_number) DO UPDATE SET embedding_text = EXCLUDED.embedding_text
            """, (
                inc.get('number'), inc.get('sys_id'), inc.get('short_description', ''), inc.get('description'),
                inc.get('category'), inc.get('subcategory'), inc.get('priority'), inc.get('severity'),
                inc.get('impact'), inc.get('urgency'), inc.get('state'), inc.get('close_code'),
                inc.get('assignment_group'), inc.get('assigned_to'), inc.get('cmdb_ci'), inc.get('business_service'),
                inc.get('caller_id'), inc.get('location'), inc.get('company'), inc.get('contact_type'),
                inc.get('opened_by'), inc.get('close_notes'), inc.get('u_resolved_by'), inc.get('u_resolution_confirmed_by'),
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
            logger.error(f"  Error: {inc.get('number')}: {e}")

    conn.commit()
    logger.info(f"Inserted {inserted} incidents into rexus_incidents_v3")

    # Show how many incidents gained new embedding content from comments
    cur.execute("""
        SELECT COUNT(*) FROM rexus_incidents_v3
        WHERE split_group = %s AND embedding_text LIKE '%%Details:%%'
    """, (args.split,))
    with_details = cur.fetchone()[0]
    logger.info(f"Incidents with comment-derived details: {with_details}/{inserted}")

    # Generate embeddings
    if not args.no_embed:
        logger.info("Generating v3 embeddings...")
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        cur.execute("""
            SELECT id, embedding_text FROM rexus_incidents_v3
            WHERE split_group = %s AND embedding IS NULL AND embedding_text IS NOT NULL
            ORDER BY id
        """, (args.split,))
        rows = cur.fetchall()
        logger.info(f"  {len(rows)} need embeddings")

        embedded = 0
        start = time.time()
        for i in range(0, len(rows), args.batch_size):
            batch = rows[i:i + args.batch_size]
            try:
                resp = client.embeddings.create(model="text-embedding-3-small", input=[r[1] for r in batch])
                for j, emb in enumerate(resp.data):
                    cur.execute("UPDATE rexus_incidents_v3 SET embedding = %s WHERE id = %s",
                                (emb.embedding, batch[j][0]))
                conn.commit()
                embedded += len(batch)
                if embedded % 500 == 0 or embedded == len(rows):
                    elapsed = time.time() - start
                    logger.info(f"  Embedded {embedded}/{len(rows)} ({embedded/elapsed:.0f}/s)")
            except Exception as e:
                logger.error(f"  Embedding error: {e}")
                conn.rollback()

        logger.info(f"v3 Embedding complete: {embedded}/{len(rows)}")

    cur.execute("SELECT COUNT(*), COUNT(embedding) FROM rexus_incidents_v3 WHERE split_group = %s", (args.split,))
    total, with_emb = cur.fetchone()
    logger.info(f"\nv3 COMPLETE — {args.split}: {total} incidents, {with_emb} embedded")
    conn.close()


if __name__ == "__main__":
    main()
