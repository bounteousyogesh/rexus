"""
REX-US — LLM Semantic Validation (GPT-5.4)

Validates every "suggested_no_actual" incident using GPT-5.4 to determine
if our problem suggestion was correct, related, or wrong.

Saves EVERY request and response as artifacts for the validation site.

Three categories of incidents:
  1. TESTABLE (has actual PRB): validated by CMDB family expansion
  2. NON-TESTABLE suggested (no actual PRB, we suggested one): validated by LLM
  3. NON-TESTABLE silent (no actual PRB, we didn't suggest): no validation needed

Usage:
    python llm_validate_all.py                    # all waves
    python llm_validate_all.py --wave wave_2      # single wave
    python llm_validate_all.py --resume           # resume from last saved position
"""

import os
import sys
import json
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict

from dotenv import load_dotenv
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path, override=True)

import psycopg2
from urllib.parse import urlparse, unquote
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ARTIFACTS_DIR = Path(__file__).parent.parent.parent / ".artifacts" / "llm_validation"
MODEL = "gpt-5.4"  # Best available model


def get_db():
    url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "").replace("postgresql://", "http://")
    parsed = urlparse(url)
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port,
        database=unquote(parsed.path.lstrip("/").split("?")[0]),
        user=unquote(parsed.username), password=unquote(parsed.password),
    )


def get_prb_evidence(cur, prb: str) -> dict:
    """Get full evidence for a problem record."""
    cur.execute("""
        SELECT incident_number, short_description, description, close_notes,
               cmdb_ci, category, subcategory, u_error_category, u_correction_type,
               priority, assignment_group
        FROM rexus_incidents
        WHERE problem_id = %s AND short_description IS NOT NULL
        ORDER BY opened_at DESC
        LIMIT 10
    """, (prb,))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    # Get aggregate stats
    cur.execute("""
        SELECT COUNT(*) as total,
               COUNT(DISTINCT cmdb_ci) as unique_systems,
               COUNT(DISTINCT category) as unique_categories,
               array_agg(DISTINCT cmdb_ci) FILTER (WHERE cmdb_ci IS NOT NULL) as systems,
               array_agg(DISTINCT category) FILTER (WHERE category IS NOT NULL) as categories
        FROM rexus_incidents WHERE problem_id = %s
    """, (prb,))
    stats = cur.fetchone()

    return {
        "problem_id": prb,
        "total_incidents": stats[0],
        "unique_systems": stats[1],
        "unique_categories": stats[2],
        "systems": stats[3] or [],
        "categories": stats[4] or [],
        "sample_incidents": rows,
    }


def build_prompt(incident: dict, prb_evidence: dict) -> str:
    """Build the validation prompt."""
    # Format PRB evidence
    evidence_text = ""
    for i, inc in enumerate(prb_evidence["sample_incidents"]):
        evidence_text += f"\n  Incident {i+1}: [{inc.get('cmdb_ci', '')}] {inc.get('short_description', '')}"
        if inc.get('description'):
            evidence_text += f"\n    Description: {str(inc['description'])[:200]}"
        if inc.get('close_notes'):
            evidence_text += f"\n    Resolution: {str(inc['close_notes'])[:200]}"
        if inc.get('u_error_category'):
            evidence_text += f"\n    Error category: {inc['u_error_category']}"
        if inc.get('u_correction_type'):
            evidence_text += f"\n    Correction type: {inc['u_correction_type']}"

    prompt = f"""You are a senior IT operations analyst at Discount Tire validating whether a support incident matches a Problem record pattern.

INCIDENT UNDER REVIEW:
  Number: {incident['incident_number']}
  Short Description: {incident.get('short_description', 'N/A')}
  Description: {str(incident.get('description') or 'N/A')[:400]}
  System (CMDB CI): {incident.get('cmdb_ci', 'N/A')}
  Category: {incident.get('category', 'N/A')} > {incident.get('subcategory', 'N/A')}
  Assignment Group: {incident.get('assignment_group', 'N/A')}
  Priority: {incident.get('priority', 'N/A')}
  Error Category: {incident.get('u_error_category', 'N/A')}
  Correction Type: {incident.get('u_correction_type', 'N/A')}
  Close Notes: {str(incident.get('close_notes') or 'N/A')[:400]}

SUGGESTED PROBLEM: {prb_evidence['problem_id']}
  Total incidents in this problem: {prb_evidence['total_incidents']}
  Systems involved: {', '.join(prb_evidence['systems'][:5])}
  Categories: {', '.join(prb_evidence['categories'][:3])}

Representative incidents tagged to this problem:
{evidence_text}

INSTRUCTIONS:
1. Ignore all PII: order numbers (10-digit numbers), store codes, customer names, phone numbers, timestamps, specific dollar amounts, incident/task numbers.
2. Focus on the OPERATIONAL ISSUE PATTERN: What is broken? What system? What type of failure? What is the root cause?
3. Rate the match on a scale of 1-5:
   5 = Identical issue pattern (same root cause, same failure mode, same system)
   4 = Strongly related (same system area, very similar failure, minor variation in root cause)
   3 = Related (same system family, different but adjacent failure mode — the suggestion helps the support engineer)
   2 = Weakly related (same broad domain, but different operational issue — limited value)
   1 = Unrelated (different systems or completely different failure patterns — wrong suggestion)

Respond ONLY in this exact JSON format, no other text:
{{"rating": <integer 1-5>, "incident_pattern": "<one-line summary of the incident's operational issue>", "problem_pattern": "<one-line summary of the PRB's typical issue pattern>", "shared_systems": "<comma-separated list of shared systems or 'none'>", "explanation": "<2-3 sentences explaining your rating, focusing on operational similarity and why this suggestion helps or doesn't help a support engineer>"}}"""

    return prompt


def parse_response(raw: str) -> dict:
    """Parse LLM response JSON."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"rating": 0, "incident_pattern": "parse_error", "problem_pattern": "", "explanation": raw[:500]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wave", default=None, help="Specific wave to validate")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    args = parser.parse_args()

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    conn = get_db()
    cur = conn.cursor()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Load checkpoint if resuming
    checkpoint_file = ARTIFACTS_DIR / "checkpoint.json"
    completed = set()
    if args.resume and checkpoint_file.exists():
        with open(checkpoint_file) as f:
            completed = set(json.load(f).get("completed", []))
        logger.info(f"Resuming — {len(completed)} already validated")

    # Get all suggested_no_actual incidents
    wave_filter = ""
    params = ('suggested_no_actual',)
    if args.wave:
        wave_filter = " AND w.wave = %s"
        params = ('suggested_no_actual', args.wave)

    cur.execute(f"""
        SELECT w.wave, w.incident_number, w.predicted_problem_id, w.confidence_score,
               i.short_description, i.description, i.cmdb_ci, i.category, i.subcategory,
               i.assignment_group, i.priority, i.close_notes, i.close_code,
               i.u_error_category, i.u_correction_type, i.u_order_number
        FROM rexus_wave_results w
        JOIN rexus_incidents i ON i.incident_number = w.incident_number
        WHERE w.problem_match_type = %s{wave_filter}
        ORDER BY w.wave, w.incident_number
    """, params)

    cols = [d[0] for d in cur.description]
    all_incidents = [dict(zip(cols, r)) for r in cur.fetchall()]

    # Filter out already completed
    pending = [inc for inc in all_incidents if inc["incident_number"] not in completed]
    logger.info(f"Total: {len(all_incidents)}, Already done: {len(completed)}, Pending: {len(pending)}")

    # Pre-fetch PRB evidence (cache to avoid re-querying)
    unique_prbs = set(inc["predicted_problem_id"] for inc in pending if inc["predicted_problem_id"])
    logger.info(f"Pre-fetching evidence for {len(unique_prbs)} unique PRBs...")
    prb_cache = {}
    for prb in unique_prbs:
        prb_cache[prb] = get_prb_evidence(cur, prb)

    # Process each incident
    results = []
    total_tokens = 0
    start_time = time.time()

    # Load existing results if resuming
    results_file = ARTIFACTS_DIR / "validation_results.json"
    if args.resume and results_file.exists():
        with open(results_file) as f:
            results = json.load(f)

    for idx, inc in enumerate(pending):
        inc_num = inc["incident_number"]
        pred_prb = inc["predicted_problem_id"]

        if not pred_prb or pred_prb not in prb_cache:
            continue

        prb_ev = prb_cache[pred_prb]
        prompt = build_prompt(inc, prb_ev)

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=400,
                temperature=1.0,  # GPT-5.4 requires temperature >= 1
            )

            raw_response = response.choices[0].message.content
            parsed = parse_response(raw_response)
            tokens = response.usage.total_tokens
            total_tokens += tokens

            # Build artifact record
            artifact = {
                "incident_number": inc_num,
                "wave": inc["wave"],
                "confidence_score": inc["confidence_score"],
                "predicted_problem_id": pred_prb,
                "incident_data": {
                    "short_description": inc["short_description"],
                    "description": (inc.get("description") or "")[:500],
                    "cmdb_ci": inc.get("cmdb_ci"),
                    "category": inc.get("category"),
                    "subcategory": inc.get("subcategory"),
                    "assignment_group": inc.get("assignment_group"),
                    "priority": inc.get("priority"),
                    "close_notes": (str(inc.get("close_notes") or ""))[:500],
                    "u_error_category": inc.get("u_error_category"),
                    "u_correction_type": inc.get("u_correction_type"),
                },
                "prb_data": {
                    "problem_id": pred_prb,
                    "total_incidents": prb_ev["total_incidents"],
                    "systems": prb_ev["systems"][:5],
                    "categories": prb_ev["categories"][:3],
                    "sample_count": len(prb_ev["sample_incidents"]),
                },
                "llm_request": {
                    "model": MODEL,
                    "prompt_length": len(prompt),
                    "prompt": prompt,
                },
                "llm_response": {
                    "raw": raw_response,
                    "parsed": parsed,
                    "tokens_used": tokens,
                },
                "rating": parsed.get("rating", 0),
                "incident_pattern": parsed.get("incident_pattern", ""),
                "problem_pattern": parsed.get("problem_pattern", ""),
                "explanation": parsed.get("explanation", ""),
                "validated_at": datetime.now().isoformat(),
            }

            results.append(artifact)
            completed.add(inc_num)

            # Progress
            rating = parsed.get("rating", "?")
            elapsed = time.time() - start_time
            rate = (idx + 1) / elapsed * 60 if elapsed > 0 else 0
            logger.info(
                f"  {idx+1}/{len(pending)} {inc_num} [{inc['wave']}] → {pred_prb} "
                f"RATING={rating}/5 tokens={tokens} ({rate:.0f}/min)"
            )

            # Save checkpoint every 25 incidents
            if (idx + 1) % 25 == 0:
                with open(checkpoint_file, "w") as f:
                    json.dump({"completed": list(completed), "last_saved": datetime.now().isoformat()}, f)
                with open(results_file, "w") as f:
                    json.dump(results, f, indent=2)
                logger.info(f"  ── Checkpoint saved: {len(completed)} done, {total_tokens:,} tokens used ──")

        except Exception as e:
            logger.error(f"  ERROR {inc_num}: {e}")
            # Save error artifact
            results.append({
                "incident_number": inc_num,
                "wave": inc["wave"],
                "predicted_problem_id": pred_prb,
                "rating": -1,
                "error": str(e),
                "validated_at": datetime.now().isoformat(),
            })
            completed.add(inc_num)
            time.sleep(2)  # back off on error

    # Final save
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
    with open(checkpoint_file, "w") as f:
        json.dump({"completed": list(completed), "last_saved": datetime.now().isoformat()}, f)

    # Summary
    ratings = defaultdict(int)
    for r in results:
        rt = r.get("rating", -1)
        ratings[rt] += 1

    elapsed = time.time() - start_time

    print()
    print("=" * 80)
    print(f"LLM VALIDATION COMPLETE — {MODEL}")
    print("=" * 80)
    print(f"  Incidents validated: {len(results)}")
    print(f"  Total tokens:       {total_tokens:,}")
    print(f"  Time elapsed:       {elapsed/60:.1f} minutes")
    print(f"  Rate:               {len(pending)/elapsed*60:.0f} incidents/min" if elapsed > 0 else "")
    print()
    print("  Rating Distribution:")
    for r in sorted(ratings.keys(), reverse=True):
        label = {5: "Identical", 4: "Strongly related", 3: "Related", 2: "Weakly related", 1: "Unrelated", 0: "Parse error", -1: "API error"}.get(r, "Unknown")
        print(f"    {r}/5 ({label}): {ratings[r]} ({ratings[r]*100//len(results)}%)")

    valid = ratings.get(5, 0) + ratings.get(4, 0)
    related = ratings.get(3, 0)
    weak = ratings.get(2, 0)
    unrelated = ratings.get(1, 0)
    total = len(results)

    print()
    print(f"  Summary:")
    print(f"    Valid (4-5):     {valid}/{total} = {valid*100//total}%")
    print(f"    Related (3):     {related}/{total} = {related*100//total}%")
    print(f"    Useful (3-5):    {valid+related}/{total} = {(valid+related)*100//total}%")
    print(f"    Weak (2):        {weak}/{total} = {weak*100//total}%")
    print(f"    Unrelated (1):   {unrelated}/{total} = {unrelated*100//total}%")

    # Save summary
    summary = {
        "model": MODEL,
        "total_validated": len(results),
        "total_tokens": total_tokens,
        "elapsed_minutes": round(elapsed / 60, 1),
        "rating_distribution": dict(ratings),
        "valid_4_5": valid,
        "related_3": related,
        "useful_3_5": valid + related,
        "weak_2": weak,
        "unrelated_1": unrelated,
        "timestamp": datetime.now().isoformat(),
    }
    with open(ARTIFACTS_DIR / "validation_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n  Artifacts saved to: {ARTIFACTS_DIR}")
    print(f"    validation_results.json  — full artifacts (every request + response)")
    print(f"    validation_summary.json  — aggregate summary")
    print(f"    checkpoint.json          — resume checkpoint")

    conn.close()


if __name__ == "__main__":
    main()
