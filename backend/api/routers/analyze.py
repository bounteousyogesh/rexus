"""
REX-US Ticket Analysis — The crown jewel.

Key design: Playbooks are generated from the SIMILAR INCIDENTS found by
vector search — not from the entire cluster. This ensures the playbook
is specific to THIS incident's pattern, not a broad cluster-level summary.

Supports:
  POST /analyze       - Analyze from JSON (ServiceNow ticket data)
  POST /analyze/text  - Analyze from plain text description
  POST /parse-pdf     - Upload PDF → extract JSON
"""

import base64
import os
import re
import json
import asyncio
import logging
import tempfile
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.api.models.analyze import (
    AnalyzeRequest,
    AnalyzeResponse,
    AnalyzeTextRequest,
    OrderAnalyzeRequest,
    OrderAnalyzeResponse,
)

# ── Configurable constants ────────────────────────────────────────
ORG_NAME = os.getenv("REXUS_ORG_NAME", "Discount Tire")

# Problem scoring weights (sum to 1.0)
_W_SIMILARITY = float(os.getenv("SCORE_W_SIMILARITY", "0.35"))
_W_FREQUENCY = float(os.getenv("SCORE_W_FREQUENCY", "0.30"))
_W_RECENCY = float(os.getenv("SCORE_W_RECENCY", "0.10"))
_W_CMDB = float(os.getenv("SCORE_W_CMDB", "0.05"))
_W_STATE = float(os.getenv("SCORE_W_STATE", "0.20"))

# Grounding score thresholds
_GROUNDING_HIGH = 8       # incidents with notes >= this → 0.95
_GROUNDING_MED = 4        # >= this → 0.85
_GROUNDING_LOW = 2        # >= this → 0.70
_GROUNDING_FLOOR = 0.40   # below LOW → this score

# Hybrid search bonus
_HYBRID_BONUS_MULTIPLIER = 0.05
_HYBRID_VEC_MIN = 0.40
_HYBRID_KW_MIN = 0.30

# Progressive learning minimum confidence
_PROGRESSIVE_MIN_CONFIDENCE = float(os.getenv("PROGRESSIVE_MIN_CONFIDENCE", "0.0"))

# KB playbook summary: max chars from extracted PDF text sent to the LLM
_MAX_KB_TEXT_FOR_SUMMARY = 14_000

from backend.api.database import get_pool
from backend.api.utils.llm_provider import embed_text, chat_complete, get_chat_model, get_embed_model
from backend.api.utils.pdf_parser import PDFParser, extract_plain_text_from_pdf_bytes
from backend.api.utils.token_tracker import track_usage
from backend.api.utils.text_cleaning import clean_for_embedding as _shared_clean_for_embedding
from backend.api.utils.kb_articles import (
    apply_kb_playbook_to_focused,
    enrich_kb_articles_from_servicenow,
    pick_kb_for_analysis,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analyze"])
limiter = Limiter(key_func=get_remote_address)

# ARCH-003: CMDB family mapping loaded from config file (not hardcoded)
_CMDB_FAMILIES_PATH = Path(__file__).parent.parent.parent / "config" / "cmdb_families.json"
if _CMDB_FAMILIES_PATH.exists():
    with open(_CMDB_FAMILIES_PATH) as _f:
        CMDB_FAMILIES: dict[str, list[str]] = json.load(_f)
else:
    logger.warning(f"CMDB families config not found at {_CMDB_FAMILIES_PATH}, using empty mapping")
    CMDB_FAMILIES: dict[str, list[str]] = {}

def get_cmdb_family(cmdb_ci: str) -> str:
    """Map a CMDB CI string to its system family name."""
    if not cmdb_ci:
        return ""
    lower = cmdb_ci.lower().strip()
    for family, members in CMDB_FAMILIES.items():
        if lower in members:
            return family
    return lower  # standalone — use as its own family

def _json_serial(obj: object) -> str:
    """Serialize datetime/date objects for JSON encoding."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)

def clean_for_embedding(text: str) -> str:
    """Normalize text for embedding — QUAL-002: delegates to shared utility."""
    return _shared_clean_for_embedding(text, strict=False)

def extract_ids_from_text(text: str) -> dict:
    """Extract order IDs, problem IDs, JIRA tickets from text."""
    return {
        "order_ids": list(set(re.findall(r'\b(5\d{9})\b', text))),
        "problem_ids": list(set(re.findall(r'\b(PRB\d{7})\b', text, re.IGNORECASE))),
        "jira_tickets": list(set(re.findall(r'\b(OPOS-\d+)\b', text, re.IGNORECASE))),
        "incident_refs": list(set(re.findall(r'\b(INC\d{7})\b', text, re.IGNORECASE))),
    }

def build_embedding_text(ticket_json: dict) -> tuple[str, str]:
    """Extract key fields from ServiceNow JSON and build embedding text.
    v3: Now includes incident_details (IDoc Text, Initial Finding, Error Category).
    Returns (cleaned_issue, embedding_text)."""
    pdf_fields = ticket_json.get("pdf_fields", {})
    incident = ticket_json.get("incident_section", {})
    resolution = ticket_json.get("resolution_information_section", {})
    details = ticket_json.get("incident_details", {})
    notes = ticket_json.get("notes_section", {})

    short_desc = pdf_fields.get("Short description", "") or ticket_json.get("short_description", "")
    description = pdf_fields.get("Description", "") or ticket_json.get("description", "")
    category = incident.get("Category", "") or ticket_json.get("category", "")
    subcategory = incident.get("Subcategory", "") or ticket_json.get("subcategory", "")
    cmdb_ci = incident.get("Configuration item", "") or ticket_json.get("cmdb_ci", "")
    close_notes = resolution.get("Close notes", "") or resolution.get("Resolution notes", "") or ticket_json.get("close_notes", "")

    cleaned_issue = clean_for_embedding(short_desc)

    parts = [
        f"Issue: {cleaned_issue}",
        f"System: {cmdb_ci} | {category} > {subcategory}" if cmdb_ci or category else "",
        f"Description: {clean_for_embedding(description)}" if description and len(description) > 10 else "",
    ]

    # v3: Include IDoc Text, Initial Finding, Error Category from PDF extraction
    idoc_text = details.get("IDoc Text", "")
    initial_finding = details.get("Initial Finding", "")
    error_category = details.get("Error Category", "")
    pos_event = details.get("POS Event", "")

    detail_parts = []
    if idoc_text:
        detail_parts.append(f"IDoc: {idoc_text}")
    if initial_finding:
        detail_parts.append(f"Finding: {initial_finding}")
    if error_category:
        detail_parts.append(f"Error: {error_category}")
    if pos_event and len(pos_event) > 2:
        detail_parts.append(f"POS Event: {pos_event}")

    if detail_parts:
        parts.append(f"Details: {' | '.join(detail_parts)}")

    # Also extract from additional comments if details not already found
    comments = notes.get("Additional comments", "")
    if comments and not idoc_text:
        m = re.search(r'IDoc\s*Text\s*:\s*(.+?)(?:\n|$)', comments, re.I)
        if m:
            parts.append(f"Details: IDoc: {m.group(1).strip()}")
        m = re.search(r'Initial\s*(?:analysis\s*)?[Ff]inding[s]?\s*:\s*(.+?)(?:\n|$)', comments, re.I)
        if m and len(m.group(1).strip()) > 3:
            parts.append(f"Finding: {m.group(1).strip()}")

    if close_notes and len(close_notes) > 10:
        parts.append(f"Resolution: {clean_for_embedding(close_notes)}")

    embedding_text = "\n".join(p for p in parts if p)

    return cleaned_issue, embedding_text

# ═══════════════════════════════════════════════════════════════════
# Focused playbook generation — from similar incidents, not clusters
# ═══════════════════════════════════════════════════════════════════

# ── SEC-011: Sanitize text before LLM prompt interpolation ────────

_PROMPT_INJECT_RE = re.compile(
    r'(ignore\s+(previous|all)\s+instructions?|system\s*prompt|you\s+are\s+now|disregard)',
    re.IGNORECASE,
)

_MAX_PROMPT_FIELD_LEN = 500

def _sanitize_for_prompt(text: str, max_len: int = _MAX_PROMPT_FIELD_LEN) -> str:
    """
    Sanitize user-supplied text before interpolating into LLM prompts.
    Truncates to max_len and strips common prompt-injection patterns.
    """
    if not text:
        return ""
    text = str(text)[:max_len]
    text = _PROMPT_INJECT_RE.sub("[REDACTED]", text)
    return text

# ── CQ-005: Helper functions extracted from _generate_focused_playbook ──

def _build_evidence_lines(incident_details: list[dict]) -> tuple[list[str], dict, list[str], list[str], int]:
    """
    Build per-incident evidence blocks and accumulate IDs.
    Returns (evidence_lines, all_problem_ids, all_order_ids, all_jira, incidents_with_notes).
    """
    evidence_lines: list[str] = []
    all_problem_ids: dict[str, dict] = {}
    all_order_ids: list[str] = []
    all_jira: list[str] = []
    incidents_with_notes = 0

    for inc in incident_details:
        combined = f"{inc.get('short_description', '')} {inc.get('close_notes', '')} {inc.get('description', '')}"
        ids = extract_ids_from_text(combined)
        all_order_ids.extend(ids["order_ids"])
        all_jira.extend(ids["jira_tickets"])

        sim = inc.get("similarity_score", 0)
        pid = inc.get("problem_id", "")
        inc_cmdb = inc.get("cmdb_ci", "") or ""
        if pid:
            if pid not in all_problem_ids:
                all_problem_ids[pid] = {"count": 0, "total_sim": 0.0, "cmdb_cis": []}
            all_problem_ids[pid]["count"] += 1
            all_problem_ids[pid]["total_sim"] += sim
            if inc_cmdb:
                all_problem_ids[pid]["cmdb_cis"].append(inc_cmdb)

        if inc.get("close_notes") and len(inc["close_notes"].strip()) > 5:
            incidents_with_notes += 1
            order_str = ", ".join(ids["order_ids"]) if ids["order_ids"] else "N/A"
            problem_str = pid or "N/A"
            block = (
                f"--- {inc['incident_number']} | {inc.get('opened_at', 'N/A')} | "
                f"Similarity: {inc.get('similarity_score', 0):.1%} | "
                f"Order(s): {order_str} | Problem: {problem_str}"
            )
            block += f"\nTitle: {inc['short_description']}"
            block += f"\nSystem: {inc.get('cmdb_ci', 'N/A')} | Group: {inc.get('assignment_group', 'N/A')}"
            block += f"\nClose Notes: {inc['close_notes'].strip()}"
            if inc.get("description"):
                block += f"\nDescription excerpt: {inc['description'][:200]}"
            evidence_lines.append(block)

    return evidence_lines, all_problem_ids, all_order_ids, all_jira, incidents_with_notes

def _score_problems(
    all_problem_ids: dict,
    problem_states: dict,
    incoming_cmdb: str,
) -> list[dict]:
    """
    Score each problem group by CMDB family match, similarity, frequency, and open state.
    Returns sorted list of scored problem dicts.
    """
    incoming_family = get_cmdb_family(incoming_cmdb)
    total_results = sum(p["count"] for p in all_problem_ids.values()) or 1
    scored_problems = []

    for pid, info in all_problem_ids.items():
        cmdb_list = info.get("cmdb_cis", [])
        dominant_cmdb = max(set(cmdb_list), key=cmdb_list.count) if cmdb_list else ""
        problem_family = get_cmdb_family(dominant_cmdb)

        cmdb_match = 0.0
        if incoming_family and problem_family:
            if incoming_family == problem_family:
                cmdb_match = 1.0
            elif incoming_cmdb and dominant_cmdb and incoming_cmdb.lower() == dominant_cmdb.lower():
                cmdb_match = 1.0

        avg_sim = info["total_sim"] / info["count"] if info["count"] > 0 else 0
        result_ratio = info["count"] / total_results
        state = problem_states.get(pid, "Unknown")
        is_open = state in ("Open", "New")

        score = (
            (0.35 * cmdb_match)
            + (0.30 * avg_sim)
            + (0.10 * result_ratio)
            + (0.05 * (1.0 if info["count"] >= 3 else 0.5))
            + (0.20 * (1.0 if is_open else 0.0))
        )
        scored_problems.append({
            "id": pid,
            "count": info["count"],
            "avg_sim": round(avg_sim, 4),
            "cmdb_match": round(cmdb_match, 2),
            "dominant_cmdb": dominant_cmdb,
            "cmdb_family": problem_family,
            "score": round(score, 4),
            "state": state,
            "is_open": is_open,
        })

    scored_problems.sort(key=lambda x: (-x["is_open"], -x["score"]))
    return scored_problems

def _build_playbook_prompts(
    cleaned_issue: str,
    cluster_name: str,
    cluster_count: int,
    incidents_with_notes: int,
    evidence_text: str,
    top_problem: Optional[dict],
) -> tuple[str, str, str]:
    """
    Build (playbook_prompt, notes_prompt, system_prompt) for LLM generation.
    User-supplied fields are sanitized before interpolation (SEC-011).
    """
    safe_issue = _sanitize_for_prompt(cleaned_issue)
    safe_cluster = _sanitize_for_prompt(cluster_name, max_len=200)

    tag_line = (
        f"Recommended: {top_problem['id']} ({top_problem['count']} similar incidents, "
        f"score={top_problem['score']})"
        if top_problem
        else "No existing problem matches — consider creating new."
    )

    playbook_prompt = f"""You are writing a CONCISE PLAYBOOK for a {ORG_NAME} support engineer who just received this incident.

INCIDENT: {safe_issue}
PATTERN: {safe_cluster} ({cluster_count} total incidents in this pattern)
BASED ON: {incidents_with_notes} similar resolved incidents

EVIDENCE FROM SIMILAR INCIDENTS:
{evidence_text[:3000]}

Write a SHORT, actionable playbook (max 400 words). Use this EXACT format:

## Playbook: {safe_cluster}

**Pattern:** 1-2 sentence description of what this issue type is, based on evidence.

**Most Likely Fix:** The #1 resolution that worked (with count). Cite [INC#].

**Step-by-Step:**
1. First step (from evidence)
2. Second step
3. etc.

**If That Doesn't Work:** Alternative approaches from evidence, cite [INC#].

**Escalate To:** Which team/person, cite which incidents triggered escalation.

**Tag Problem:** {tag_line}

RULES: Only use facts from the evidence. Cite [INC#] for every claim. Be brief."""

    notes_prompt = f"""Create detailed resolution notes from these similar incidents.

INCIDENT: {safe_issue}
SIMILAR INCIDENTS: {incidents_with_notes} with resolution data

{evidence_text}

Format as:

## Resolution Notes

### What the Team DID
Group by technique, cite [INC#] + Order ID for each:
1. **Action** (count) — [INC#] — Order: X

### What the Team REQUESTED
Escalations, problem tickets, JIRA tickets — cite source incident.

### Incident Reference
| # | Date | Order | Sim% | Problem | Summary |
(All incidents, sorted by similarity)

RULES: Zero hallucination. Every fact cites an incident number."""

    system_prompt = """You are a technical writer for {ORG_NAME} support engineers.
ABSOLUTE RULES:
1. ONLY write what appears in the evidence. Do NOT invent.
2. Every step MUST cite [INC#].
3. Use exact technical terms (WE19, poslog, IDoc, APCR, finalize).
4. Be concise — engineers scan, not read."""

    return playbook_prompt, notes_prompt, system_prompt

def _compute_grounding_score(evidence_count: int) -> float:
    """Map count of evidence sources (incidents with notes or KB articles with text) to a score."""
    if evidence_count >= _GROUNDING_HIGH:
        return 0.95
    if evidence_count >= _GROUNDING_MED:
        return 0.85
    if evidence_count >= _GROUNDING_LOW:
        return 0.70
    return _GROUNDING_FLOOR


def _llm_error_summary(exc: Exception) -> str:
    """Short user-facing reason when LLM calls fail."""
    message = str(exc)
    if "Zscaler" in message or "PermissionDenied" in type(exc).__name__:
        return "corporate network blocked OpenAI chat API"
    if "CERTIFICATE_VERIFY_FAILED" in message or "APIConnectionError" in type(exc).__name__:
        return "OpenAI connection failed (check OPENAI_SSL_VERIFY or network)"
    return type(exc).__name__


def _build_fallback_playbook(
    cluster_name: str,
    incident_details: list[dict],
    top_problem: dict | None,
    llm_error: str,
) -> tuple[str, str]:
    """Evidence-based playbook when LLM generation is unavailable."""
    similar_with_notes = [
        inc for inc in incident_details
        if inc.get("close_notes") and len(inc["close_notes"].strip()) > 5
    ][:5]

    inc_refs = ", ".join(f"[{inc['incident_number']}]" for inc in similar_with_notes) or "N/A"

    playbook = (
        f"## Playbook: {_sanitize_for_prompt(cluster_name, 120)}\n\n"
        f"**Pattern:** Based on {len(incident_details)} similar incident(s) in the knowledge base.\n\n"
        f"**Most Likely Fix:** Review resolutions from similar incidents: {inc_refs}.\n\n"
        "**Step-by-Step:**\n"
    )
    if similar_with_notes:
        for i, inc in enumerate(similar_with_notes[:3], 1):
            note = inc["close_notes"].strip().split("\n")[0][:200]
            playbook += f"{i}. {note} [{inc['incident_number']}].\n"
    else:
        playbook += "1. Review similar incidents listed below for matching symptoms.\n"

    playbook += (
        "\n**If That Doesn't Work:** Expand review to additional similar incidents "
        "or escalate to the owning support group.\n"
    )
    if top_problem:
        playbook += (
            f"\n**Tag Problem:** Consider linking to {top_problem['id']} "
            f"({top_problem['count']} similar incidents).\n"
        )
    playbook += (
        f"\n_Note: AI playbook generation was unavailable ({llm_error}). "
        "Showing evidence-based summary from similar incidents._\n"
    )

    notes = "\n\n".join(
        f"### {inc['incident_number']} ({inc.get('similarity_score', 0):.0%} match)\n"
        f"{inc['close_notes'].strip()}"
        for inc in similar_with_notes
    )
    return playbook, notes


async def _generate_focused_playbook(
    cleaned_issue: str,
    incident_details: list[dict],
    incoming_cmdb: str,
    cluster_info: dict | None,
    pool=None,
) -> dict:
    """
    Generate a playbook from the SPECIFIC similar incidents found by vector search.
    Not from the whole cluster — only from what's actually relevant to THIS ticket.
    """
    if not incident_details:
        return {"content": "", "grounding_score": 0}

    # CQ-005: Use extracted helpers for evidence building and problem scoring
    evidence_lines, all_problem_ids, all_order_ids, all_jira, incidents_with_notes = (
        _build_evidence_lines(incident_details)
    )

    # ARCH-001 FIX: Batch fetch problem states in a single SELECT
    problem_states: dict[str, str] = {}
    if all_problem_ids:
        try:
            async with pool.acquire() as pconn:
                rows = await pconn.fetch(
                    "SELECT problem_id, state_display FROM rexus_problems WHERE problem_id = ANY($1)",
                    list(all_problem_ids.keys()),
                )
                problem_states = {r["problem_id"]: r["state_display"] for r in rows}
        except Exception as e:
            logger.warning(f"Failed to fetch problem states: {e}")

    # CQ-005: Use extracted helper for problem scoring (uses module-level CMDB_FAMILIES)
    scored_problems = _score_problems(all_problem_ids, problem_states, incoming_cmdb)

    top_problem = scored_problems[0] if scored_problems else None
    secondary_problem = scored_problems[1] if len(scored_problems) > 1 else None
    remaining_problems = [p["id"] for p in scored_problems[2:]]

    evidence_text = "\n\n".join(evidence_lines)
    unique_orders = list(set(all_order_ids))
    unique_jira = list(set(all_jira))

    cluster_name = cluster_info["cluster_name"] if cluster_info else "Unknown Pattern"
    cluster_count = cluster_info.get("incident_count", 0) if cluster_info else 0

    # CQ-005: Use extracted helper to build prompts (SEC-011: sanitizes user data)
    playbook_prompt, notes_prompt, system_prompt = _build_playbook_prompts(
        cleaned_issue, cluster_name, cluster_count,
        incidents_with_notes, evidence_text, top_problem,
    )

    model = get_chat_model()

    playbook_coro = chat_complete(
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": playbook_prompt}],
        max_tokens=1500, temperature=0.1,
    )
    notes_coro = chat_complete(
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": notes_prompt}],
        max_tokens=3000, temperature=0.1,
    )

    playbook_content = ""
    notes_content = ""
    playbook_source = "similar_incidents"
    try:
        playbook_resp, notes_resp = await asyncio.gather(playbook_coro, notes_coro)
        playbook_content = playbook_resp.choices[0].message.content or ""
        notes_content = notes_resp.choices[0].message.content or ""

        if pool:
            pb_usage = playbook_resp.usage
            nt_usage = notes_resp.usage
            await track_usage(pool, "completion", model,
                              pb_usage.prompt_tokens, pb_usage.completion_tokens,
                              endpoint="/analyze-playbook")
            await track_usage(pool, "completion", model,
                              nt_usage.prompt_tokens, nt_usage.completion_tokens,
                              endpoint="/analyze-notes")
    except Exception as exc:
        logger.warning("LLM playbook generation failed, using evidence fallback: %s", exc)
        playbook_source = "evidence_fallback"
        playbook_content, notes_content = _build_fallback_playbook(
            cluster_name, incident_details, top_problem, _llm_error_summary(exc),
        )

    return {
        "playbook": playbook_content,
        "notes": notes_content,
        "grounding_score": _compute_grounding_score(incidents_with_notes),
        "source_incident_count": incidents_with_notes,
        "total_similar": len(incident_details),
        "top_problem": top_problem,
        "secondary_problem": secondary_problem,
        "other_problems": remaining_problems,
        "order_ids": unique_orders[:20],
        "jira_tickets": unique_jira,
        "playbook_source": playbook_source,
    }

def _fetch_kb_pdf_from_servicenow(kb_number: str) -> bytes | None:
    """Sync: load KB PDF from ServiceNow (same client pattern as get_incident_detailed)."""
    from backend.services.servicenow_client import ServiceNowClient

    try:
        sn_client = ServiceNowClient()
    except ValueError:
        return None

    data = sn_client.get_knowledge_article(kb_number)
    if not data:
        return None

    pdf_meta = data.get("pdf")
    if not isinstance(pdf_meta, dict):
        return None
    pdf_b64 = pdf_meta.get("base64")
    if not pdf_b64:
        return None

    try:
        pdf_bytes = base64.b64decode(pdf_b64, validate=True)
        if pdf_bytes.startswith(b"%PDF"):
            return pdf_bytes
    except Exception:
        return None
    return None

async def _load_kb_article_pdf(kb_number: str) -> bytes | None:
    """KB article PDF: ServiceNow API first, kb_articles table fallback."""
    kb_number = kb_number.strip().upper()
    if not kb_number:
        return None

    sn_pdf = await asyncio.to_thread(_fetch_kb_pdf_from_servicenow, kb_number)
    if sn_pdf:
        return sn_pdf

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT kb_data FROM kb_articles
                   WHERE UPPER(TRIM(kb_article_no)) = $1""",
                kb_number,
            )
        if row and row["kb_data"]:
            pdf_bytes = base64.b64decode(row["kb_data"], validate=True)
            if pdf_bytes.startswith(b"%PDF"):
                return pdf_bytes
    except ValueError:
        raise
    except Exception as e:
        logger.warning("KB article %s database PDF lookup failed: %s", kb_number, e)
    return None

async def _load_kb_article_pdf_cached(
    kb_number: str,
    pdf_cache: dict[str, bytes | None],
) -> bytes | None:
    key = kb_number.strip().upper()
    if not key:
        return None
    if key not in pdf_cache:
        pdf_cache[key] = await _load_kb_article_pdf(key)
    return pdf_cache[key]

async def _fetch_kb_article_text(
    kb_number: str,
    pdf_cache: dict[str, bytes | None],
) -> str:
    """Plain text from cached KB article PDF bytes."""
    pdf_bytes = await _load_kb_article_pdf_cached(kb_number, pdf_cache)
    if not pdf_bytes:
        return ""
    extracted = await asyncio.to_thread(extract_plain_text_from_pdf_bytes, pdf_bytes)
    if not extracted.strip():
        return ""
    return extracted[:_MAX_KB_TEXT_FOR_SUMMARY]

async def _generate_kb_playbook_summary(
    cleaned_issue: str,
    incident_number: str,
    kb_articles: list[dict],
    pool,
    pdf_cache: dict[str, bytes | None],
) -> dict | None:
    """Summarize KB PDF(s) via _load_kb_article_pdf (parallel path to _generate_focused_playbook)."""
    sections: list[str] = []
    for art in kb_articles:
        number = (art.get("number") or "").strip().upper()
        if not number:
            continue
        body = await _fetch_kb_article_text(number, pdf_cache)
        if not body.strip():
            continue
        title = art.get("short_description") or number
        sections.append(f"### {number}: {title}\n{body}")

    articles_with_text = len(sections)
    if not articles_with_text:
        return None

    kb_content = "\n\n".join(sections)[:_MAX_KB_TEXT_FOR_SUMMARY]
    safe_issue = _sanitize_for_prompt(cleaned_issue)
    safe_inc = _sanitize_for_prompt(incident_number or "N/A", max_len=50)
    safe_kb = _sanitize_for_prompt(kb_content, max_len=_MAX_KB_TEXT_FOR_SUMMARY)

    system_prompt = f"""You are a technical writer for {ORG_NAME} support engineers.
Summarize official knowledge base content for the incident at hand.
Use only facts from the knowledge article text. Do not invent steps or systems."""

    user_prompt = f"""INCIDENT: {safe_issue}
INCIDENT NUMBER: {safe_inc}

KNOWLEDGE ARTICLE CONTENT:
{safe_kb}

Write a concise playbook-style summary (max 500 words) for the engineer handling this incident.

Use this format:

## Knowledge Article Summary

**Article(s):** List KB numbers referenced.

**What this article covers:** 2-3 sentences.

**Steps for this incident:**
1. Actionable steps from the article
2. Continue as needed

**Prerequisites / checks:** Bullet list if present in the article.

**Escalate when:** Only if stated in the article.

RULES: Only use information from the knowledge article text. Be specific and actionable."""

    model = get_chat_model()
    resp = await chat_complete(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=1500,
        temperature=0.1,
    )
    summary = (resp.choices[0].message.content or "").strip()
    if not summary:
        return None

    if pool:
        usage = resp.usage
        await track_usage(
            pool, "completion", model,
            usage.prompt_tokens, usage.completion_tokens,
            endpoint="/analyze-kb-summary",
            incident_number=incident_number,
        )

    # Official KB PDF text is primary-source evidence; floor above sparse incident-note tiers.
    grounding = max(_compute_grounding_score(articles_with_text), 0.85)

    return {
        "playbook": summary,
        "notes": "",
        "grounding_score": grounding,
        "source_incident_count": articles_with_text,
        "total_similar": len(kb_articles),
        "top_problem": None,
        "secondary_problem": None,
        "other_problems": [],
        "order_ids": [],
        "jira_tickets": [],
        "playbook_source": "knowledge_article",
    }

# ── POST /analyze — from ServiceNow JSON ──────────────────────────

async def _run_analyze(req: AnalyzeRequest) -> dict:
    """Core analysis logic — no HTTP plumbing. Called by the endpoint AND the sync pipeline."""
    cleaned_issue, embedding_text = build_embedding_text(req.ticket_json)
    if not embedding_text.strip():
        raise HTTPException(400, "No usable text found in ticket JSON")

    # Check if this incident already exists
    incident_section = req.ticket_json.get("incident_section", {})
    incident_number = incident_section.get("Number", "") or req.ticket_json.get("incident_number", "")

    try:
        embedding = await embed_text(embedding_text)
    except Exception as exc:
        logger.error("Embedding failed for analyze: %s", exc)
        raise HTTPException(
            503,
            f"OpenAI embedding unavailable: {_llm_error_summary(exc)}",
        ) from exc
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    pool = await get_pool()

    # Track embedding token usage (~1 token per 4 chars)
    embed_tokens = len(embedding_text) // 4
    from backend.api.utils.llm_provider import get_embed_model
    await track_usage(pool, "embedding", get_embed_model(), embed_tokens, 0,
                      endpoint="/analyze", incident_number=incident_number)
    async with pool.acquire() as conn:
        # Check existence
        incident_exists = False
        if incident_number:
            existing = await conn.fetchval(
                "SELECT id FROM rexus_incidents_v3 WHERE incident_number = $1", incident_number
            )
            incident_exists = existing is not None

        # Hybrid search: vector + keyword on v3 table
        raw_query = req.ticket_json.get("pdf_fields", {}).get("Short description", "") or ""

        # Vector search on v3
        vector_results = await conn.fetch(
            """SELECT id as incident_id, incident_number, short_description, close_notes,
                      (1 - (embedding <=> $1::vector))::float AS similarity_score,
                      NULL::int as cluster_id
               FROM rexus_incidents_v3
               WHERE embedding IS NOT NULL
                 AND split_group IN ('training',  'analyzed', 'synced')
                 AND 1 - (embedding <=> $1::vector) >= $2
               ORDER BY embedding <=> $1::vector
               LIMIT $3""",
            embedding_str, req.threshold - 0.05, req.limit,
        )

        # Keyword search on v3 (trigram)
        keyword_results = []
        if raw_query and len(raw_query) > 5:
            keyword_results = await conn.fetch(
                """SELECT id as incident_id, incident_number, short_description, close_notes,
                          similarity(short_description, $1)::float AS similarity_score,
                          NULL::int as cluster_id
                   FROM rexus_incidents_v3
                   WHERE split_group IN ('training', 'analyzed', 'synced')
                     AND short_description % $1
                   ORDER BY similarity(short_description, $1) DESC
                   LIMIT $2""",
                raw_query, req.limit,
            )

        logger.info(
            "Analyze %s: vector=%d keyword=%d threshold=%.2f",
            incident_number, len(vector_results), len(keyword_results), req.threshold,
        )

        # Merge: MAX(vector, keyword) + agreement bonus
        merged: dict[int, dict] = {}
        for r in vector_results:
            merged[r["incident_id"]] = {**dict(r), "vec": r["similarity_score"], "kw": 0.0}
        for r in keyword_results:
            iid = r["incident_id"]
            if iid in merged:
                merged[iid]["kw"] = r["similarity_score"]
            else:
                merged[iid] = {**dict(r), "vec": 0.0, "kw": r["similarity_score"]}

        # Calculate hybrid score — capped at 1.0 so it never exceeds 100%
        for iid, m in merged.items():
            base = max(m["vec"], m["kw"])
            bonus = min(m["vec"], m["kw"]) * _HYBRID_BONUS_MULTIPLIER if m["vec"] > _HYBRID_VEC_MIN and m["kw"] > _HYBRID_KW_MIN else 0
            m["similarity_score"] = min(base + bonus, 1.0)

        # Sort by hybrid score and take top N
        similar = sorted(merged.values(), key=lambda x: -x["similarity_score"])[:req.limit]

        # Determine dominant cluster
        cluster_ids = [r["cluster_id"] for r in similar if r["cluster_id"]]
        dominant_cluster_id = max(set(cluster_ids), key=cluster_ids.count) if cluster_ids else None

        # Confidence = top match similarity
        confidence_score = similar[0]["similarity_score"] if similar else 0.0

        # Cluster info
        cluster_info = None
        if dominant_cluster_id:
            cluster_info = await conn.fetchrow(
                """SELECT id, cluster_name, cluster_description, incident_count,
                          dominant_category, avg_resolution_hours, avg_internal_similarity
                   FROM rexus_clusters WHERE id = $1""",
                dominant_cluster_id,
            )

        # ARCH-001 FIX: Batch fetch ALL incident details in a single SELECT instead of N+1
        similar_ids = [r["incident_id"] for r in similar]
        if similar_ids:
            detail_rows = await conn.fetch(
                """SELECT id, incident_number, short_description, description, category,
                          subcategory, priority, state, cmdb_ci, assignment_group,
                          close_notes, close_code, opened_at, resolved_at, closed_at,
                          business_duration, problem_id, u_jira_number, u_order_number,
                          work_notes
                   FROM rexus_incidents_v3
                   WHERE id = ANY($1)""",
                similar_ids,
            )
        else:
            detail_rows = []

        # Build id → detail map, preserving similarity scores from search results
        detail_map = {row["id"]: dict(row) for row in detail_rows}
        incident_details = []
        for r in similar:
            detail = detail_map.get(r["incident_id"])
            if detail:
                detail["similarity_score"] = r["similarity_score"]
                detail["cluster_id"] = r["cluster_id"]
                incident_details.append(detail)

        # Resolution patterns from top matches
        resolutions = []
        for r in similar:
            if r["close_notes"] and len(r["close_notes"].strip()) > 5:
                resolutions.append({
                    "incident_number": r["incident_number"],
                    "close_notes": r["close_notes"],
                    "similarity": round(r["similarity_score"], 4),
                })

    incoming_cmdb = (
        req.ticket_json.get("incident_section", {}).get("Configuration item", "")
        or req.ticket_json.get("cmdb_ci", "")
        or ""
    )
    focused_playbook = await _generate_focused_playbook(
        cleaned_issue, incident_details, incoming_cmdb,
        dict(cluster_info) if cluster_info else None, pool,
    )

    kb_articles, kb_meta = await pick_kb_for_analysis(
        incident_number,
        req.ticket_json.get("kb_articles") or [],
        incident_details,
    )
    focused_playbook["kb_articles"] = await enrich_kb_articles_from_servicenow(kb_articles)
    focused_playbook.update(kb_meta)
    if kb_articles:
        if kb_meta.get("kb_source") == "incident":
            logger.warning(
                "Analyze KB from incoming incident: kb=%s incoming=%s count=%s",
                ", ".join(a.get("number", "") for a in kb_articles),
                incident_number,
                len(kb_articles),
            )
        else:
            logger.warning(
                "Analyze KB from similar incident mapping: kb=%s via_incident=%s match_percent=%s incoming=%s",
                kb_articles[0].get("number"),
                kb_meta.get("kb_source_incident"),
                kb_meta.get("kb_match_percent"),
                incident_number,
            )
    else:
        logger.warning(
            "Analyze: no KB from similar-incident mapping for %s",
            incident_number,
        )
    await apply_kb_playbook_to_focused(focused_playbook, pool=pool)

    # SEC-003 FIX: Don't expose embedding_text (contains sensitive concatenated data)
    # SEC-014 FIX: Strip work_notes from similar_incidents response (PII) — already handled in incidents.py
    safe_incidents = []
    for inc in incident_details[:10]:
        safe = {k: v for k, v in inc.items() if k not in ("work_notes", "embedding_text")}
        safe_incidents.append(safe)

    result: dict = {
        "cleaned_issue": cleaned_issue,
        "confidence_score": round(confidence_score, 4),
        "incident_exists": incident_exists,
        "incident_number": incident_number or None,
        "match_count": len(similar),
        "similar_incidents": safe_incidents,
        "dominant_cluster": dict(cluster_info) if cluster_info else None,
        "focused_playbook": focused_playbook,
        "resolution_patterns": resolutions[:5],
    }

    similar_summary = [
        {"incident_number": d["incident_number"], "similarity_score": d["similarity_score"],
         "short_description": d["short_description"] or "", "close_notes": (d.get("close_notes") or "")[:300]}
        for d in incident_details[:10]
    ]

    # Save to analysis log for review
    async with pool.acquire() as conn:
        log_id = await conn.fetchval(
            """INSERT INTO rexus_analysis_log
               (incident_number, input_json, cleaned_issue, confidence_score,
                match_count, dominant_cluster_id, dominant_cluster_name,
                focused_playbook_content, focused_playbook_grounding,
                top_problem_id, similar_incidents, full_response)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
               RETURNING id""",
            incident_number or None,
            json.dumps({"cleaned_issue": cleaned_issue, "incident_number": incident_number}, default=_json_serial),  # SEC-003: store only sanitized data, not raw PII
            cleaned_issue,
            confidence_score,
            len(similar),
            dominant_cluster_id,
            cluster_info["cluster_name"] if cluster_info else None,
            focused_playbook.get("playbook", ""),
            focused_playbook.get("grounding_score", 0),
            focused_playbook.get("top_problem", {}).get("id") if focused_playbook.get("top_problem") else None,
            json.dumps(similar_summary, default=_json_serial),
            json.dumps(result, default=_json_serial),
        )

    result["analysis_id"] = log_id

    # Progressive learning: add this incident to the knowledge base
    # so future queries benefit from it (only if it doesn't already exist).
    # ARCH-014: Table rexus_incidents_v3 confirmed correct for progressive inserts.
    if not incident_exists and incident_number and confidence_score > 0:
        try:
            pdf_fields = req.ticket_json.get("pdf_fields", {})
            inc_section = req.ticket_json.get("incident_section", {})
            async with pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO rexus_incidents_v3
                       (incident_number, short_description, description,
                        category, subcategory, priority, cmdb_ci, assignment_group,
                        caller_id, location, opened_at,
                        split_group, embedding_text, embedding)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 'analyzed', $12, $13)
                       ON CONFLICT (incident_number) DO NOTHING""",
                    incident_number,
                    pdf_fields.get("Short description", ""),
                    pdf_fields.get("Description", ""),
                    inc_section.get("Category", ""),
                    inc_section.get("Subcategory", ""),
                    inc_section.get("Priority", ""),
                    inc_section.get("Configuration item", ""),
                    inc_section.get("Assignment group", ""),
                    inc_section.get("Caller", ""),
                    inc_section.get("Location", ""),
                    None,  # opened_at — parse if available                    embedding_text,
                    "[" + ",".join(str(x) for x in embedding) + "]",
                )
        except Exception as e:
            logger.warning(f"Progressive learning failed for {incident_number}: {e}")

    return result

# ── POST /analyze — from ServiceNow JSON ──────────────────────────

@router.post("/analyze", response_model=AnalyzeResponse)
@limiter.limit(os.getenv("RATE_LIMIT_ANALYZE", "20/minute"))
async def analyze_ticket(request: Request, req: AnalyzeRequest):
    """HTTP endpoint — delegates to _run_analyze (no rate-limit / Request dependency there)."""
    return await _run_analyze(req)

# ── POST /analyze/text — from plain text ──────────────────────────

@router.post("/analyze/text", response_model=AnalyzeResponse)
@limiter.limit(os.getenv("RATE_LIMIT_ANALYZE", "20/minute"))
async def analyze_text(request: Request, req: AnalyzeTextRequest):
    """
    Analyze from plain text (wraps into ticket_json format).
    ENH-015: This is an intentional convenience wrapper — it normalises the plain-text    input into the same ticket_json shape that analyze_ticket expects.
    """
    ticket_json = {
        "pdf_fields": {"Short description": req.text, "Description": ""},
        "incident_section": {},
        "resolution_information_section": {},
    }
    wrapped_req = AnalyzeRequest(ticket_json=ticket_json, limit=req.limit, threshold=req.threshold)
    return await _run_analyze(wrapped_req)

# ── ServiceNow incident fetch + analyze ──────────────────────────

def _build_kb_url(number: str) -> str:
    """Construct a public ServiceNow KB article view URL."""
    instance = os.getenv("SERVICENOW_INSTANCE", "").rstrip("/")
    if not instance or not number:
        return ""
    return f"{instance}/kb_view.do?sysparm_article={number}"

def _extract_kb_articles(data: dict) -> list[dict]:
    """Pull KB articles from a ServiceNow response (detailed or search shape) and add a viewable URL."""
    raw = data.get("kb_articles")
    if not raw:
        inc = data.get("incident") or {}
        raw = inc.get("kb_articles") if isinstance(inc, dict) else None
    if not isinstance(raw, list):
        return []
    out = []
    for ka in raw:
        if not isinstance(ka, dict):
            continue
        number = ka.get("number", "")
        out.append({
            "sys_id": ka.get("sys_id", ""),
            "number": number,
            "short_description": ka.get("short_description", ""),
            "kb_category_display": ka.get("kb_category_display", ""),
            "attached_on": ka.get("attached_on", ""),
            "url": _build_kb_url(number),
        })
    return out

def _normalize_kb_article(ka: dict) -> dict | None:
    """Normalize KB article dicts from ServiceNow, ticket JSON, or the mapping table."""
    number = (ka.get("number") or ka.get("knowledge_article_number") or "").strip()
    if not number:
        return None
    return {
        "sys_id": ka.get("sys_id", ""),
        "number": number,
        "short_description": ka.get("short_description") or ka.get("kb_description") or "",
        "kb_category_display": ka.get("kb_category_display", ""),
        "attached_on": ka.get("attached_on", ""),
        "url": ka.get("url") or _build_kb_url(number),
        "source": ka.get("source", "servicenow"),
    }

async def _get_kb_article_fallbacks(incident_number: str) -> list[dict]:
    """Load KB article mappings from the local reference table when ServiceNow returns none."""
    if not incident_number:
        return []

    incident_number = incident_number.strip().upper()

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT knowledge_article_number, kb_description
                   FROM rexus_kb_article_incident_mapping
                   WHERE UPPER(TRIM(incident_number)) = $1
                   ORDER BY knowledge_article_number""",
                incident_number,
            )
    except Exception as e:
        logger.warning("KB article fallback lookup failed for %s: %s", incident_number, e)
        return []

    articles = []
    for row in rows:
        number = row["knowledge_article_number"]
        articles.append({
            "sys_id": "",
            "number": number,
            "short_description": row["kb_description"] or "",
            "kb_category_display": "",
            "attached_on": "",
            "url": _build_kb_url(number),
            "source": "mapping_table",
        })
    return articles

async def _resolve_kb_articles(
    ticket_kb: list,
    incident_number: str,
    pdf_cache: dict[str, bytes | None] | None = None,
) -> list[dict]:
    """Merge KB articles from ticket JSON with rexus_kb_article_incident_mapping."""
    articles: list[dict] = []
    seen: set[str] = set()

    for ka in ticket_kb:
        if not isinstance(ka, dict):
            continue
        normalized = _normalize_kb_article(ka)
        if normalized and normalized["number"] not in seen:
            seen.add(normalized["number"])
            articles.append(normalized)

    if incident_number:
        for ka in await _get_kb_article_fallbacks(incident_number):
            if ka["number"] not in seen:
                seen.add(ka["number"])
                articles.append(ka)

    if pdf_cache is not None:
        for art in articles:
            number = (art.get("number") or "").strip().upper()
            if not number:
                art.pop("pdf_base64", None)
                continue
            pdf_bytes = await _load_kb_article_pdf_cached(number, pdf_cache)
            if pdf_bytes:
                art["pdf_base64"] = base64.b64encode(pdf_bytes).decode("ascii")
            else:
                art.pop("pdf_base64", None)

    return articles

async def _build_ticket_json_from_sn(data: dict, incident_number: str) -> dict:
    """Convert ServiceNow detailed API response to ticket_json format."""
    inc = data.get("incident", {})
    res = data.get("resolution", {})
    notes = data.get("notes", {})
    order = data.get("order_data", {})
    contact = data.get("contact", {})
    kb_articles = await _resolve_kb_articles(
        _extract_kb_articles(data),
        incident_number,
        pdf_cache=None,
    )

    comments_list = notes.get("comments", [])
    comments_text = ""
    if isinstance(comments_list, list):
        comments_text = "\n".join(c.get("value", "") for c in comments_list)

    wn_list = notes.get("work_notes", [])
    first_work_note = ""
    if isinstance(wn_list, list):
        for note in reversed(wn_list):
            val = note.get("value", "")
            if len(val) > 50:
                first_work_note = val[:300]
                break

    return {
        "pdf_fields": {
            "Short description": inc.get("short_description", ""),
            "Description": inc.get("description", ""),
        },
        "incident_section": {
            "Number": inc.get("number", incident_number),
            "Category": inc.get("category", ""),
            "Subcategory": inc.get("subcategory", ""),
            "Priority": inc.get("priority_display", ""),
            "Configuration item": inc.get("cmdb_ci_display", ""),
            "Assignment group": inc.get("assignment_group_display", ""),
            "Caller": contact.get("caller_id_display", ""),
            "Location": inc.get("location_display", ""),
            "Impact": inc.get("impact_display", ""),
            "Urgency": inc.get("urgency_display", ""),
        },
        "incident_details": {
            "Error Category": order.get("u_error_category", ""),
            "IDoc Text": "",
        },
        "notes_section": {
            "Additional comments": comments_text,
            "First work note": first_work_note,
        },
        "resolution_information_section": {
            "Close notes": res.get("close_notes", ""),
            "Close code": res.get("close_code_display", ""),
        },
        "kb_articles": kb_articles,
    }

@router.post("/analyze/order", response_model=OrderAnalyzeResponse)
@limiter.limit(os.getenv("RATE_LIMIT_ANALYZE", "20/minute"))
async def analyze_by_order_number(request: Request, body: OrderAnalyzeRequest):
    """
    Look up local DB incidents that explicitly reference a sales order number,
    extract related tasks/problems/alternate orders, and generate summaries.
    """
    order_number = (body.order_number or "").strip()
    if not order_number:
        raise HTTPException(400, "Enter a sales order number.")
    if not order_number.isdigit():
        raise HTTPException(
            400,
            "Invalid sales order format. Enter digits only (e.g. 5073352821).",
        )

    from backend.api.services.order_analyze import analyze_order

    pool = await get_pool()
    try:
        return await analyze_order(pool, order_number)
    except Exception as e:
        logger.exception("Order analyze failed for %s: %s", order_number, e)
        raise HTTPException(500, f"Order analysis failed: {e}") from e


@router.get("/fetch-incident/{incident_number}")
@limiter.limit(os.getenv("RATE_LIMIT_ANALYZE", "20/minute"))
async def fetch_from_servicenow(request: Request, incident_number: str):
    """
    Fetch an incident from ServiceNow and return the ticket_json
    without running analysis. Lets the user preview before analyzing.
    """
    if not re.match(r'^INC\d+$', incident_number):
        raise HTTPException(400, "Invalid incident number format. Must be INC followed by digits.")

    from backend.services.servicenow_client import ServiceNowClient
    try:
        sn_client = ServiceNowClient()
    except ValueError:
        raise HTTPException(503, "ServiceNow credentials not configured")

    data = await asyncio.to_thread(sn_client.get_incident_detailed, incident_number)
    if not data:
        raise HTTPException(404, f"Incident {incident_number} not found in ServiceNow")

    return await _build_ticket_json_from_sn(data, incident_number)

@router.post("/analyze/incident/{incident_number}", response_model=AnalyzeResponse)
@limiter.limit(os.getenv("RATE_LIMIT_ANALYZE", "20/minute"))
async def analyze_from_servicenow(request: Request, incident_number: str,
                                   limit: int = 15, threshold: float = 0.40):
    """
    Fetch an incident directly from ServiceNow by INC number,
    convert to ticket_json format, and run the full analysis.
    """
    if not re.match(r'^INC\d+$', incident_number):
        raise HTTPException(400, "Invalid incident number format. Must be INC followed by digits.")

    from backend.services.servicenow_client import ServiceNowClient
    try:
        sn_client = ServiceNowClient()
    except ValueError:
        raise HTTPException(503, "ServiceNow credentials not configured")

    data = await asyncio.to_thread(sn_client.get_incident_detailed, incident_number)
    if not data:
        raise HTTPException(404, f"Incident {incident_number} not found in ServiceNow")
    ticket_json = await _build_ticket_json_from_sn(data, incident_number)
    wrapped_req = AnalyzeRequest(ticket_json=ticket_json, limit=limit, threshold=threshold)
    return await _run_analyze(wrapped_req)

# ── POST /parse-pdf — upload PDF, return JSON ─────────────────────

# SEC-005 FIX: PDF upload with validation
MAX_PDF_SIZE = 10 * 1024 * 1024  # 10MB

@router.post("/parse-pdf")
async def parse_pdf(file: UploadFile = File(...)):
    """Upload a ServiceNow incident PDF and return extracted JSON."""
    # Validate extension
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(400, "File must be a PDF")

    # Validate content type
    if file.content_type and file.content_type != "application/pdf":
        raise HTTPException(400, f"Invalid content type: {file.content_type}. Expected application/pdf")

    # Read with size limit
    content = await file.read()
    if len(content) > MAX_PDF_SIZE:
        raise HTTPException(400, f"File too large ({len(content)} bytes). Maximum is {MAX_PDF_SIZE} bytes")
    if len(content) < 100:
        raise HTTPException(400, "File too small to be a valid PDF")

    # Validate PDF magic bytes
    if not content.startswith(b'%PDF-'):
        raise HTTPException(400, "File does not appear to be a valid PDF")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        parser = PDFParser(tmp_path)
        return parser.extract()
    finally:
        os.remove(tmp_path)
