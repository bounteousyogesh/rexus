#!/bin/bash
# REX-US — One-Command Setup
# Usage: ./setup.sh
#
# Prerequisites: Python 3.11+, Node.js 18+, Docker (optional — for local DB)
# If using an external database, set DATABASE_URL in .env before running.

set -e
cd "$(dirname "$0")"

echo "========================================="
echo "  REX-US Setup"
echo "========================================="

# Step 1: Check prerequisites
echo ""
echo "[1/6] Checking prerequisites..."
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found. Install Python 3.11+"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "ERROR: node not found. Install Node.js 18+"; exit 1; }
echo "  Python: $(python3 --version)"
echo "  Node:   $(node --version)"

# Step 2: Environment file
echo ""
echo "[2/6] Setting up environment..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  Created .env from .env.example"
    echo "  *** EDIT .env WITH YOUR CREDENTIALS BEFORE CONTINUING ***"
    echo "  Required: SERVICENOW_INSTANCE, SERVICENOW_CLIENT_ID, SERVICENOW_CLIENT_SECRET, OPENAI_API_KEY"
    echo ""
    read -p "  Press Enter after editing .env (or Ctrl+C to abort)..."
else
    echo "  .env already exists"
fi

# Step 3: Database
echo ""
echo "[3/6] Setting up database..."

# Check if DATABASE_URL points to an external DB or we need Docker
DB_URL=$(grep "^DATABASE_URL=" .env | cut -d= -f2-)

if echo "$DB_URL" | grep -q "localhost:5434"; then
    # Local Docker database
    if command -v docker >/dev/null 2>&1; then
        echo "  Starting local PostgreSQL + pgvector via Docker..."
        docker compose up -d
        sleep 5
        echo "  Applying schema..."
        cat backend/migrations/002_enriched_schema.sql | docker exec -i rexus-db psql -U rexus
        echo "  Local database ready on port 5434"
    else
        echo "  ERROR: Docker not found but DATABASE_URL points to localhost:5434"
        echo "  Either install Docker or set DATABASE_URL to an external PostgreSQL with pgvector"
        exit 1
    fi
else
    # External database
    echo "  Using external database: $DB_URL"
    echo "  Ensure pgvector extension is installed on your database."
    echo "  Applying schema..."
    PGPASSWORD=$(echo $DB_URL | sed 's|.*://[^:]*:\([^@]*\)@.*|\1|') \
    psql "$DB_URL" < backend/migrations/002_enriched_schema.sql 2>/dev/null || \
    echo "  WARNING: Could not apply schema automatically. Run manually:"
    echo "  psql \$DATABASE_URL < backend/migrations/002_enriched_schema.sql"
fi

# Step 4: Backend
echo ""
echo "[4/6] Setting up backend..."
if [ ! -d backend/.venv ]; then
    python3 -m venv backend/.venv
    echo "  Created virtual environment"
fi
backend/.venv/bin/pip install -q -r backend/requirements.txt
backend/.venv/bin/pip install -q psycopg2-binary requests spacy
backend/.venv/bin/python -m spacy download en_core_web_sm -q 2>/dev/null
echo "  Backend dependencies installed"

# Step 5: Frontend
echo ""
echo "[5/6] Setting up frontend..."
cd frontend
npm install --silent 2>/dev/null
cd ..
echo "  Frontend dependencies installed"

# Step 6: Verify
echo ""
echo "[6/6] Verifying setup..."
echo "  Starting backend temporarily..."
backend/.venv/bin/python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
sleep 4

if curl -s http://localhost:8000/health | grep -q "healthy"; then
    echo "  Backend: OK"
else
    echo "  Backend: FAILED — check .env credentials"
fi
kill $BACKEND_PID 2>/dev/null

echo ""
echo "========================================="
echo "  Setup Complete!"
echo "========================================="
echo ""
echo "  Next steps:"
echo "  1. Import incidents:  backend/.venv/bin/python backend/scripts/enrich_incidents.py --split training --batch-size 50"
echo "  2. Load & embed:      backend/.venv/bin/python backend/scripts/load_enriched_v3.py data/enriched/enriched_training.json --split training"
echo "  3. Start the app:     ./dev.sh"
echo "  4. Open browser:      http://localhost:5173"
echo ""
