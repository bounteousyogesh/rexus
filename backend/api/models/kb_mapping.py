from pydantic import BaseModel, Field

from backend.api.utils.sync_constants import IncidentNumber, KB_MAPPING_REFRESH_MAX

class KbMappingRefreshRequest(BaseModel):
    incident_numbers: list[IncidentNumber] = Field(..., max_length=KB_MAPPING_REFRESH_MAX)
