import json
from typing import Optional

from pydantic import BaseModel, Field, model_validator

class AnalyzeRequest(BaseModel):
    ticket_json: dict
    limit: int = Field(15, ge=1, le=50)
    threshold: float = Field(0.40, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_ticket_json_size(self):
        """SEC-009: Limit ticket_json size to prevent DoS via oversized payloads."""
        serialized = json.dumps(self.ticket_json, default=str)
        if len(serialized) > 100_000:
            raise ValueError(
                f"ticket_json too large ({len(serialized)} chars, max 100,000). "
                "Reduce the payload size."
            )
        return self

class ProblemInfo(BaseModel):
    id: str
    count: int
    score: float
    is_open: bool

class FocusedPlaybookResult(BaseModel):
    playbook: str = ""
    notes: str = ""
    grounding_score: float = 0.0
    source_incident_count: int = 0
    total_similar: int = 0
    top_problem: Optional[ProblemInfo] = None
    secondary_problem: Optional[ProblemInfo] = None
    other_problems: list[str] = []
    order_ids: list[str] = []
    jira_tickets: list[str] = []

class AnalyzeResponse(BaseModel):
    """Response model for /analyze endpoint."""
    analysis_id: Optional[int] = None
    cleaned_issue: str
    confidence_score: float
    incident_exists: bool
    incident_number: Optional[str] = None
    match_count: int
    similar_incidents: list[dict]
    dominant_cluster: Optional[dict] = None
    focused_playbook: dict
    resolution_patterns: list[dict]

class AnalyzeTextRequest(BaseModel):
    text: str = Field(..., min_length=3, max_length=5000)
    limit: int = Field(15, ge=1, le=50)
    threshold: float = Field(0.40, ge=0.0, le=1.0)


class OrderAnalyzeRequest(BaseModel):
    order_number: str = Field(..., min_length=1, max_length=50)


class OrderIncidentCard(BaseModel):
    incident_number: str
    status: str = ""
    short_description: str = ""
    opened_at: Optional[str] = None
    two_line_summary: list[str] = []
    inc_tasks: list[str] = []
    alternate_orders: list[str] = []
    problem_refs: list[str] = []


class OrderAnalyzeSummary(BaseModel):
    analysis: str = ""
    accounting_actions: str = ""
    payment_activities: str = ""
    solutions: str = ""
    system_states: str = ""


class OrderAnalyzeResponse(BaseModel):
    order_number: str
    incident_count: int = 0
    message: str = ""
    incidents: list[OrderIncidentCard] = []
    summary: OrderAnalyzeSummary = Field(default_factory=OrderAnalyzeSummary)
