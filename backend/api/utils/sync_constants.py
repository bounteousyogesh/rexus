"""Shared constants and types for sync and KB mapping refresh maintenance endpoints."""

import os
from typing import Annotated

from pydantic import Field

# SEC-020: Max incident numbers per POST /sync/import.
SYNC_IMPORT_MAX = int(os.getenv("SYNC_IMPORT_MAX_INCIDENTS", "1000"))

# Max incident numbers per POST /kb-mappings/refresh.
KB_MAPPING_REFRESH_MAX = int(os.getenv("KB_MAPPING_REFRESH_MAX", "500"))

# Max incidents per POST /sync/new-incidents/run.
NEW_INCIDENTS_SYNC_MAX = int(os.getenv("NEW_INCIDENTS_SYNC_MAX", "500"))

IncidentNumber = Annotated[str, Field(min_length=3, max_length=20, pattern=r"^INC\d+$")]
