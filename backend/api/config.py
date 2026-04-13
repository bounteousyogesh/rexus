import os
import warnings

from pathlib import Path

from dotenv import load_dotenv

# Load .env from repo root
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path, override=True)

# SEC-002 FIX: No hardcoded defaults for sensitive config — require .env
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required. Copy .env.example to .env and configure.")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
if LLM_PROVIDER == "openai" and not OPENAI_API_KEY:
    warnings.warn("OPENAI_API_KEY is not set. LLM features will not work.", stacklevel=2)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")  # Optional; required when Claude integration is enabled

# SSO / Okta OIDC configuration
SSO_ENABLED = os.getenv("SSO_ENABLED", "false").lower() == "true"
SSO_CLIENT_ID = os.getenv("SSO_CLIENT_ID", "")
SSO_ISSUER_URL = os.getenv("SSO_ISSUER_URL", "")
SSO_AUDIENCE = os.getenv("SSO_AUDIENCE", "")
SSO_DEFAULT_ROLE = os.getenv("SSO_DEFAULT_ROLE", "analyst")
SSO_REDIRECT_URI = os.getenv("SSO_REDIRECT_URI", "http://localhost:5173/auth/callback")
