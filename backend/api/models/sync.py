from pydantic import BaseModel, Field
from datetime import date as DateType

from backend.api.utils.sync_constants import (
    IncidentNumber,
    NEW_INCIDENTS_SYNC_MAX,
    SYNC_IMPORT_MAX,
)

class ImportRequest(BaseModel):
    incident_numbers: list[IncidentNumber] = Field(..., max_length=SYNC_IMPORT_MAX)

class NewIncidentsRunRequest(BaseModel):
    incident_numbers: list[IncidentNumber] = Field(
        default_factory=list,
        max_length=NEW_INCIDENTS_SYNC_MAX,
    )


class ClosedIncidentSyncRunRequest(BaseModel):
    date: DateType | None = Field(
        default=None,
        description="YYYY-MM-DD — incidents updated on this date (default: today)",
    )


class ClosedIncidentSyncConfigUpdate(BaseModel):
    enabled: bool = True
    interval_hours: int = Field(default=24, ge=1, le=168)


class NewIncidentSyncConfigUpdate(BaseModel):
    enabled: bool = True
    interval_hours: int = Field(default=24, ge=1, le=168)
