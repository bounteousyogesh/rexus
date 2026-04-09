import os
import re
from datetime import datetime
from typing import Any
from fastapi import APIRouter, Query, HTTPException

from backend.api.database import get_pool
from backend.api.utils.llm_provider import chat_complete, get_chat_model

router = APIRouter(tags=["playbooks"])


def extract_ids(text: str) -> dict:
    """Extract order IDs, incident refs, problem IDs, JIRA tickets from text."""
    orders = list(set(re.findall(r'\b(5\d{9})\b', text)))
    problems = list(set(re.findall(r'\b(PRB\d{7})\b', text, re.IGNORECASE)))
    incidents = list(set(re.findall(r'\b(INC\d{7})\b', text, re.IGNORECASE)))
    jira = list(set(re.findall(r'\b(OPOS-\d+)\b', text, re.IGNORECASE)))
    idocs = list(set(re.findall(r'\b(?:IDoc|idoc)\s*(\d{10,16})\b', text)))
    sites = list(set(re.findall(r'\bsite[:\s]+(\w{3}\s*\d{2})\b', text, re.IGNORECASE)))
    netstation = list(set(re.findall(r'\b(NS\d{2})\b', text)))
    return {
        "order_ids": orders,
        "problem_ids": problems,
        "incident_refs": incidents,
        "jira_tickets": jira,
        "idoc_numbers": idocs,
        "sites": sites,
        "netstations": netstation,
    }


@router.get("/playbooks")
async def list_playbooks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
):
    pool = await get_pool()
    offset = (page - 1) * page_size
    conditions = []
    params = []
    idx = 1

    if status:
        conditions.append(f"p.status = ${idx}")
        params.append(status)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with pool.acquire() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM rexus_playbooks p {where}", *params
        )
        rows = await conn.fetch(
            f"""SELECT p.id, p.title, p.cluster_id, p.source_incident_count,
                       p.grounding_score, p.status, p.version, p.created_at,
                       c.cluster_name, c.incident_count as cluster_size
                FROM rexus_playbooks p
                LEFT JOIN rexus_clusters c ON c.id = p.cluster_id
                {where}
                ORDER BY p.source_incident_count DESC NULLS LAST
                LIMIT ${idx} OFFSET ${idx + 1}""",
            *params, page_size, offset,
        )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "items": [dict(r) for r in rows],
    }


@router.get("/playbooks/{playbook_id}")
async def get_playbook(playbook_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT p.*, c.cluster_name, c.incident_count as cluster_size
               FROM rexus_playbooks p
               LEFT JOIN rexus_clusters c ON c.id = p.cluster_id
               WHERE p.id = $1""",
            playbook_id,
        )
        if not row:
            raise HTTPException(404, "Playbook not found")
    return dict(row)


# ═══════════════════════════════════════════════════════════════════
# Smart problem ID ranking
# ═══════════════════════════════════════════════════════════════════

async def _rank_problems(pool: Any, cluster_id: int, incidents: list[Any]) -> list[dict]:
    """
    Rank problem IDs by composite relevance score:
      1. Relevance  (40%) — avg similarity to centroid of incidents linked to this problem
      2. Recency    (30%) — how recent the latest incident is (days ago → 0-1 scale)
      3. Frequency  (20%) — direct-link count normalized
      4. Direct ratio (10%) — % of references that are direct (problem_id field) vs mentioned in notes

    Tiebreaker: if two problems score within 0.02, pick the one with the more recent incident.
    """
    # Step 1: Get all problems from the problem_id field (direct links)
    async with pool.acquire() as conn:
        direct_problems = await conn.fetch(
            """SELECT ri.problem_id,
                      COUNT(*) as direct_count,
                      MAX(ri.opened_at) as latest_date,
                      AVG(rcm.similarity_to_centroid) as avg_sim,
                      MAX(rcm.similarity_to_centroid) as max_sim
               FROM rexus_incidents ri
               JOIN rexus_cluster_mapping rcm ON ri.id = rcm.incident_id
               WHERE rcm.cluster_id = $1
                 AND ri.problem_id IS NOT NULL AND ri.problem_id != ''
               GROUP BY ri.problem_id
               ORDER BY COUNT(*) DESC""",
            cluster_id,
        )

    # Step 2: Also find problems mentioned in close_notes but not in problem_id field
    notes_mentions: dict[str, dict] = {}
    for inc in incidents:
        cn = inc["close_notes"] or ""
        sd = inc["short_description"] or ""
        combined = f"{cn} {sd}"
        for pid in re.findall(r'\b(PRB\d{7})\b', combined, re.IGNORECASE):
            pid_upper = pid.upper()
            if pid_upper not in notes_mentions:
                notes_mentions[pid_upper] = {"count": 0, "latest": None, "sims": []}
            notes_mentions[pid_upper]["count"] += 1
            if inc["opened_at"]:
                if notes_mentions[pid_upper]["latest"] is None or inc["opened_at"] > notes_mentions[pid_upper]["latest"]:
                    notes_mentions[pid_upper]["latest"] = inc["opened_at"]
            notes_mentions[pid_upper]["sims"].append(inc["similarity_to_centroid"] or 0)

    # Step 3: Merge into unified problem list
    now = datetime.now()
    problem_data: dict[str, dict] = {}

    # Direct links (strongest signal)
    for row in direct_problems:
        pid = row["problem_id"].upper()
        problem_data[pid] = {
            "id": pid,
            "direct_count": row["direct_count"],
            "notes_count": 0,
            "latest_date": row["latest_date"],
            "avg_sim": float(row["avg_sim"] or 0),
            "max_sim": float(row["max_sim"] or 0),
        }

    # Add notes mentions
    for pid, info in notes_mentions.items():
        if pid in problem_data:
            problem_data[pid]["notes_count"] = info["count"]
            # Update latest date if notes mention is more recent
            if info["latest"] and (problem_data[pid]["latest_date"] is None or info["latest"] > problem_data[pid]["latest_date"]):
                problem_data[pid]["latest_date"] = info["latest"]
        else:
            avg_s = sum(info["sims"]) / len(info["sims"]) if info["sims"] else 0
            problem_data[pid] = {
                "id": pid,
                "direct_count": 0,
                "notes_count": info["count"],
                "latest_date": info["latest"],
                "avg_sim": avg_s,
                "max_sim": max(info["sims"]) if info["sims"] else 0,
            }

    if not problem_data:
        return []

    # Step 4: Compute composite scores
    max_direct = max((p["direct_count"] for p in problem_data.values()), default=1) or 1
    max_total = max((p["direct_count"] + p["notes_count"] for p in problem_data.values()), default=1) or 1

    scored = []
    for pid, p in problem_data.items():
        total_count = p["direct_count"] + p["notes_count"]

        # Relevance: avg similarity to centroid (0.0 - 1.0)
        relevance = p["avg_sim"]

        # Recency: 1.0 = today, decays over ~12 months
        if p["latest_date"]:
            days_ago = (now - p["latest_date"]).days
            recency = max(0.0, 1.0 - (days_ago / 365.0))
        else:
            recency = 0.0

        # Frequency: normalized by max in cluster
        frequency = total_count / max_total

        # Direct link ratio: problems directly in the problem_id field are stronger signals
        direct_ratio = p["direct_count"] / total_count if total_count > 0 else 0

        # Composite score
        score = (0.40 * relevance) + (0.30 * recency) + (0.20 * frequency) + (0.10 * direct_ratio)

        scored.append({
            "id": pid,
            "score": round(score, 4),
            "direct_count": p["direct_count"],
            "notes_count": p["notes_count"],
            "total_count": total_count,
            "avg_similarity": round(p["avg_sim"], 4),
            "max_similarity": round(p["max_sim"], 4),
            "latest_date": p["latest_date"].isoformat() if p["latest_date"] else None,
            "recency_score": round(recency, 3),
            "relevance_score": round(relevance, 4),
        })

    # Step 5: Sort by score, tiebreak by recency
    scored.sort(key=lambda x: (-x["score"], -(x["recency_score"])))

    # Step 6: Tiebreaker — if top two are within 0.02, prefer the more recent one
    if len(scored) >= 2:
        if abs(scored[0]["score"] - scored[1]["score"]) < 0.02:
            # Very close scores — prefer the one with more recent incident
            if scored[1]["recency_score"] > scored[0]["recency_score"]:
                scored[0], scored[1] = scored[1], scored[0]

    return scored


# ═══════════════════════════════════════════════════════════════════
# Grounded playbook generation — no hallucination
# ═══════════════════════════════════════════════════════════════════

@router.post("/playbooks/generate/{cluster_id}")
async def generate_playbook(cluster_id: int):
    """
    Generate a grounded playbook from real incident data.
    - Analyzes incidents newest → oldest
    - Extracts order IDs, problem IDs, JIRA tickets per incident
    - Only includes what the team actually did / requested
    - Zero hallucination — every claim cites an incident number

    ENH-008: This endpoint is idempotent (upsert by cluster_id).  Calling it
    multiple times for the same cluster will regenerate and overwrite the
    existing playbook, incrementing the version counter.  This is equivalent
    to PUT semantics, so clients should treat it as a safe retry operation.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Get cluster info
        cluster = await conn.fetchrow(
            """SELECT id, cluster_name, incident_count, dominant_category,
                      avg_resolution_hours, problem_ids
               FROM rexus_clusters WHERE id = $1""",
            cluster_id,
        )
        if not cluster:
            raise HTTPException(404, "Cluster not found")

        # Pull ALL incidents with close_notes, newest first
        incidents = await conn.fetch(
            """SELECT ri.incident_number, ri.short_description, ri.description,
                      ri.close_notes, ri.cmdb_ci, ri.assignment_group,
                      ri.category, ri.subcategory, ri.priority, ri.problem_id,
                      ri.u_jira_number, ri.u_order_number, ri.opened_at, ri.closed_at,
                      ri.business_duration, ri.close_code, ri.work_notes as full_work_notes,
                      rcm.similarity_to_centroid
               FROM rexus_incidents ri
               JOIN rexus_cluster_mapping rcm ON ri.id = rcm.incident_id
               WHERE rcm.cluster_id = $1
               ORDER BY ri.opened_at DESC""",
            cluster_id,
        )

    if not incidents:
        raise HTTPException(400, "No incidents in this cluster")

    # ── Build per-incident evidence ────────────────────────────────
    evidence_lines = []
    all_ids: dict[str, list] = {
        "order_ids": [], "problem_ids": [], "jira_tickets": [],
        "incident_refs": [], "sites": [], "netstations": [],
    }
    incidents_with_notes = 0
    groups = {}
    resolution_actions = []

    for inc in incidents:
        combined_text = f"{inc['short_description'] or ''} {inc['close_notes'] or ''} {inc['description'] or ''}"
        ids = extract_ids(combined_text)

        # Accumulate all IDs
        for key in all_ids:
            all_ids[key].extend(ids.get(key, []))

        # Track assignment groups
        grp = inc["assignment_group"] or "Unknown"
        groups[grp] = groups.get(grp, 0) + 1

        if inc["close_notes"] and len(inc["close_notes"].strip()) > 5:
            incidents_with_notes += 1
            # Build evidence block for this incident
            order_str = ", ".join(ids["order_ids"]) if ids["order_ids"] else "N/A"
            problem_str = ", ".join(ids["problem_ids"]) if ids["problem_ids"] else ""
            jira_str = ", ".join(ids["jira_tickets"]) if ids["jira_tickets"] else ""

            block = (
                f"--- {inc['incident_number']} | {inc['opened_at']} | "
                f"Order(s): {order_str}"
            )
            if problem_str:
                block += f" | Problem: {problem_str}"
            if jira_str:
                block += f" | JIRA: {jira_str}"
            block += f"\nTitle: {inc['short_description']}"
            block += f"\nClose Notes: {inc['close_notes'].strip()}"
            evidence_lines.append(block)

    # Deduplicate IDs
    for key in all_ids:
        all_ids[key] = list(set(all_ids[key]))

    # ── Smart problem ID ranking ──────────────────────────────────
    # Score each problem by: relevance (centroid similarity), recency, frequency, direct-link strength
    top_problems = await _rank_problems(pool, cluster_id, incidents)
    all_ids["top_problems"] = top_problems

    # Take top 30 incidents for the LLM (newest first, already sorted)
    evidence_text = "\n\n".join(evidence_lines[:30])
    top_groups = sorted(groups.items(), key=lambda x: -x[1])[:5]
    groups_str = ", ".join(f"{g} ({c})" for g, c in top_groups)

    # Top problem suggestions (from smart ranking)
    if top_problems:
        suggested_parts = []
        for i, p in enumerate(top_problems[:3]):
            label = "RECOMMENDED" if i == 0 else ("Secondary" if i == 1 else "Alternative")
            suggested_parts.append(
                f"{label}: {p['id']} (score={p['score']}, {p['total_count']} incidents, "
                f"similarity={p['avg_similarity']}, latest={p.get('latest_date', 'N/A')})"
            )
        suggested_str = "\n".join(suggested_parts)
    else:
        suggested_str = "None found"

    # ── LLM synthesis with strict grounding ────────────────────────

    org_name = os.getenv("REXUS_ORG_NAME", "Discount Tire")
    system_prompt = f"""You are a technical documentation writer for {org_name} support engineers.

ABSOLUTE RULES:
1. ONLY write what appears in the evidence below. Do NOT invent any steps, tools, or procedures.
2. Every resolution step MUST cite the incident number(s) it came from in brackets, e.g. [INC2085173].
3. If the evidence is thin or unclear, say "Insufficient data" — do NOT guess or fill gaps.
4. Use the exact technical terms from the close notes (e.g., "Windows+D", "force closed POS", "WE19", "poslog").
5. For each incident referenced, include its order ID(s) if present.
6. Distinguish between "What the team DID" (actions taken) and "What the team REQUESTED" (escalations, problem tickets raised).
7. Organize incidents chronologically — latest first."""

    user_prompt = f"""Create a grounded playbook for the following incident cluster.

CLUSTER: {cluster['cluster_name']}
TOTAL INCIDENTS: {cluster['incident_count']}
INCIDENTS WITH CLOSE NOTES: {incidents_with_notes}
CATEGORY: {cluster['dominant_category'] or 'N/A'}
ASSIGNMENT GROUPS: {groups_str}
ALL ORDER IDs FOUND: {', '.join(all_ids['order_ids'][:20]) or 'None'}
ALL PROBLEM IDs: {', '.join(all_ids['problem_ids'][:10]) or 'None'}
ALL JIRA TICKETS: {', '.join(all_ids['jira_tickets'][:10]) or 'None'}
TOP SUGGESTED PROBLEMS: {suggested_str}

═══ INCIDENT EVIDENCE (newest first) ═══

{evidence_text}

═══ END OF EVIDENCE ═══

Generate a Markdown playbook with EXACTLY these sections IN THIS ORDER:

# Playbook: {cluster['cluster_name']}

## Overview
- What this issue pattern is (1-2 sentences, from evidence only)
- Total incidents: X | With resolution notes: Y
- Affected Systems: (list)

## Suggested Problem Tags
Use the TOP SUGGESTED PROBLEMS data below. The ranking already accounts for relevance (how well the problem's incidents match this cluster's pattern), recency (most recent usage), and frequency.
- **Recommended:** First problem from TOP SUGGESTED PROBLEMS — include the score, count, and a 1-line reason from evidence why it's the best match
- **Secondary:** Second problem — include score, count, and brief reason
- **Other:** remaining problem IDs, all on one comma-separated line

## What the Team DID (Resolution Actions)
THIS IS THE MOST IMPORTANT SECTION. Group by technique, most common first.
Each action must cite [INC#] and include Order ID if available:
1. **Action name** (X occurrences) — [INC#, INC#] — Order(s): X
2. **Next action** (X occurrences) — [INC#] — Order(s): X

## What the Team REQUESTED (Escalations & Tickets)
Problem tickets raised, JIRA tickets created, escalation requests — cite which incident triggered each.

## Resolution Pattern Summary
Numbered list, most common first, with exact counts.

## Confidence
- High/Medium/Low + reason

## Incident Registry
Table of ALL incidents analyzed (this section goes LAST):
| Incident # | Date | Order ID(s) | Problem ID | Summary |
(Include every incident from the evidence, newest first)

REMEMBER: Zero hallucination. Every fact must trace to an incident number above."""

    response = await chat_complete(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=4000,
        temperature=0.1,
    )

    content = response.choices[0].message.content or ""

    # Grounding score based on evidence depth
    if incidents_with_notes >= 15:
        grounding = 0.95
    elif incidents_with_notes >= 8:
        grounding = 0.85
    elif incidents_with_notes >= 3:
        grounding = 0.7
    else:
        grounding = 0.4

    source_incidents = [inc["incident_number"] for inc in incidents[:30]]

    # Save to DB (upsert by cluster_id)
    async with pool.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT id FROM rexus_playbooks WHERE cluster_id = $1", cluster_id
        )
        if existing:
            await conn.execute(
                """UPDATE rexus_playbooks
                   SET content = $1, source_incident_count = $2,
                       source_incidents = $3, grounding_score = $4,
                       version = version + 1, updated_at = CURRENT_TIMESTAMP
                   WHERE cluster_id = $5""",
                content, incidents_with_notes, source_incidents, grounding, cluster_id,
            )
            playbook_id = existing
        else:
            playbook_id = await conn.fetchval(
                """INSERT INTO rexus_playbooks
                   (cluster_id, title, content, source_incident_count,
                    source_incidents, grounding_score, status)
                   VALUES ($1, $2, $3, $4, $5, $6, 'draft')
                   RETURNING id""",
                cluster_id,
                f"Playbook: {cluster['cluster_name']}",
                content,
                incidents_with_notes,
                source_incidents,
                grounding,
            )

    return {
        "playbook_id": playbook_id,
        "cluster_id": cluster_id,
        "cluster_name": cluster["cluster_name"],
        "content": content,
        "grounding_score": grounding,
        "source_incident_count": incidents_with_notes,
        "total_incidents": cluster["incident_count"],
        "extracted_ids": all_ids,
    }
