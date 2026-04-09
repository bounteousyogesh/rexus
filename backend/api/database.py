import os
import asyncio

import asyncpg
from urllib.parse import urlparse, unquote

from backend.api.config import DATABASE_URL

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


def _parse_dsn() -> dict:
    """
    ARCH-010: Parse a postgresql:// DSN directly with urlparse — no need to
    swap the scheme prefix since urlparse handles postgresql:// natively.
    """
    parsed = urlparse(DATABASE_URL)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "database": unquote(parsed.path.lstrip("/").split("?")[0]),
        "user": unquote(parsed.username) if parsed.username else "rexus",
        "password": unquote(parsed.password) if parsed.password else "",
    }


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is not None:
        return _pool
    async with _pool_lock:
        if _pool is None:
            dsn = _parse_dsn()
            # ARCH-018: Pool sizes configurable via environment variables
            pool_min = int(os.getenv("DB_POOL_MIN", "2"))
            pool_max = int(os.getenv("DB_POOL_MAX", "10"))
            _pool = await asyncpg.create_pool(
                min_size=pool_min,
                max_size=pool_max,
                command_timeout=30.0,
                **dsn,
            )
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
