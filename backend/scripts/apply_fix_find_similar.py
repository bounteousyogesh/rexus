"""
One-shot script: applies the rexus_find_similar fix directly to the live DB.

Fetches DATABASE_URL from AWS Secrets Manager (same as start.sh), then runs
the corrected CREATE OR REPLACE FUNCTION statement.

Usage:
    python apply_fix_find_similar.py
    python apply_fix_find_similar.py --verify-only   # just prints current function body
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote

import boto3
import psycopg2

SECRET_NAME = os.getenv("SECRET_NAME", "dt-app-secrets")
AWS_REGION  = os.getenv("AWS_REGION",  "us-west-2")

FIX_SQL = """
CREATE OR REPLACE FUNCTION rexus_find_similar(
    query_embedding vector,
    similarity_threshold FLOAT DEFAULT 0.40,
    max_results INTEGER DEFAULT 15,
    training_only BOOLEAN DEFAULT TRUE
)
RETURNS TABLE (
    incident_id INTEGER,
    incident_number VARCHAR(50),
    short_description TEXT,
    close_notes TEXT,
    similarity_score FLOAT,
    cluster_id INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ri.id,
        ri.incident_number,
        ri.short_description,
        ri.close_notes,
        (1 - (ri.embedding <=> query_embedding))::FLOAT AS similarity_score,
        rcm.cluster_id
    FROM rexus_incidents_v3 ri
    LEFT JOIN rexus_cluster_mapping rcm ON ri.id = rcm.incident_id
    WHERE ri.embedding IS NOT NULL
      AND (NOT training_only OR ri.split_group = 'training')
      AND 1 - (ri.embedding <=> query_embedding) >= similarity_threshold
    ORDER BY ri.embedding <=> query_embedding
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql;
"""

VERIFY_SQL = "SELECT prosrc FROM pg_proc WHERE proname = 'rexus_find_similar';"
ROW_COUNT_SQL = """
SELECT
    COUNT(*) AS total,
    COUNT(embedding) AS with_embeddings,
    COUNT(DISTINCT split_group) AS split_groups,
    string_agg(DISTINCT split_group, ', ' ORDER BY split_group) AS split_group_values
FROM rexus_incidents_v3;
"""


def get_db_url() -> str:
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        print(f"Using DATABASE_URL from environment.")
        return db_url

    print(f"Fetching DATABASE_URL from Secrets Manager: {SECRET_NAME} ({AWS_REGION})")
    sm = boto3.client("secretsmanager", region_name=AWS_REGION)
    secret = json.loads(
        sm.get_secret_value(SecretId=SECRET_NAME)["SecretString"]
    )
    return secret["DATABASE_URL"]


def get_conn(db_url: str):
    url = db_url.replace("+asyncpg", "")
    p = urlparse(url)
    return psycopg2.connect(
        host=p.hostname, port=p.port or 5432,
        database=unquote(p.path.lstrip("/").split("?")[0]),
        user=unquote(p.username) if p.username else "rexus",
        password=unquote(p.password) if p.password else "",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true",
                        help="Only print the current function body and row counts, don't apply the fix")
    args = parser.parse_args()

    db_url = get_db_url()
    conn = get_conn(db_url)
    cur = conn.cursor()

    # Always show current state
    print("\n── Current rexus_find_similar body ──────────────────────")
    cur.execute(VERIFY_SQL)
    row = cur.fetchone()
    if row:
        body = row[0]
        table = "rexus_incidents_v3" if "rexus_incidents_v3" in body else "rexus_incidents (OLD ❌)"
        print(f"  Queries: {table}")
    else:
        print("  Function not found!")

    print("\n── rexus_incidents_v3 row counts ────────────────────────")
    cur.execute(ROW_COUNT_SQL)
    r = cur.fetchone()
    print(f"  Total rows:       {r[0]}")
    print(f"  With embeddings:  {r[1]}")
    print(f"  Split groups:     {r[3] or 'none'}")

    if args.verify_only:
        conn.close()
        return

    if row and "rexus_incidents_v3" in row[0]:
        print("\n✅ Function already targets rexus_incidents_v3 — no fix needed.")
        conn.close()
        return

    print("\n── Applying fix ─────────────────────────────────────────")
    cur.execute(FIX_SQL)
    conn.commit()
    print("✅ rexus_find_similar updated to query rexus_incidents_v3")

    # Verify
    cur.execute(VERIFY_SQL)
    row = cur.fetchone()
    if row and "rexus_incidents_v3" in row[0]:
        print("✅ Verified: function now queries rexus_incidents_v3")
    else:
        print("❌ Verification failed — check DB manually")

    conn.close()


if __name__ == "__main__":
    main()
