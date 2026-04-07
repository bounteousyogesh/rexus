"""
REX-US — Grounded Playbook Generator

Generates playbooks from REAL resolution data in close_notes.
The LLM synthesizes and organizes — it does NOT invent steps.

Usage:
    python generate_playbooks.py
    python generate_playbooks.py --min-size 10    # only clusters with 10+ incidents
    python generate_playbooks.py --top 20         # only top 20 clusters
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from collections import Counter

from dotenv import load_dotenv
# Load .env from repo root (REX-US/.env)
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path, override=True)

import psycopg2
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def get_db():
    from urllib.parse import urlparse, unquote
    url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "").replace("postgresql://", "http://")
    parsed = urlparse(url)
    return psycopg2.connect(
        host=parsed.hostname or "localhost",
        port=parsed.port or 5432,
        database=unquote(parsed.path.lstrip("/").split("?")[0]),
        user=unquote(parsed.username) if parsed.username else "rexus",
        password=unquote(parsed.password) if parsed.password else "",
    )


def get_cluster_resolution_data(cursor, cluster_id: int, max_incidents: int = 30) -> dict:
    """Pull actual resolution data from a cluster's incidents."""
    cursor.execute("""
        SELECT ri.incident_number, ri.short_description, ri.close_notes,
               ri.cmdb_ci, ri.assignment_group, ri.category, ri.subcategory,
               ri.problem_id, ri.systems_involved,
               ri.time_to_resolve_hours,
               rcm.similarity_to_centroid
        FROM rexus_incidents ri
        JOIN rexus_cluster_mapping rcm ON ri.id = rcm.incident_id
        WHERE rcm.cluster_id = %s
          AND ri.close_notes IS NOT NULL
          AND length(ri.close_notes) > 5
        ORDER BY rcm.similarity_to_centroid DESC
        LIMIT %s
    """, (cluster_id, max_incidents))

    rows = cursor.fetchall()

    incidents = []
    close_notes_all = []
    assignment_groups = []
    cmdb_cis = []
    systems = []
    resolve_times = []

    for row in rows:
        inc_num, sd, cn, cmdb, group, cat, subcat, prob, sys_inv, ttr, sim = row
        incidents.append({
            "number": inc_num,
            "title": sd,
            "close_notes": cn,
            "cmdb_ci": cmdb,
            "group": group,
            "problem_id": prob,
        })
        if cn and len(cn.strip()) > 5:
            close_notes_all.append(f"[{inc_num}]: {cn.strip()}")
        if group:
            assignment_groups.append(group)
        if cmdb:
            cmdb_cis.append(cmdb)
        if sys_inv:
            systems.extend(sys_inv)
        if ttr and ttr > 0:
            resolve_times.append(ttr)

    return {
        "incidents": incidents,
        "close_notes_text": "\n\n".join(close_notes_all[:20]),  # Top 20 most relevant
        "top_groups": Counter(assignment_groups).most_common(3),
        "top_cmdb": Counter(cmdb_cis).most_common(3),
        "top_systems": Counter(systems).most_common(5),
        "avg_resolve_hours": round(sum(resolve_times) / len(resolve_times), 1) if resolve_times else None,
        "total_with_notes": len(close_notes_all),
    }


def generate_grounded_playbook(client: OpenAI, cluster_name: str, cluster_size: int,
                                resolution_data: dict) -> tuple:
    """Generate a playbook grounded in real close_notes. Returns (content, grounding_score)."""

    if not resolution_data["close_notes_text"]:
        return None, 0.0

    top_groups = ", ".join(f"{g} ({c})" for g, c in resolution_data["top_groups"])
    top_cmdb = ", ".join(f"{c} ({n})" for c, n in resolution_data["top_cmdb"])
    top_systems = ", ".join(f"{s} ({n})" for s, n in resolution_data["top_systems"])

    system_prompt = """You are a technical writer creating a troubleshooting playbook for DT (Discount Tire) support engineers.

CRITICAL RULES:
1. ONLY include resolution steps that appear in the evidence below. Do NOT invent steps.
2. Every step must be traceable to at least one incident's close notes.
3. If evidence is thin, say so — mark the playbook as "Low Confidence" rather than filling gaps with guesses.
4. Use the exact technical terms from the close notes (e.g., "poslog", "IDOC", "MuleSoft", "SAP OMS").
5. Cite incident numbers when a step comes from a specific resolution."""

    user_prompt = f"""Create a playbook for the following cluster of {cluster_size} similar incidents.

CLUSTER: {cluster_name}
INCIDENTS WITH CLOSE NOTES: {resolution_data['total_with_notes']}
TOP ASSIGNMENT GROUPS: {top_groups}
TOP SYSTEMS: {top_cmdb}
AFFECTED PLATFORMS: {top_systems}
AVG RESOLUTION TIME: {resolution_data['avg_resolve_hours']}h

=== ACTUAL RESOLUTION DATA (close_notes from real incidents) ===

{resolution_data['close_notes_text']}

=== END OF EVIDENCE ===

Generate a Markdown playbook with these sections:
1. **Overview** — What this issue pattern is (1-2 sentences, from the evidence)
2. **Affected Systems** — List systems involved (from evidence only)
3. **Common Root Causes** — What typically causes this (from close notes patterns)
4. **Resolution Steps** — Step-by-step, each step citing which incident(s) it came from
5. **Escalation Path** — Which team handles this (from assignment group data)
6. **Confidence** — Rate as High (15+ incidents with clear pattern), Medium (5-15), or Low (<5 or ambiguous)

Keep it concise and actionable. Support engineers will use this during live incidents."""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=2000,
    )

    content = response.choices[0].message.content

    # Grounding score based on evidence quality
    notes_count = resolution_data["total_with_notes"]
    if notes_count >= 15:
        grounding = 0.9
    elif notes_count >= 5:
        grounding = 0.7
    elif notes_count >= 2:
        grounding = 0.5
    else:
        grounding = 0.3

    return content, grounding


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-size", type=int, default=5, help="Min cluster size for playbook")
    parser.add_argument("--top", type=int, default=30, help="Generate for top N clusters")
    args = parser.parse_args()

    conn = get_db()
    cursor = conn.cursor()

    # Get clusters sorted by size
    cursor.execute("""
        SELECT id, cluster_name, incident_count, avg_internal_similarity
        FROM rexus_clusters
        WHERE incident_count >= %s
        ORDER BY incident_count DESC
        LIMIT %s
    """, (args.min_size, args.top))
    clusters = cursor.fetchall()
    logger.info(f"Generating playbooks for {len(clusters)} clusters (min_size={args.min_size})")

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    generated = 0

    for cluster_id, name, size, quality in clusters:
        logger.info(f"  Cluster #{cluster_id}: {name} ({size} incidents, quality={quality})")

        # Get real resolution data
        res_data = get_cluster_resolution_data(cursor, cluster_id)

        if res_data["total_with_notes"] < 2:
            logger.info(f"    Skipping — only {res_data['total_with_notes']} incidents with useful close notes")
            continue

        # Generate grounded playbook
        content, grounding_score = generate_grounded_playbook(client, name, size, res_data)

        if not content:
            logger.info(f"    Skipping — no content generated")
            continue

        # Source incidents used
        source_incidents = [i["number"] for i in res_data["incidents"][:20]]

        # Save to database
        cursor.execute("""
            INSERT INTO rexus_playbooks (
                cluster_id, title, content,
                source_incident_count, source_incidents,
                grounding_score, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (
            cluster_id,
            f"Playbook: {name}",
            content,
            res_data["total_with_notes"],
            source_incidents,
            grounding_score,
            "draft",
        ))
        conn.commit()
        generated += 1
        logger.info(f"    Generated (grounding={grounding_score}, sources={res_data['total_with_notes']})")

    # Summary
    cursor.execute("SELECT COUNT(*), round(AVG(grounding_score)::numeric, 2) FROM rexus_playbooks")
    total_playbooks, avg_grounding = cursor.fetchone()

    logger.info(f"\n{'='*60}")
    logger.info(f"PLAYBOOK GENERATION COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Generated:        {generated} playbooks")
    logger.info(f"Total in DB:      {total_playbooks}")
    logger.info(f"Avg grounding:    {avg_grounding}")

    conn.close()


if __name__ == "__main__":
    main()
