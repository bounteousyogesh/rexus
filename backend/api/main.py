"""
REX-US — FastAPI Backend
Incident intelligence API powered by pgvector similarity search.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from backend.api.database import get_pool, close_pool
from backend.api.routers import health, incidents, clusters, playbooks, search, analyze, analytics, feedback, wave_test, sync
from backend.api.routers import auth as auth_router

logger = logging.getLogger("rexus")


async def _ensure_default_admin() -> None:
    """Create a default admin user if none exists."""
    from backend.api.auth import hash_password

    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT id FROM rexus_users WHERE role = 'admin' LIMIT 1"
    )
    if row is None:
        default_pw = os.getenv("REXUS_ADMIN_PASSWORD", "RexUS@2026!")
        pw_hash = hash_password(default_pw)
        await pool.execute(
            "INSERT INTO rexus_users (username, password_hash, role) "
            "VALUES ($1, $2, 'admin') ON CONFLICT (username) DO NOTHING",
            "admin",
            pw_hash,
        )
        logger.warning(
            "Default admin account created. Change the password after first login."
        )


async def _run_migrations() -> None:
    """Run all SQL migrations in order on startup.

    Each migration uses IF NOT EXISTS / IF EXISTS guards, so re-running
    is safe. This eliminates the need to manually apply migrations or
    run CLI scripts before using the UI.
    """
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    if not migrations_dir.is_dir():
        logger.warning("Migrations directory not found at %s — skipping", migrations_dir)
        return

    pool = await get_pool()
    sql_files = sorted(migrations_dir.glob("*.sql"))
    for sql_file in sql_files:
        try:
            sql = sql_file.read_text()
            await pool.execute(sql)
            logger.info("Migration applied: %s", sql_file.name)
        except Exception as exc:
            logger.warning("Migration %s skipped (may already be applied): %s", sql_file.name, exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    await _run_migrations()
    try:
        await _ensure_default_admin()
    except Exception as exc:
        # Don't crash the app if the users table doesn't exist yet
        logger.info("Skipping admin bootstrap (table may not exist yet): %s", exc)
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
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


# SEC-016 FIX: Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    # SEC-005: Content-Security-Policy for defense-in-depth against XSS
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )
    return response


# SEC-008 FIX: Global exception handler — don't leak internal errors
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


# DIAG-001: Log full Pydantic validation errors so 422s are debuggable in CloudWatch
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning("422 Validation error on %s %s: %s", request.method, request.url, exc.errors())
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


# ARCH-013: Rate limiting via slowapi — protects expensive endpoints from abuse.
# Configurable via environment variables.
_RATE_ANALYZE = os.getenv("RATE_LIMIT_ANALYZE", "20/minute")
_RATE_SYNC = os.getenv("RATE_LIMIT_SYNC", "5/minute")
_RATE_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "60/minute")

limiter = Limiter(key_func=get_remote_address, default_limits=[_RATE_DEFAULT])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


app.include_router(health.router)
app.include_router(auth_router.router, prefix="/api/v1")
app.include_router(incidents.router, prefix="/api/v1")
app.include_router(clusters.router, prefix="/api/v1")
app.include_router(playbooks.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(analyze.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(feedback.router, prefix="/api/v1")
app.include_router(wave_test.router, prefix="/api/v1")
app.include_router(sync.router, prefix="/api/v1")
