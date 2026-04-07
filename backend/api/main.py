"""
REX-US — FastAPI Backend
Incident intelligence API powered by pgvector similarity search.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from backend.api.database import get_pool, close_pool
from backend.api.routers import health, incidents, clusters, playbooks, search, analyze, analytics, feedback, wave_test, sync


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    yield
    await close_pool()


# SEC-017 FIX: Disable interactive docs in production
is_dev = os.getenv("REXUS_ENV", "development") == "development"

app = FastAPI(
    title="REX-US",
    description="Incident Intelligence API — vector search, clustering, and grounded playbooks",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if is_dev else None,
    redoc_url="/redoc" if is_dev else None,
)

# SEC-007 FIX: Configurable CORS origins from environment
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


# SEC-016 FIX: Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


# SEC-008 FIX: Global exception handler — don't leak internal errors
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


# ARCH-013: Rate limiting via slowapi — protects expensive endpoints from abuse.
# Configurable via environment variables.
_RATE_ANALYZE = os.getenv("RATE_LIMIT_ANALYZE", "20/minute")
_RATE_SYNC = os.getenv("RATE_LIMIT_SYNC", "5/minute")
_RATE_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "60/minute")

limiter = Limiter(key_func=get_remote_address, default_limits=[_RATE_DEFAULT])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


app.include_router(health.router)
app.include_router(incidents.router, prefix="/api/v1")
app.include_router(clusters.router, prefix="/api/v1")
app.include_router(playbooks.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(analyze.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(feedback.router, prefix="/api/v1")
app.include_router(wave_test.router, prefix="/api/v1")
app.include_router(sync.router, prefix="/api/v1")
