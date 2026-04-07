"""
REX-US — Automated Wave Testing

Takes N incidents from a test wave, runs each through the analyzer
(using only intake data — no close_notes, no work_notes, no problem_id),
then compares the system's prediction against the actual resolution.

Usage:
    python run_wave_test.py --wave wave_1 --count 100 --offset 0
    python run_wave_test.py --wave wave_1 --count 100 --offset 100  # next batch
"""

import os
import sys
import json
import time
import argparse
import logging
import asyncio
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path, override=True)

import psycopg2
from urllib.parse import urlparse, unquote
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

API_BASE = "http://localhost:8000/api/v1"


def get_db():
    url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "").replace("postgresql://", "http://")
    parsed = urlparse(url)
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port,
        database=unquote(parsed.path.lstrip("/").split("?")[0]),
        user=unquote(parsed.username), password=unquote(parsed.password),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wave", required=True)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()

    conn = get_db()
    cur = conn.cursor()

    # Get test incidents
    cur.execute("""
        SELECT incident_number, short_description, description,
               category, subcategory, priority, cmdb_ci, assignment_group,
               caller_id, location, impact, urgency,
               -- Actual answers (for comparison)
               problem_id, u_jira_number, close_notes, u_order_number,
               u_correction_type, u_error_category
        FROM rexus_incidents
        WHERE split_group = %s
        ORDER BY opened_at
        OFFSET %s LIMIT %s
    """, (args.wave, args.offset, args.count))

    columns = [desc[0] for desc in cur.description]
    incidents = [dict(zip(columns, row)) for row in cur.fetchall()]

    logger.info(f"Testing {len(incidents)} incidents from {args.wave} (offset={args.offset})")

    results = []
    scores = {"exact_match": 0, "correct_no_match": 0, "wrong_suggestion": 0,
              "missed_suggestion": 0, "no_problem_no_suggestion": 0, "total": 0}

    for i, inc in enumerate(incidents):
        inc_num = inc["incident_number"]
        actual_problem = inc["problem_id"] or ""

        # Build input (intake data only — NO close_notes, work_notes, problem_id)
        input_data = {
            "pdf_fields": {
                "Short description": inc["short_description"] or "",
                "Description": inc["description"] or "",
            },
            "incident_section": {
                "Number": inc_num,
                "Category": inc["category"] or "",
                "Subcategory": inc["subcategory"] or "",
                "Priority": inc["priority"] or "",
                "Configuration item": inc["cmdb_ci"] or "",
                "Assignment group": inc["assignment_group"] or "",
                "Caller": inc["caller_id"] or "",
                "Location": inc["location"] or "",
            },
            "resolution_information_section": {},
        }

        try:
            resp = requests.post(
                f"{API_BASE}/analyze",
                json={"ticket_json": input_data, "limit": 15, "threshold": 0.40},
                timeout=120,
            )
            resp.raise_for_status()
            analysis = resp.json()

            predicted_problem = ""
            all_suggested = []
            pb = analysis.get("focused_playbook", {})
            if pb and pb.get("top_problem"):
                predicted_problem = pb["top_problem"]["id"]
                all_suggested.append(pb["top_problem"]["id"])
            if pb and pb.get("secondary_problem"):
                all_suggested.append(pb["secondary_problem"]["id"])
            # Also count "other_problems" as top-3
            for op in (pb.get("other_problems", []) or [])[:1]:
                all_suggested.append(op)

            confidence = analysis.get("confidence_score", 0)
            match_count = analysis.get("match_count", 0)

            # Score the prediction with nuanced matching
            if actual_problem and predicted_problem:
                if predicted_problem.upper() == actual_problem.upper():
                    match_type = "exact_match"
                elif actual_problem.upper() in [s.upper() for s in all_suggested]:
                    match_type = "top3_match"  # actual is in our top 3 — good
                else:
                    # Check if they're in the same cluster (group match)
                    match_type = "wrong_suggestion"
            elif actual_problem and not predicted_problem:
                match_type = "missed_suggestion"
            elif not actual_problem and not predicted_problem:
                match_type = "no_problem_no_suggest"
            elif not actual_problem and predicted_problem:
                match_type = "suggested_no_actual"
            else:
                match_type = "unknown"

            scores[match_type] = scores.get(match_type, 0) + 1
            scores["total"] += 1

            result = {
                "incident_number": inc_num,
                "actual_problem": actual_problem,
                "predicted_problem": predicted_problem,
                "confidence": round(confidence, 4),
                "match_count": match_count,
                "match_type": match_type,
                "actual_close_notes": (inc.get("close_notes") or "")[:200],
                "actual_jira": inc.get("u_jira_number") or "",
            }
            results.append(result)

            # Save to DB
            cur.execute("""
                INSERT INTO rexus_wave_results
                    (wave, incident_number, input_description, actual_problem_id,
                     actual_close_notes, actual_jira, predicted_problem_id,
                     confidence_score, match_count, problem_match,
                     problem_match_type, analysis_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                args.wave, inc_num, inc["short_description"],
                actual_problem or None, (inc.get("close_notes") or "")[:500],
                inc.get("u_jira_number") or None, predicted_problem or None,
                confidence, match_count,
                match_type == "exact_match",
                match_type, analysis.get("analysis_id"),
            ))
            conn.commit()

            status_icon = {"exact_match": "✓", "top3_match": "≈", "wrong_suggestion": "✗",
                           "missed_suggestion": "⊘", "no_problem_no_suggest": "○", "suggested_no_actual": "○"}.get(match_type, "?")
            logger.info(f"  {status_icon} {i+1}/{len(incidents)} {inc_num}: {match_type} "
                       f"(actual={actual_problem or 'none'}, pred={predicted_problem or 'none'}, "
                       f"all_suggested={all_suggested[:3]}, conf={confidence:.0%})")

        except Exception as e:
            logger.error(f"  ✗ {i+1}/{len(incidents)} {inc_num}: ERROR — {e}")
            conn.rollback()
            scores["total"] += 1
            results.append({"incident_number": inc_num, "match_type": "error", "error": str(e)})

    # ── Scorecard ──────────────────────────────────────────────────
    total = scores["total"]
    exact = scores.get("exact_match", 0)
    top3 = scores.get("top3_match", 0)
    wrong = scores.get("wrong_suggestion", 0)
    missed = scores.get("missed_suggestion", 0)
    no_no = scores.get("no_problem_no_suggest", 0)
    sug_no = scores.get("suggested_no_actual", 0)

    testable = exact + top3 + wrong + missed  # incidents with actual problem

    logger.info(f"\n{'='*60}")
    logger.info(f"WAVE TEST SCORECARD — {args.wave} (offset={args.offset}, count={args.count})")
    logger.info(f"{'='*60}")
    logger.info(f"Total tested:           {total}")
    logger.info(f"")
    logger.info(f"ACCURACY (incidents with actual problem = {testable}):")
    logger.info(f"  ✓ Exact match:        {exact} ({exact*100//testable if testable else 0}%) — predicted == actual")
    logger.info(f"  ≈ Top-3 match:        {top3} ({top3*100//testable if testable else 0}%) — actual in our suggestions")
    logger.info(f"  ✗ Wrong suggestion:   {wrong} ({wrong*100//testable if testable else 0}%) — predicted != actual")
    logger.info(f"  ⊘ Missed:             {missed} ({missed*100//testable if testable else 0}%) — had problem, we didn't suggest")
    logger.info(f"  Combined accuracy:    {(exact+top3)*100//testable if testable else 0}% (exact + top3)")
    logger.info(f"")
    logger.info(f"No problem in actual:   {no_no + sug_no}")
    logger.info(f"  ○ No problem, no suggest: {no_no}")
    logger.info(f"  ○ No problem, we suggested: {sug_no}")
    logger.info(f"  We also didn't suggest:{no_no}")
    logger.info(f"  We suggested anyway:  {sug_no}")
    logger.info(f"")

    avg_conf = sum(r.get("confidence", 0) for r in results) / len(results) if results else 0
    logger.info(f"Avg confidence:         {avg_conf:.0%}")

    # Save scorecard
    scorecard = {
        "wave": args.wave,
        "offset": args.offset,
        "count": args.count,
        "tested": total,
        "scores": scores,
        "problem_match_accuracy": f"{exact*100//testable if testable else 0}%",
        "testable_incidents": testable,
        "avg_confidence": round(avg_conf, 4),
        "timestamp": datetime.now().isoformat(),
    }

    scorecard_path = Path(__file__).parent.parent.parent / f"data/scorecard_{args.wave}_offset{args.offset}.json"
    with open(scorecard_path, "w") as f:
        json.dump(scorecard, f, indent=2)
    logger.info(f"\nScorecard saved to {scorecard_path}")

    # Show top failures for review
    failures = [r for r in results if r.get("match_type") in ("wrong_suggestion", "missed_suggestion")]
    if failures:
        logger.info(f"\n{'='*60}")
        logger.info(f"FAILURES TO REVIEW ({len(failures)})")
        logger.info(f"{'='*60}")
        for r in failures[:20]:
            logger.info(f"  {r['incident_number']}: {r['match_type']} "
                       f"(actual={r.get('actual_problem','')}, pred={r.get('predicted_problem','')}, "
                       f"conf={r.get('confidence',0):.0%})")

    conn.close()


if __name__ == "__main__":
    main()
