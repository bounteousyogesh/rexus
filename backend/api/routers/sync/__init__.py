"""ServiceNow sync: shared helpers, manual SN import, scheduled incident sync."""

from fastapi import APIRouter

from .servicenow_sync import router as servicenow_router
from .new_incident import router as new_router
from .closed_incident import router as closed_router
from .sync import filter_incidents_by_opened_date

router = APIRouter(tags=["sync"])
router.include_router(servicenow_router)
router.include_router(new_router)
router.include_router(closed_router)
