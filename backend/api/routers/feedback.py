"""
REX-US Feedback — voice + text feedback on analysis results.
"""

import os
import tempfile

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from openai import AsyncOpenAI

from backend.api.config import OPENAI_API_KEY
from backend.api.database import get_pool

router = APIRouter(tags=["feedback"])

# ENH-011: Shared AsyncOpenAI singleton — avoids creating a new client object
# per transcription request (each instantiation opens an httpx connection pool).
_openai_client: AsyncOpenAI | None = None


def _get_openai() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


class FeedbackRequest(BaseModel):
    analysis_id: int | None = None
    incident_number: str | None = Field(None, max_length=20)
    feedback_text: str = Field(..., min_length=1, max_length=5000)  # SEC-009 FIX
    feedback_type: str = Field("general", max_length=50)
    input_method: str = Field("text", max_length=20)
    rating: int | None = Field(None, ge=1, le=5)


@router.post("/feedback")
async def submit_feedback(req: FeedbackRequest):
    pool = await get_pool()
    async with pool.acquire() as conn:
        fid = await conn.fetchval(
            """INSERT INTO rexus_feedback
               (analysis_id, incident_number, feedback_type, feedback_text, input_method, rating)
               VALUES ($1, $2, $3, $4, $5, $6)
               RETURNING id""",
            req.analysis_id, req.incident_number, req.feedback_type,
            req.feedback_text, req.input_method, req.rating,
        )
    return {"feedback_id": fid, "status": "saved"}


@router.get("/feedback")
async def list_feedback(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    pool = await get_pool()
    offset = (page - 1) * page_size
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM rexus_feedback")
        rows = await conn.fetch(
            """SELECT f.*, a.cleaned_issue, a.confidence_score as analysis_confidence
               FROM rexus_feedback f
               LEFT JOIN rexus_analysis_log a ON a.id = f.analysis_id
               ORDER BY f.created_at DESC
               LIMIT $1 OFFSET $2""",
            page_size, offset,
        )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "items": [dict(r) for r in rows],
    }


# SEC-006 FIX: Audio upload with validation
MAX_AUDIO_SIZE = 25 * 1024 * 1024  # 25MB (Whisper limit)
ALLOWED_AUDIO_TYPES = {"audio/webm", "audio/wav", "audio/mp3", "audio/mpeg", "audio/ogg", "audio/mp4"}

@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcribe audio using OpenAI Whisper."""
    # Validate file type
    if file.content_type and file.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(400, f"Invalid audio type: {file.content_type}")

    # Read with size limit
    content = await file.read()
    if len(content) > MAX_AUDIO_SIZE:
        raise HTTPException(400, f"Audio file too large ({len(content)} bytes). Maximum is {MAX_AUDIO_SIZE} bytes")
    if len(content) < 100:
        raise HTTPException(400, "File too small to be valid audio")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # ENH-011: Use shared client singleton instead of creating per-request
        client = _get_openai()
        with open(tmp_path, "rb") as audio_file:
            transcript = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )
        return {"text": transcript.text}
    finally:
        os.remove(tmp_path)
