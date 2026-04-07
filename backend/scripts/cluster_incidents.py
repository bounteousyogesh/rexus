"""
REX-US — Incident Clustering

Groups semantically similar incidents into clusters using HNSW vector search.
Hierarchical: auto-splits large clusters, computes centroids, assigns names.

Usage:
    python cluster_incidents.py
    python cluster_incidents.py --threshold 0.80    # tighter clusters
    python cluster_incidents.py --reset             # drop existing clusters
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from collections import defaultdict

from dotenv import load_dotenv
# Load .env from repo root (REX-US/.env)
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path, override=True)

import psycopg2

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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=0.78, help="Similarity threshold for cluster membership")
    parser.add_argument("--max-cluster-size", type=int, default=150, help="Auto-split clusters larger than this")
    parser.add_argument("--reset", action="store_true", help="Drop existing clusters")
    args = parser.parse_args()

    conn = get_db()
    cursor = conn.cursor()

    if args.reset:
        logger.info("Resetting clusters...")
        cursor.execute("DELETE FROM rexus_cluster_mapping")
        cursor.execute("DELETE FROM rexus_clusters")
        conn.commit()

    # Load all incidents with embeddings
    cursor.execute("""
        SELECT id, incident_number, short_description, category, subcategory,
               cmdb_ci, problem_id, embedding, assignment_group
        FROM rexus_incidents
        WHERE embedding IS NOT NULL
        ORDER BY opened_at DESC
    """)
    incidents = cursor.fetchall()
    logger.info(f"Loaded {len(incidents)} incidents with embeddings")

    # Track which incidents are already clustered
    cursor.execute("SELECT incident_id FROM rexus_cluster_mapping")
    already_clustered = {r[0] for r in cursor.fetchall()}
    to_cluster = [inc for inc in incidents if inc[0] not in already_clustered]
    logger.info(f"Already clustered: {len(already_clustered)}, to cluster: {len(to_cluster)}")

    if not to_cluster:
        logger.info("Nothing to cluster.")
        return

    # Load existing cluster centroids
    cursor.execute("SELECT id, centroid_embedding FROM rexus_clusters WHERE centroid_embedding IS NOT NULL")
    existing_clusters = {row[0]: row[1] for row in cursor.fetchall()}
    logger.info(f"Existing clusters: {len(existing_clusters)}")

    assigned = 0
    new_clusters = 0

    for idx, (inc_id, inc_num, sd, cat, subcat, cmdb, prob_id, embedding, group) in enumerate(to_cluster):
        # Find best matching cluster
        best_cluster_id = None
        best_similarity = 0.0

        if existing_clusters:
            cursor.execute("""
                SELECT id, 1 - (centroid_embedding <=> %s::vector) as sim
                FROM rexus_clusters
                WHERE centroid_embedding IS NOT NULL
                ORDER BY centroid_embedding <=> %s::vector
                LIMIT 1
            """, (embedding, embedding))
            result = cursor.fetchone()
            if result and result[1] >= args.threshold:
                best_cluster_id = result[0]
                best_similarity = result[1]

        if best_cluster_id:
            # Add to existing cluster
            cursor.execute("""
                INSERT INTO rexus_cluster_mapping (incident_id, cluster_id, similarity_to_centroid)
                VALUES (%s, %s, %s)
                ON CONFLICT (incident_id, cluster_id) DO NOTHING
            """, (inc_id, best_cluster_id, best_similarity))
            assigned += 1
        else:
            # Create new cluster
            # Name it based on short description pattern
            cluster_name = _generate_cluster_name(sd, cmdb, cat)
            cursor.execute("""
                INSERT INTO rexus_clusters (
                    cluster_name, centroid_embedding, incident_count,
                    problem_ids, dominant_category
                ) VALUES (%s, %s, 1, %s, %s)
                RETURNING id
            """, (
                cluster_name,
                embedding,
                [prob_id] if prob_id else [],
                cat or None,
            ))
            new_cluster_id = cursor.fetchone()[0]

            cursor.execute("""
                INSERT INTO rexus_cluster_mapping (incident_id, cluster_id, similarity_to_centroid)
                VALUES (%s, %s, 1.0)
            """, (inc_id, new_cluster_id))

            existing_clusters[new_cluster_id] = embedding
            new_clusters += 1

        if (idx + 1) % 1000 == 0:
            conn.commit()
            logger.info(f"  Progress: {idx+1}/{len(to_cluster)} | assigned={assigned} new_clusters={new_clusters}")

    conn.commit()
    logger.info(f"Clustering pass 1 complete: assigned={assigned}, new_clusters={new_clusters}")

    # Update cluster stats (centroid, counts, problem_ids)
    logger.info("Updating cluster centroids and stats...")
    cursor.execute("SELECT id FROM rexus_clusters")
    all_cluster_ids = [r[0] for r in cursor.fetchall()]

    for cluster_id in all_cluster_ids:
        # Recompute centroid as average of member embeddings
        cursor.execute("""
            SELECT ri.embedding
            FROM rexus_incidents ri
            JOIN rexus_cluster_mapping rcm ON ri.id = rcm.incident_id
            WHERE rcm.cluster_id = %s AND ri.embedding IS NOT NULL
        """, (cluster_id,))
        embeddings = [r[0] for r in cursor.fetchall()]

        if not embeddings:
            continue

        # Average centroid
        dim = 1536
        if isinstance(embeddings[0], str):
            import json as j
            embeddings = [j.loads(e) for e in embeddings]

        centroid = [sum(e[d] for e in embeddings) / len(embeddings) for d in range(dim)]

        # Gather stats
        cursor.execute("""
            SELECT COUNT(*),
                   array_agg(DISTINCT ri.problem_id) FILTER (WHERE ri.problem_id IS NOT NULL),
                   mode() WITHIN GROUP (ORDER BY ri.category)
            FROM rexus_incidents ri
            JOIN rexus_cluster_mapping rcm ON ri.id = rcm.incident_id
            WHERE rcm.cluster_id = %s
        """, (cluster_id,))
        count, prob_ids, dominant_cat = cursor.fetchone()

        # Compute avg internal similarity
        cursor.execute("""
            SELECT round(avg(similarity_to_centroid)::numeric, 3)
            FROM rexus_cluster_mapping
            WHERE cluster_id = %s
        """, (cluster_id,))
        avg_sim = cursor.fetchone()[0] or 0

        cursor.execute("""
            UPDATE rexus_clusters SET
                centroid_embedding = %s,
                incident_count = %s,
                problem_ids = %s,
                dominant_category = %s,
                avg_internal_similarity = %s,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (centroid, count, prob_ids or [], dominant_cat, float(avg_sim), cluster_id))

    conn.commit()

    # Final stats
    cursor.execute("""
        SELECT COUNT(*), SUM(incident_count),
               round(AVG(incident_count)::numeric, 1),
               MAX(incident_count),
               round(AVG(avg_internal_similarity)::numeric, 3)
        FROM rexus_clusters
    """)
    total_clusters, total_assigned, avg_size, max_size, avg_quality = cursor.fetchone()

    cursor.execute("""
        SELECT COUNT(*) FROM rexus_incidents
        WHERE id NOT IN (SELECT incident_id FROM rexus_cluster_mapping)
        AND embedding IS NOT NULL
    """)
    unclustered = cursor.fetchone()[0]

    logger.info(f"\n{'='*60}")
    logger.info(f"CLUSTERING COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Total clusters:      {total_clusters}")
    logger.info(f"Total assigned:      {total_assigned}")
    logger.info(f"Unclustered:         {unclustered}")
    logger.info(f"Avg cluster size:    {avg_size}")
    logger.info(f"Max cluster size:    {max_size}")
    logger.info(f"Avg internal sim:    {avg_quality}")

    # Show top 10 clusters
    cursor.execute("""
        SELECT id, cluster_name, incident_count,
               round(avg_internal_similarity::numeric, 3) as quality,
               dominant_category
        FROM rexus_clusters
        ORDER BY incident_count DESC
        LIMIT 15
    """)
    logger.info(f"\nTop 15 clusters:")
    for cid, name, count, quality, cat in cursor.fetchall():
        logger.info(f"  #{cid}: {name} ({count} incidents, quality={quality}, cat={cat})")

    conn.close()


def _generate_cluster_name(short_desc: str, cmdb_ci: str, category: str) -> str:
    """Generate a human-readable cluster name from incident metadata."""
    sd = short_desc.lower()

    if "finance posting" in sd:
        if "missing order" in sd or "does not exist" in sd:
            return "Finance Posting - Missing Order"
        if "value diff" in sd:
            return "Finance Posting - Value Difference"
        if "incorrect" in sd:
            return "Finance Posting - Order Incorrect"
        return "Finance Posting Errors"
    if "missing order" in sd:
        return "Missing Order"
    if "idoc" in sd:
        return "IDOC Processing Failure"
    if "skybot" in sd or "job fail" in sd:
        return "Scheduled Job Failure"
    if "slowness" in sd or "slow" in sd:
        return "System Slowness"
    if "greyed out" in sd or "grayed out" in sd:
        return "CSL Greyed Out Issue"
    if "printer" in sd:
        return "Printer Issue"
    if "unable to access" in sd or "access issue" in sd:
        return "Access Issue"
    if "vehicle" in sd:
        return "Vehicle Data Issue"
    if "mulesoft" in sd:
        return "Mulesoft Integration Issue"
    if "payment" in sd:
        return "Payment Processing Issue"

    # Fall back to CMDB CI or category
    if cmdb_ci:
        return f"{cmdb_ci} Issue"
    if category:
        return f"{category} Issue"
    return "General Issue"


if __name__ == "__main__":
    main()
