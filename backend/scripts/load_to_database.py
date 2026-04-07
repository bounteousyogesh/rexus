"""
REX-US — Database Loader

Loads embedded incidents into PostgreSQL with pgvector.
Creates schema if not exists, inserts incidents, and builds HNSW index.

Usage:
    python load_to_database.py rexus/data/sn_incidents_full_embedded.json
    python load_to_database.py rexus/data/sn_incidents_full_embedded.json --reset  # drop and recreate tables
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
# Prefer rexus/.env, fall back to project root .env
# Load .env from repo root (REX-US/.env)
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path, override=True)

import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def get_db_connection():
    """
    Parse DATABASE_URL and return a psycopg2 connection.
    CQ-007: This helper is duplicated across scripts; consider extracting to
    backend/scripts/_db_utils.py if more scripts need database access.
    CQ-011: Default user corrected to 'rexus' (was incorrectly 'nexus').
    """
    from urllib.parse import urlparse, unquote

    database_url = os.getenv("DATABASE_URL", "")
    # Strip asyncpg prefix if present; urlparse handles postgresql:// natively
    database_url = database_url.replace("+asyncpg", "")

    parsed = urlparse(database_url)
    return psycopg2.connect(
        host=parsed.hostname or "localhost",
        port=parsed.port or 5432,
        database=unquote(parsed.path.lstrip("/").split("?")[0]),
        user=unquote(parsed.username) if parsed.username else "rexus",
        password=unquote(parsed.password) if parsed.password else "",
    )


def parse_timestamp(ts: str):
    """Parse ServiceNow timestamp or return None."""
    if not ts:
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def compute_recency_weight(opened_at: str, reference_date: datetime | None = None) -> float:
    """
    Compute time-decay weight. More recent = higher weight.
    CQ-015: Reference date defaults to today so the weight stays meaningful
    as new incidents are loaded over time (was previously hardcoded to 2025-12-25).
    Pass an explicit reference_date to reproduce historical runs.
    """
    if not opened_at:
        return 0.5
    ref = reference_date or datetime.now()
    try:
        opened = datetime.strptime(opened_at, "%Y-%m-%d %H:%M:%S")
        months_old = (ref - opened).days / 30.0
        return max(0.3, 1.0 - (months_old * 0.04))
    except ValueError:
        return 0.5


def main():
    parser = argparse.ArgumentParser(description="Load embedded incidents into database")
    parser.add_argument("input_file", help="Path to embedded incidents JSON")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate tables")
    args = parser.parse_args()

    # Load data
    with open(args.input_file) as f:
        incidents = json.load(f)

    embedded = [i for i in incidents if i.get("embedding") is not None]
    logger.info(f"Loaded {len(incidents)} incidents, {len(embedded)} with embeddings")

    if not embedded:
        logger.error("No embedded incidents found. Run generate_embeddings.py first.")
        return

    # Connect
    conn = get_db_connection()
    cursor = conn.cursor()
    logger.info("Connected to database")

    # Run schema migration
    schema_path = Path(__file__).parent.parent / "migrations" / "001_rexus_schema.sql"
    if schema_path.exists():
        if args.reset:
            logger.warning("RESETTING: Dropping existing REX-US tables")
            cursor.execute("DROP TABLE IF EXISTS rexus_cluster_mapping CASCADE")
            cursor.execute("DROP TABLE IF EXISTS rexus_work_notes CASCADE")
            cursor.execute("DROP TABLE IF EXISTS rexus_playbooks CASCADE")
            cursor.execute("DROP TABLE IF EXISTS rexus_clusters CASCADE")
            cursor.execute("DROP TABLE IF EXISTS rexus_incidents CASCADE")
            conn.commit()

        logger.info("Running schema migration...")
        with open(schema_path) as f:
            cursor.execute(f.read())
        conn.commit()
        logger.info("Schema migration complete")
    else:
        logger.warning(f"Schema file not found: {schema_path}")

    # Insert incidents
    inserted = 0
    skipped = 0

    for inc in embedded:
        try:
            cursor.execute(
                """
                INSERT INTO rexus_incidents (
                    incident_number, sys_id, problem_id, parent_incident,
                    short_description, description, cleaned_text,
                    category, subcategory, priority, state, close_code,
                    assignment_group, assigned_to, cmdb_ci, business_service,
                    close_notes, opened_at, resolved_at, closed_at,
                    time_to_resolve_hours, systems_involved,
                    embedding, embedding_text, recency_weight
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s
                )
                ON CONFLICT (incident_number) DO UPDATE SET
                    close_notes = EXCLUDED.close_notes,
                    embedding = EXCLUDED.embedding,
                    embedding_text = EXCLUDED.embedding_text,
                    recency_weight = EXCLUDED.recency_weight,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    inc["incident_number"],
                    inc.get("sys_id"),
                    inc.get("problem_id") or None,
                    inc.get("parent_incident") or None,
                    inc["short_description"],
                    inc.get("description") or None,
                    inc.get("cleaned_text", ""),
                    inc.get("category") or None,
                    inc.get("subcategory") or None,
                    inc.get("priority") or None,
                    inc.get("state") or None,
                    inc.get("close_code") or None,
                    inc.get("assignment_group") or None,
                    inc.get("assigned_to") or None,
                    inc.get("cmdb_ci") or None,
                    inc.get("business_service") or None,
                    inc.get("close_notes") or None,
                    parse_timestamp(inc.get("opened_at", "")),
                    parse_timestamp(inc.get("resolved_at", "")),
                    parse_timestamp(inc.get("closed_at", "")),
                    inc.get("time_to_resolve_hours"),
                    inc.get("systems_involved", []),
                    inc["embedding"],
                    inc.get("embedding_text", ""),
                    compute_recency_weight(inc.get("opened_at", "")),
                ),
            )
            inserted += 1

            if inserted % 500 == 0:
                conn.commit()
                logger.info(f"  Inserted {inserted}/{len(embedded)}")

        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            skipped += 1
        except Exception as e:
            conn.rollback()
            logger.error(f"  Error inserting {inc.get('incident_number')}: {e}")
            skipped += 1

    conn.commit()

    # Verify
    cursor.execute("SELECT COUNT(*) FROM rexus_incidents")
    total_in_db = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM rexus_incidents WHERE embedding IS NOT NULL")
    embedded_in_db = cursor.fetchone()[0]

    logger.info(f"\n{'='*60}")
    logger.info(f"DATABASE LOAD COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Inserted:     {inserted}")
    logger.info(f"Skipped:      {skipped}")
    logger.info(f"Total in DB:  {total_in_db}")
    logger.info(f"With vectors: {embedded_in_db}")

    conn.close()


if __name__ == "__main__":
    main()
