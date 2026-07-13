"""
Frontend API call logging.
Receives log entries from the browser and writes them via Python's standard
logging infrastructure so they appear in the same log stream as backend logs.
"""
import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger("rexus.frontend")
# Attach a dedicated handler so these messages survive uvicorn's dictConfig
# takeover, which resets the root logger but leaves named loggers with their
# own handlers untouched.
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    ))
    logger.addHandler(_h)
    logger.propagate = False   # root logger already logs uvicorn lines; avoid duplicates

router = APIRouter(tags=["internal"])


class FrontendLogEntry(BaseModel):
    level: str          # "request" | "success" | "error"
    method: str
    url: str
    status: int | None = None
    body: Any = None
    response: Any = None
    ts: str             # ISO timestamp from the browser


@router.post("/log/frontend", status_code=204)
async def receive_frontend_log(entry: FrontendLogEntry) -> None:
    """Accept a single frontend API log entry and write it to the server log."""
    if entry.level == "request":
        logger.info(
            "[FRONTEND] → %s %s  body=%s",
            entry.method,
            entry.url,
            _truncate(entry.body),
        )
    elif entry.level == "error":
        logger.warning(
            "[FRONTEND] ← %s %s  status=%s  response=%s",
            entry.method,
            entry.url,
            entry.status,
            _truncate(entry.response),
        )
    else:
        logger.info(
            "[FRONTEND] ← %s %s  status=%s",
            entry.method,
            entry.url,
            entry.status,
        )


def _truncate(value: Any, max_len: int = 500) -> str:
    """Safely convert a value to string and truncate for log readability."""
    if value is None:
        return ""
    text = str(value)
    return text[:max_len] + "…" if len(text) > max_len else text
