"""
REX-US Auth Router
Endpoints for login, user management, password changes, and SSO (Okta OIDC/PKCE).
"""

import base64
import json
import logging

import requests as http_requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.auth import (
    create_token,
    get_current_user,
    hash_password,
    require_admin,
    verify_password,
)
from backend.api.config import (
    SSO_AUDIENCE,
    SSO_CLIENT_ID,
    SSO_DEFAULT_ROLE,
    SSO_ENABLED,
    SSO_ISSUER_URL,
    SSO_REDIRECT_URI,
)
from backend.api.database import get_pool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Request / Response Models ──────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: dict


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=8)
    email: str | None = None
    role: str = "analyst"


class UpdateUserRequest(BaseModel):
    email: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None  # admin can reset password


# ── Endpoints ──────────────────────────────────────────────────────

@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    """Authenticate with username and password, receive JWT."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT id, username, email, password_hash, role, is_active "
        "FROM rexus_users WHERE username = $1",
        body.username,
    )
    if not row:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    if not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Update last_login
    await pool.execute(
        "UPDATE rexus_users SET last_login = NOW() WHERE id = $1", row["id"]
    )

    token = create_token(row["id"], row["username"], row["role"])
    return {
        "token": token,
        "user": {"id": row["id"], "username": row["username"], "role": row["role"]},
    }


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT id, username, email, role, is_active, must_change_password, created_at, last_login "
        "FROM rexus_users WHERE id = $1",
        user["user_id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(row)


@router.put("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    user: dict = Depends(get_current_user),
):
    """Change the authenticated user's password."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT password_hash FROM rexus_users WHERE id = $1", user["user_id"]
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(body.current_password, row["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    new_hash = hash_password(body.new_password)
    await pool.execute(
        "UPDATE rexus_users SET password_hash = $1, must_change_password = false WHERE id = $2",
        new_hash,
        user["user_id"],
    )
    return {"status": "Password changed successfully"}


@router.get("/users")
async def list_users(admin: dict = Depends(require_admin)):
    """List all users (admin only)."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT id, username, email, role, is_active, must_change_password, created_at, last_login "
        "FROM rexus_users ORDER BY id"
    )
    return [dict(r) for r in rows]


@router.post("/users")
async def create_user(body: CreateUserRequest, admin: dict = Depends(require_admin)):
    """Create a new user (admin only)."""
    if body.role not in ("admin", "analyst", "viewer"):
        raise HTTPException(status_code=400, detail="Role must be admin, analyst, or viewer")

    pool = await get_pool()

    # Check duplicate username
    existing = await pool.fetchrow(
        "SELECT id FROM rexus_users WHERE username = $1", body.username
    )
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")

    pw_hash = hash_password(body.password)
    row = await pool.fetchrow(
        "INSERT INTO rexus_users (username, email, password_hash, role, must_change_password) "
        "VALUES ($1, $2, $3, $4, true) RETURNING id, username, email, role",
        body.username,
        body.email,
        pw_hash,
        body.role,
    )
    return dict(row)


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    body: UpdateUserRequest,
    admin: dict = Depends(require_admin),
):
    """Update a user's profile (admin only)."""
    pool = await get_pool()

    existing = await pool.fetchrow("SELECT id FROM rexus_users WHERE id = $1", user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

    updates: list[str] = []
    values: list = []
    idx = 1

    if body.email is not None:
        updates.append(f"email = ${idx}")
        values.append(body.email)
        idx += 1
    if body.role is not None:
        if body.role not in ("admin", "analyst", "viewer"):
            raise HTTPException(status_code=400, detail="Role must be admin, analyst, or viewer")
        updates.append(f"role = ${idx}")
        values.append(body.role)
        idx += 1
    if body.is_active is not None:
        updates.append(f"is_active = ${idx}")
        values.append(body.is_active)
        idx += 1
    if body.password is not None:
        updates.append(f"password_hash = ${idx}")
        values.append(hash_password(body.password))
        idx += 1
        updates.append(f"must_change_password = ${idx}")
        values.append(True)
        idx += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    values.append(user_id)
    query = f"UPDATE rexus_users SET {', '.join(updates)} WHERE id = ${idx} RETURNING id, username, email, role, is_active"
    row = await pool.fetchrow(query, *values)
    return dict(row)


@router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: int,
    admin: dict = Depends(require_admin),
):
    """Deactivate a user (admin only). Cannot deactivate self."""
    if admin["user_id"] == user_id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

    pool = await get_pool()
    existing = await pool.fetchrow("SELECT id FROM rexus_users WHERE id = $1", user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

    await pool.execute(
        "UPDATE rexus_users SET is_active = false WHERE id = $1", user_id
    )
    return {"status": "User deactivated"}


# ── SSO (Okta OIDC / PKCE) ──────────────────────────────────────

class SSOCallbackRequest(BaseModel):
    code: str
    code_verifier: str


@router.get("/sso/config")
async def sso_config():
    """Return SSO configuration for the frontend. No auth required."""
    if not SSO_ENABLED:
        return {"enabled": False}

    authorize_url = f"{SSO_ISSUER_URL}/v1/authorize"
    return {
        "enabled": True,
        "client_id": SSO_CLIENT_ID,
        "authorize_url": authorize_url,
        "redirect_uri": SSO_REDIRECT_URI,
        "audience": SSO_AUDIENCE,
    }


@router.post("/sso/callback")
async def sso_callback(body: SSOCallbackRequest):
    """
    Exchange an Okta authorization code (with PKCE code_verifier) for tokens,
    extract user info, find-or-create the user, and return a REX-US JWT.
    """
    if not SSO_ENABLED:
        raise HTTPException(status_code=400, detail="SSO is not enabled")

    # 1. Exchange auth code for tokens at Okta token endpoint
    token_url = f"{SSO_ISSUER_URL}/v1/token"
    token_payload = {
        "grant_type": "authorization_code",
        "client_id": SSO_CLIENT_ID,
        "code": body.code,
        "code_verifier": body.code_verifier,
        "redirect_uri": SSO_REDIRECT_URI,
    }

    try:
        token_resp = http_requests.post(
            token_url,
            data=token_payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
    except Exception as exc:
        logger.error("SSO token exchange network error: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to contact identity provider")

    if token_resp.status_code != 200:
        logger.error("SSO token exchange failed (%s): %s", token_resp.status_code, token_resp.text)
        raise HTTPException(status_code=401, detail="SSO token exchange failed")

    token_data = token_resp.json()
    id_token = token_data.get("id_token")
    if not id_token:
        raise HTTPException(status_code=401, detail="No id_token in SSO response")

    # 2. Decode ID token to extract user info (Okta already validated it)
    #    We do a base64 decode of the payload without cryptographic verification
    #    since the token came directly from Okta over HTTPS.
    try:
        payload_b64 = id_token.split(".")[1]
        # Fix padding
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        id_claims = json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception as exc:
        logger.error("Failed to decode id_token: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid id_token")

    email = id_claims.get("email", "")
    name = id_claims.get("name", "")
    preferred_username = id_claims.get("preferred_username", "")

    if not email:
        raise HTTPException(status_code=401, detail="SSO token missing email claim")

    # Use email prefix as username fallback
    sso_username = preferred_username or email.split("@")[0]

    # 3. Find or create user in rexus_users
    pool = await get_pool()

    row = await pool.fetchrow(
        "SELECT id, username, email, role, is_active FROM rexus_users WHERE email = $1",
        email,
    )

    if row:
        # Existing user
        if not row["is_active"]:
            raise HTTPException(status_code=403, detail="Account is deactivated")
        user_id = row["id"]
        username = row["username"]
        role = row["role"]
    else:
        # Auto-create user from SSO
        # Check if username is already taken; if so, append a suffix
        existing_username = await pool.fetchrow(
            "SELECT id FROM rexus_users WHERE username = $1", sso_username
        )
        if existing_username:
            sso_username = email.replace("@", "_at_").replace(".", "_")

        row = await pool.fetchrow(
            "INSERT INTO rexus_users (username, email, password_hash, role, must_change_password) "
            "VALUES ($1, $2, $3, $4, false) RETURNING id, username, role",
            sso_username,
            email,
            "",  # No password for SSO users
            SSO_DEFAULT_ROLE,
        )
        user_id = row["id"]
        username = row["username"]
        role = row["role"]
        logger.info("Auto-created SSO user: %s (%s) with role %s", username, email, role)

    # 4. Update last_login
    await pool.execute("UPDATE rexus_users SET last_login = NOW() WHERE id = $1", user_id)

    # 5. Issue REX-US JWT
    token = create_token(user_id, username, role)
    return {
        "token": token,
        "user": {"id": user_id, "username": username, "role": role},
    }
