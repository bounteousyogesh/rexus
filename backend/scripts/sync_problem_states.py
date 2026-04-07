"""
REX-US — Cache Problem States from ServiceNow

Fetches all unique problem IDs from our incidents and caches their
current state (Open/Closed/Cancelled) in the rexus_problems table.

Usage:
    python sync_problem_states.py
"""

import os
import sys
import logging
from pathlib import Path
from urllib.parse import urlparse, unquote

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path, override=True)

import psycopg2

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from backend.services.servicenow_client import ServiceNowClient

# CQ-012: Use logging instead of print() for structured, level-controlled output.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def get_db() -> psycopg2.extensions.connection:
    """
    Parse DATABASE_URL and return a psycopg2 connection.
    CQ-007: This is a duplicated helper — see load_to_database.py for context.
    """
    url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
    parsed = urlparse(url)
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        database=unquote(parsed.path.lstrip("/").split("?")[0]),
        user=unquote(parsed.username) if parsed.username else "rexus",
        password=unquote(parsed.password) if parsed.password else "",
    )


def main() -> None:
    conn = get_db()
    cur = conn.cursor()

    # Create table if not exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rexus_problems (
            problem_id VARCHAR(50) PRIMARY KEY,
            short_description TEXT,
            state VARCHAR(50),
            state_display VARCHAR(50),
            priority VARCHAR(50),
            opened_at TIMESTAMP,
            closed_at TIMESTAMP,
            last_synced TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    # Get all unique problem IDs across all incident tables
    cur.execute("""
        SELECT DISTINCT problem_id FROM (
            SELECT problem_id FROM rexus_incidents WHERE problem_id IS NOT NULL AND problem_id != ''
            UNION
            SELECT problem_id FROM rexus_incidents_v3 WHERE problem_id IS NOT NULL AND problem_id != ''
        ) all_prbs
    """)
    all_problems = [r[0] for r in cur.fetchall()]
    logger.info("Found %d unique problem IDs", len(all_problems))

    client = ServiceNowClient()
    inserted = 0

    for i in range(0, len(all_problems), 50):
        batch = all_problems[i:i + 50]
        query = "numberIN" + ",".join(batch)

        try:
            results = client.query_table(
                "problem", query=query,
                fields=["number", "short_description", "state", "priority", "opened_at", "closed_at"],
                display_value=True, limit=50,
            )
        except Exception as e:
            logger.error("Error fetching batch at offset %d: %s", i, e)
            continue

        for p in results:
            num = p.get("number", "")
            state = p.get("state", "")
            state_display = state.get("display_value", "") if isinstance(state, dict) else str(state)
            state_val = str(state.get("value", "")) if isinstance(state, dict) else str(state)
            sd = p.get("short_description", "")
            sd = sd.get("display_value", "") if isinstance(sd, dict) else str(sd or "")
            priority = p.get("priority", "")
            priority = priority.get("display_value", "") if isinstance(priority, dict) else str(priority or "")
            opened = p.get("opened_at") or None
            closed = p.get("closed_at") or None
            if opened == "":
                opened = None
            if closed == "":
                closed = None

            cur.execute("""
                INSERT INTO rexus_problems (problem_id, short_description, state, state_display, priority, opened_at, closed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (problem_id) DO UPDATE SET
                    state = EXCLUDED.state, state_display = EXCLUDED.state_display,
                    short_description = EXCLUDED.short_description, last_synced = CURRENT_TIMESTAMP
            """, (num, sd, state_val, state_display, priority, opened, closed))
            inserted += 1

        conn.commit()

    logger.info("Cached %d problems", inserted)

    cur.execute("SELECT state_display, COUNT(*) FROM rexus_problems GROUP BY state_display ORDER BY COUNT(*) DESC")
    logger.info("Problem states breakdown:")
    for row in cur.fetchall():
        logger.info("  %s: %d", row[0], row[1])

    conn.close()


if __name__ == "__main__":
    main()
