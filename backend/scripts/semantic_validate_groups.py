"""
REX-US — Semantic Validation of Group Matches

For every "wrong_suggestion" in wave results, compares the actual PRB and
predicted PRB using OpenAI embeddings to determine if they describe the
same issue pattern (semantic group match) vs genuinely different issues.

This validates the group match claim with LLM-backed semantic similarity
instead of just shared CMDB systems.

Usage:
    python semantic_validate_groups.py
    python semantic_validate_groups.py --wave wave_2
    python semantic_validate_groups.py --threshold 0.70
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from collections import defaultdict

from dotenv import load_dotenv
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path, override=True)

import psycopg2
from urllib.parse import urlparse, unquote
from openai import OpenAI
import numpy as np

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


def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def get_prb_description(cur, problem_id: str) -> str:
    """Build a representative description for a PRB from its tagged incidents."""
    cur.execute("""
        SELECT short_description, cmdb_ci, category, close_notes
        FROM rexus_incidents
        WHERE problem_id = %s AND problem_id IS NOT NULL
        ORDER BY opened_at DESC
        LIMIT 10
    """, (problem_id,))
    rows = cur.fetchall()
    if not rows:
        return f"Problem {problem_id}: no incidents found"

    # Build representative text from top incidents
    parts = [f"Problem {problem_id}:"]
    systems = set()
    categories = set()
    descriptions = []

    for sd, cmdb, cat, cn in rows:
        if sd:
            descriptions.append(sd)
        if cmdb:
            systems.add(cmdb)
        if cat:
            categories.add(cat)

    if systems:
        parts.append(f"Systems: {', '.join(list(systems)[:5])}")
    if categories:
        parts.append(f"Categories: {', '.join(list(categories)[:3])}")
    # Use unique descriptions (deduplicated)
    unique_descs = list(dict.fromkeys(descriptions))[:5]
    parts.append("Typical issues: " + " | ".join(unique_descs))

    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wave", default=None, help="Specific wave (e.g. wave_2). Default: all waves.")
    parser.add_argument("--threshold", type=float, default=0.70, help="Cosine similarity threshold for group match")
    args = parser.parse_args()

    conn = get_db()
    cur = conn.cursor()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Get all wrong suggestions
    if args.wave:
        cur.execute("""
            SELECT wave, incident_number, actual_problem_id, predicted_problem_id, confidence_score
            FROM rexus_wave_results
            WHERE problem_match_type = 'wrong_suggestion' AND wave = %s
            ORDER BY wave, incident_number
        """, (args.wave,))
    else:
        cur.execute("""
            SELECT wave, incident_number, actual_problem_id, predicted_problem_id, confidence_score
            FROM rexus_wave_results
            WHERE problem_match_type = 'wrong_suggestion'
            ORDER BY wave, incident_number
        """)

    wrongs = cur.fetchall()
    logger.info(f"Found {len(wrongs)} wrong suggestions to validate")

    # Collect unique PRB pairs to minimize embedding calls
    prb_pairs = set()
    for wave, inc, actual, pred, conf in wrongs:
        pair = tuple(sorted([actual.upper(), pred.upper()]))
        prb_pairs.add(pair)

    logger.info(f"Unique PRB pairs: {len(prb_pairs)}")

    # Get descriptions and embed each unique PRB
    prb_descriptions = {}
    prb_embeddings = {}
    unique_prbs = set()
    for a, b in prb_pairs:
        unique_prbs.add(a)
        unique_prbs.add(b)

    logger.info(f"Unique PRBs to embed: {len(unique_prbs)}")

    # Build descriptions
    for prb in unique_prbs:
        prb_descriptions[prb] = get_prb_description(cur, prb)

    # Batch embed (max 100 at a time)
    prb_list = list(unique_prbs)
    for i in range(0, len(prb_list), 100):
        batch = prb_list[i:i + 100]
        texts = [prb_descriptions[p] for p in batch]
        logger.info(f"Embedding batch {i // 100 + 1} ({len(batch)} PRBs)...")
        resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
        for j, emb in enumerate(resp.data):
            prb_embeddings[batch[j]] = emb.embedding

    # Compute similarity for each pair
    pair_similarity = {}
    for a, b in prb_pairs:
        sim = cosine_similarity(prb_embeddings[a], prb_embeddings[b])
        pair_similarity[(a, b)] = sim

    # Classify each wrong suggestion
    results_by_wave = defaultdict(lambda: {"semantic_group": 0, "real_miss": 0, "total": 0, "details": []})

    for wave, inc, actual, pred, conf in wrongs:
        pair = tuple(sorted([actual.upper(), pred.upper()]))
        sim = pair_similarity[pair]
        is_semantic_group = sim >= args.threshold

        results_by_wave[wave]["total"] += 1
        if is_semantic_group:
            results_by_wave[wave]["semantic_group"] += 1
        else:
            results_by_wave[wave]["real_miss"] += 1
        results_by_wave[wave]["details"].append({
            "incident": inc,
            "actual": actual,
            "predicted": pred,
            "similarity": round(sim, 4),
            "is_group": is_semantic_group,
        })

    # Print results
    print()
    print("=" * 80)
    print(f"SEMANTIC VALIDATION RESULTS (threshold={args.threshold})")
    print("=" * 80)

    grand_total = 0
    grand_group = 0
    grand_real = 0

    for wave in sorted(results_by_wave.keys()):
        r = results_by_wave[wave]

        # Get full wave counts
        cur.execute("""SELECT problem_match_type, COUNT(*) FROM rexus_wave_results WHERE wave = %s GROUP BY problem_match_type""", (wave,))
        counts = dict(cur.fetchall())
        exact = counts.get('exact_match', 0)
        top3 = counts.get('top3_match', 0)
        wrong = counts.get('wrong_suggestion', 0)
        missed = counts.get('missed_suggestion', 0)
        testable = exact + top3 + wrong + missed
        strict = exact + top3

        print(f"\n{wave.upper()}:")
        print(f"  Wrong suggestions: {r['total']}")
        print(f"  Semantic group match (sim >= {args.threshold}): {r['semantic_group']} ({r['semantic_group'] * 100 // r['total'] if r['total'] else 0}%)")
        print(f"  Real miss (sim < {args.threshold}): {r['real_miss']} ({r['real_miss'] * 100 // r['total'] if r['total'] else 0}%)")
        adjusted = strict + r['semantic_group']
        total_real_miss = r['real_miss'] + missed
        print(f"  Strict accuracy:   {strict}/{testable} = {strict * 100 // testable if testable else 0}%")
        print(f"  Adjusted accuracy: {adjusted}/{testable} = {adjusted * 100 // testable if testable else 0}%")
        print(f"  Real miss rate:    {total_real_miss}/{testable} = {total_real_miss * 100 // testable if testable else 0}%")

        grand_total += r['total']
        grand_group += r['semantic_group']
        grand_real += r['real_miss']

        # Show real misses
        real_misses = [d for d in r['details'] if not d['is_group']]
        if real_misses:
            print(f"  Real misses:")
            for d in real_misses[:10]:
                print(f"    {d['incident']}: actual={d['actual']} pred={d['predicted']} sim={d['similarity']:.3f}")

    print(f"\n{'=' * 80}")
    print(f"GRAND TOTAL across all waves:")
    print(f"  Wrong suggestions validated: {grand_total}")
    print(f"  Semantic group matches: {grand_group} ({grand_group * 100 // grand_total if grand_total else 0}%)")
    print(f"  Real misses: {grand_real} ({grand_real * 100 // grand_total if grand_total else 0}%)")
    print(f"{'=' * 80}")

    # Save results
    output = {
        "threshold": args.threshold,
        "total_wrong": grand_total,
        "semantic_group": grand_group,
        "real_miss": grand_real,
        "waves": {
            wave: {
                "semantic_group": r["semantic_group"],
                "real_miss": r["real_miss"],
                "total": r["total"],
            }
            for wave, r in results_by_wave.items()
        },
        "pair_similarities": {f"{a}|{b}": round(s, 4) for (a, b), s in sorted(pair_similarity.items())},
    }
    outpath = Path(__file__).parent.parent.parent / "data/semantic_validation_results.json"
    with open(outpath, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to {outpath}")

    conn.close()


if __name__ == "__main__":
    main()
