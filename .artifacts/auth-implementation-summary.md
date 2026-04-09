# REX-US Authentication System — Implementation Summary

## Overview
Complete username/password authentication with JWT tokens, role-based access control,
and admin user management. No existing routes were modified to require auth — the
system is additive and can be enforced later.

---

## Database

**Migration:** `backend/migrations/005_auth.sql`
- `rexus_users` table with id, username, email, password_hash (bcrypt), role, is_active, must_change_password, created_at, last_login
- Roles: `admin`, `analyst`, `viewer` (enforced via CHECK constraint)
- Indexes on username and role

---

## Backend

### Dependencies Added (`backend/requirements.txt`)
- `bcrypt==5.0.0` — password hashing
- `PyJWT==2.12.1` — JWT token creation and verification

### Auth Module (`backend/api/auth.py`)
- `hash_password(password)` — bcrypt hashing
- `verify_password(password, hash)` — bcrypt verification
- `create_token(user_id, username, role)` — JWT with 24h expiry, signed with `REXUS_JWT_SECRET` env var
- `get_current_user(request)` — FastAPI dependency, extracts Bearer token, returns user dict or 401
- `require_admin(user)` — FastAPI dependency, checks role == 'admin' or 403

### Auth Router (`backend/api/routers/auth.py`)
| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/auth/login` | POST | None | Authenticate, returns JWT + user |
| `/auth/me` | GET | Required | Current user profile |
| `/auth/change-password` | PUT | Required | Change own password |
| `/auth/users` | GET | Admin | List all users |
| `/auth/users` | POST | Admin | Create user |
| `/auth/users/{id}` | PUT | Admin | Update user (role, email, active, password) |
| `/auth/users/{id}` | DELETE | Admin | Deactivate user (can't deactivate self) |

### Startup Bootstrap (`backend/api/main.py`)
- On app startup, checks if any admin user exists in `rexus_users`
- If none found, creates default: `admin` / `RexUS@2026!` (or `REXUS_ADMIN_PASSWORD` env var)
- Gracefully skips if table doesn't exist yet (migration not run)
- CORS updated to allow PUT and DELETE methods

### Environment Variables
| Variable | Default | Purpose |
|---|---|---|
| `REXUS_JWT_SECRET` | Random 32-byte hex | JWT signing key |
| `REXUS_ADMIN_PASSWORD` | `RexUS@2026!` | Default admin password |

---

## Frontend

### Auth Context (`frontend/src/contexts/AuthContext.tsx`)
- React context providing: `user`, `token`, `isAuthenticated`, `isLoading`, `login()`, `logout()`
- On mount: reads token from `localStorage`, validates via `GET /auth/me`
- On invalid/expired token: clears storage and shows login

### Login Page (`frontend/src/pages/Login.tsx`)
- Username + password form with error display
- On success: stores token in localStorage, context updates, redirects to dashboard

### Admin Page (`frontend/src/pages/Admin.tsx`)
- Only visible in nav when user role is `admin`
- Users table: username, email, role, active status, last login
- Create user form with role dropdown
- Deactivate/activate toggle per user
- Reset password modal for admin to change any user's password

### Change Password (`frontend/src/pages/ChangePassword.tsx`)
- Modal component accessible from the sidebar for all authenticated users
- Current password + new password + confirm fields
- Success/error feedback

### App.tsx Updates
- Wrapped in `AuthProvider`
- Unauthenticated: shows `LoginPage`
- Authenticated: shows sidebar nav + pages
- Sidebar includes user info (username, role), "Change Password" link, and "Sign out" button
- Admin nav item conditionally shown for admin users

### API Updates (`frontend/src/api.ts`)
- All `get()`, `post()`, `put()`, `del()` helpers inject `Authorization: Bearer <token>` header
- `parsePdf` and `transcribeAudio` also include auth headers
- New `authApi` object with: `login`, `me`, `changePassword`, `listUsers`, `createUser`, `updateUser`, `deactivateUser`

---

## Validation
- All Python files pass `ast.parse()` syntax check
- `npx tsc --noEmit` passes with zero errors
- `from backend.api.main import app` imports successfully
- `/health` endpoint remains unauthenticated
- No existing routes were modified to require auth

---

## Setup Steps
1. Run migration: `psql $DATABASE_URL -f backend/migrations/005_auth.sql`
2. Install deps: `pip install -r backend/requirements.txt`
3. (Optional) Set env vars: `REXUS_JWT_SECRET`, `REXUS_ADMIN_PASSWORD`
4. Start backend — default admin account auto-created on first boot
5. Login at frontend with `admin` / `RexUS@2026!`
