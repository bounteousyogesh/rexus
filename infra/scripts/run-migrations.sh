#!/usr/bin/env bash
###############################################################################
# run-migrations.sh — Run all 5 REX-US database migrations in order
#
# Usage:
#   ./infra/scripts/run-migrations.sh [OPTIONS]
#
# Options:
#   --host     <host>     RDS hostname (overrides env var / Secrets Manager)
#   --port     <port>     PostgreSQL port (default: 5432)
#   --dbname   <dbname>   Database name (default: rexus)
#   --username <user>     Database user (default: rexus)
#   --dry-run             Print migration files without executing
#
# The script resolves credentials in this order:
#   1. Explicit CLI flags
#   2. PGHOST / PGPASSWORD / PGDATABASE / PGUSER environment variables
#   3. DATABASE_URL environment variable (postgresql://user:pass@host/db)
#   4. AWS Secrets Manager secret "rexus/dev/db-password"
#
# This script must be run from a machine that has network access to the RDS
# instance (e.g., a bastion host, an ECS Exec session, or a VPN-connected machine).
#
# ECS Exec example:
#   # First get a running task ARN:
#   TASK=$(aws ecs list-tasks --cluster rexus-dev-cluster \
#            --service-name rexus-dev-backend --query 'taskArns[0]' --output text)
#   # Then exec into it and download + run this script:
#   aws ecs execute-command --cluster rexus-dev-cluster --task "$TASK" \
#     --container backend --interactive --command /bin/bash
###############################################################################

set -euo pipefail

# ── Defaults ───────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MIGRATIONS_DIR="${REPO_ROOT}/backend/migrations"
AWS_REGION="${AWS_REGION:-us-east-1}"
PROJECT="${PROJECT:-rexus}"
ENVIRONMENT="${ENVIRONMENT:-dev}"

PG_HOST="${PGHOST:-}"
PG_PORT="${PGPORT:-5432}"
PG_DB="${PGDATABASE:-rexus}"
PG_USER="${PGUSER:-rexus}"
PG_PASSWORD="${PGPASSWORD:-}"
DRY_RUN=false

# Ordered list of migration files
MIGRATIONS=(
  "001_rexus_schema.sql"
  "002_enriched_schema.sql"
  "003_token_usage.sql"
  "005_auth.sql"
  "006_create_v3_table.sql"
  "004_indexes_and_extensions.sql"
  "007_kb_article_incident_mapping.sql"
)

# ── Parse CLI arguments ────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)     PG_HOST="$2";     shift 2 ;;
    --port)     PG_PORT="$2";     shift 2 ;;
    --dbname)   PG_DB="$2";       shift 2 ;;
    --username) PG_USER="$2";     shift 2 ;;
    --password) PG_PASSWORD="$2"; shift 2 ;;
    --dry-run)  DRY_RUN=true;     shift   ;;
    *)
      echo "[error] Unknown option: $1"
      echo "Usage: $0 [--host H] [--port P] [--dbname D] [--username U] [--password PW] [--dry-run]"
      exit 1
      ;;
  esac
done

# ── Resolve credentials ────────────────────────────────────────────────────────

resolve_from_database_url() {
  # Parse postgresql[+asyncpg]://user:password@host:port/dbname
  local url="${DATABASE_URL:-}"
  if [[ -z "$url" ]]; then return 1; fi

  # Strip scheme
  url="${url#postgresql+asyncpg://}"
  url="${url#postgresql://}"
  url="${url#postgres://}"

  # user:pass@host:port/db
  local userpass="${url%%@*}"
  local hostdb="${url#*@}"

  PG_USER="${userpass%%:*}"
  PG_PASSWORD="${userpass#*:}"

  local hostport="${hostdb%%/*}"
  PG_DB="${hostdb#*/}"
  # Strip query params
  PG_DB="${PG_DB%%\?*}"

  PG_HOST="${hostport%%:*}"
  local port="${hostport#*:}"
  if [[ "$port" != "$hostport" ]]; then
    PG_PORT="$port"
  fi

  echo "[info] Credentials resolved from DATABASE_URL"
  return 0
}

resolve_from_secrets_manager() {
  if ! command -v aws &>/dev/null; then return 1; fi

  echo "[info] Fetching credentials from Secrets Manager (${PROJECT}/${ENVIRONMENT}/db-password)..."
  local secret
  secret="$(aws secretsmanager get-secret-value \
    --secret-id "${PROJECT}/${ENVIRONMENT}/db-password" \
    --region "${AWS_REGION}" \
    --query SecretString \
    --output text 2>/dev/null)" || return 1

  PG_HOST="$(echo "$secret" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['host'])")"
  PG_USER="$(echo "$secret" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['username'])")"
  PG_PASSWORD="$(echo "$secret" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['password'])")"
  PG_DB="$(echo "$secret" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['dbname'])")"
  echo "[info] Credentials resolved from Secrets Manager"
  return 0
}

# Fallback chain
if [[ -z "$PG_HOST" ]]; then
  if [[ -n "${DATABASE_URL:-}" ]]; then
    resolve_from_database_url || true
  fi
  if [[ -z "$PG_HOST" ]]; then
    resolve_from_secrets_manager || true
  fi
fi

# ── Validate we have everything ────────────────────────────────────────────────

if [[ -z "$PG_HOST" ]]; then
  echo "[error] Cannot determine database host."
  echo "  Provide --host, set PGHOST, set DATABASE_URL, or ensure AWS credentials are available."
  exit 1
fi

if [[ -z "$PG_PASSWORD" ]]; then
  echo "[error] Cannot determine database password."
  echo "  Provide --password, set PGPASSWORD, set DATABASE_URL, or ensure AWS credentials are available."
  exit 1
fi

# Validate psql is available
if ! command -v psql &>/dev/null; then
  echo "[error] psql is not installed. Install postgresql-client to run migrations."
  echo "  Ubuntu/Debian: apt-get install -y postgresql-client"
  echo "  Alpine:        apk add postgresql-client"
  echo "  macOS:         brew install postgresql"
  exit 1
fi

# ── Print plan ─────────────────────────────────────────────────────────────────

echo ""
echo "============================================================"
echo " REX-US Database Migrations"
echo "============================================================"
echo " Host     : ${PG_HOST}"
echo " Port     : ${PG_PORT}"
echo " Database : ${PG_DB}"
echo " User     : ${PG_USER}"
echo " Dry Run  : ${DRY_RUN}"
echo "============================================================"
echo ""

# Verify each migration file exists before starting
echo "[check] Verifying migration files in: ${MIGRATIONS_DIR}"
for migration in "${MIGRATIONS[@]}"; do
  filepath="${MIGRATIONS_DIR}/${migration}"
  if [[ ! -f "$filepath" ]]; then
    echo "[error] Migration file not found: ${filepath}"
    exit 1
  fi
  echo "  [ok] ${migration}"
done
echo ""

# ── Run migrations ─────────────────────────────────────────────────────────────

export PGPASSWORD="${PG_PASSWORD}"

run_psql() {
  local file="$1"
  psql \
    --host="${PG_HOST}" \
    --port="${PG_PORT}" \
    --username="${PG_USER}" \
    --dbname="${PG_DB}" \
    --variable=ON_ERROR_STOP=1 \
    --single-transaction \
    --file="$file"
}

for i in "${!MIGRATIONS[@]}"; do
  migration="${MIGRATIONS[$i]}"
  filepath="${MIGRATIONS_DIR}/${migration}"
  step=$((i + 1))
  total="${#MIGRATIONS[@]}"

  echo "[${step}/${total}] Running migration: ${migration}"

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "--- DRY RUN: would execute ---"
    head -5 "$filepath"
    echo "..."
    echo "--- end ---"
  else
    run_psql "$filepath"
    echo "[ok] ${migration} applied successfully"
  fi
  echo ""
done

# ── Post-migration validation ──────────────────────────────────────────────────

if [[ "$DRY_RUN" != "true" ]]; then
  echo "[validate] Checking key tables exist..."
  tables=$(psql \
    --host="${PG_HOST}" \
    --port="${PG_PORT}" \
    --username="${PG_USER}" \
    --dbname="${PG_DB}" \
    --tuples-only \
    --command="SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;" \
    2>/dev/null)

  echo "$tables"

  echo ""
  echo "[validate] Checking pgvector extension..."
  psql \
    --host="${PG_HOST}" \
    --port="${PG_PORT}" \
    --username="${PG_USER}" \
    --dbname="${PG_DB}" \
    --command="SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector','pg_trgm');" \
    2>/dev/null

  echo ""
  echo "============================================================"
  echo " All ${#MIGRATIONS[@]} migrations applied successfully."
  echo "============================================================"
fi

unset PGPASSWORD
