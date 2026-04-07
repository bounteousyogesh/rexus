import os
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
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY environment variable is required.")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")  # Optional; required when Claude integration is enabled
