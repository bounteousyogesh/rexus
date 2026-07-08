from typing import Literal

from pydantic import BaseModel, Field

class FeedbackRequest(BaseModel):
    analysis_id: int | None = None
    incident_number: str | None = Field(None, max_length=20)
    feedback_text: str = Field(..., min_length=1, max_length=5000)
    feedback_type: Literal["general", "positive", "negative", "suggestion"] = "general"
    input_method: Literal["text", "voice"] = "text"
    rating: int | None = Field(None, ge=1, le=5)
