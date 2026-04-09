"""
REX-US Feedback — voice + text feedback on analysis results.
"""

import os
import tempfile
from typing import Literal

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, UploadFile, File, Query

from backend.api.database import get_pool
from backend.api.utils.llm_provider import LLM_PROVIDER

router = APIRouter(tags=["feedback"])


class FeedbackRequest(BaseModel):
    analysis_id: int | None = None
    incident_number: str | None = Field(None, max_length=20)
    feedback_text: str = Field(..., min_length=1, max_length=5000)  # SEC-009 FIX
    feedback_type: Literal["general", "positive", "negative", "suggestion"] = "general"
    input_method: Literal["text", "voice"] = "text"
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
    if not file.content_type or file.content_type not in ALLOWED_AUDIO_TYPES:
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
        if LLM_PROVIDER == "bedrock":
            # Bedrock doesn't have Whisper — use AWS Transcribe or return error
            raise HTTPException(501, "Voice transcription not available with Bedrock provider. Use text feedback.")

        from openai import AsyncOpenAI
        import os as _os
        client = AsyncOpenAI(api_key=_os.getenv("OPENAI_API_KEY"))
        with open(tmp_path, "rb") as audio_file:
            transcript = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )
        return {"text": transcript.text}
    finally:
        os.remove(tmp_path)
