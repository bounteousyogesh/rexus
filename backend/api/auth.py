"""
REX-US Authentication Utilities
Provides password hashing (bcrypt), JWT creation/verification,
and FastAPI dependencies for protecting endpoints.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, Request


# JWT configuration
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24
_jwt_secret: str | None = None


def _get_jwt_secret() -> str:
    """Lazy-load JWT secret — ensures .env is loaded before reading."""
    global _jwt_secret
    if _jwt_secret is None:
        _jwt_secret = os.getenv("REXUS_JWT_SECRET") or secrets.token_hex(32)
        if not os.getenv("REXUS_JWT_SECRET"):
            import logging
            logging.getLogger(__name__).warning(
                "REXUS_JWT_SECRET not set — using random secret. Tokens will not survive restart."
            )
    return _jwt_secret


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_token(user_id: int, username: str, role: str) -> str:
    """Create a signed JWT with 24-hour expiry."""
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=JWT_ALGORITHM)


async def get_current_user(request: Request) -> dict:
    """
    FastAPI dependency: extract and validate JWT from the Authorization header.
    Returns a dict with user_id, username, and role.
    Raises 401 if token is missing, expired, or invalid.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = auth_header[7:]  # Strip "Bearer "
    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    return {
        "user_id": int(payload["sub"]),
        "username": payload["username"],
        "role": payload["role"],
    }


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency: require the authenticated user to have the admin role."""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


_ADMIN_KEY = os.getenv("REXUS_ADMIN_KEY", "")


async def require_admin_or_api_key(
    request: Request,
    x_admin_key: Optional[str] = Header(None),
) -> dict:
    """
    FastAPI dependency for maintenance endpoints (sync import, KB mapping refresh).
    Accepts either a valid admin JWT or X-Admin-Key matching REXUS_ADMIN_KEY.
    """
    if _ADMIN_KEY and x_admin_key and secrets.compare_digest(x_admin_key, _ADMIN_KEY):
        return {"role": "admin", "via": "api_key"}

    user = await get_current_user(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user