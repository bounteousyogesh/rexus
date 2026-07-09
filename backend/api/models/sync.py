from pydantic import BaseModel, Field, model_validator
from datetime import date as DateType, datetime

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
    start_date: DateType | None = Field(
        default=None,
        description="YYYY-MM-DD — start of manual sync window (default: today)",
    )
    end_date: DateType | None = Field(
        default=None,
        description="YYYY-MM-DD — end of manual sync window (default: today)",
    )

    @model_validator(mode="after")
    def _default_dates(self):
        # Max 7-day range is enforced in the UI only.
        self.start_date = self.start_date or DateType.today()
        self.end_date = self.end_date or DateType.today()
        return self


class ClosedIncidentSyncRunRequest(BaseModel):
    start_date: DateType | None = Field(
        default=None,
        description="YYYY-MM-DD — start of manual sync window (default: today)",
    )
    end_date: DateType | None = Field(
        default=None,
        description="YYYY-MM-DD — end of manual sync window (default: today)",
    )

    @model_validator(mode="after")
    def _default_dates(self):
        # Max 7-day range is enforced in the UI only.
        self.start_date = self.start_date or DateType.today()
        self.end_date = self.end_date or DateType.today()
        return self


class ClosedIncidentSyncConfigUpdate(BaseModel):
    enabled: bool = True
    interval_hours: int = Field(default=24, ge=1, le=168)
    start_at: datetime | None = None


class NewIncidentSyncConfigUpdate(BaseModel):
    enabled: bool = True
    interval_hours: int = Field(default=24, ge=1, le=168)
    start_at: datetime | None = None
