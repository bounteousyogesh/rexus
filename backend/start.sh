#!/bin/bash
set -e

echo "Fetching secrets from AWS Secrets Manager..."

# Required inputs — use :- for proper default value syntax
SECRET_NAME=${SECRET_NAME:-dt-app-secrets}
AWS_REGION=${AWS_REGION:-us-east-1}

# Fetch secret JSON
SECRET_JSON=$(aws secretsmanager get-secret-value \
  --region "$AWS_REGION" \
  --secret-id "$SECRET_NAME" \
  --query SecretString \
  --output text) || { echo "ERROR: Failed to fetch secrets from AWS Secrets Manager"; exit 1; }

# Export environment variables
export DATABASE_URL=$(echo "$SECRET_JSON" | jq -r .DATABASE_URL)
export SERVICENOW_INSTANCE=$(echo "$SECRET_JSON" | jq -r .SERVICENOW_INSTANCE)
export SERVICENOW_CLIENT_ID=$(echo "$SECRET_JSON" | jq -r .SERVICENOW_CLIENT_ID)
export SERVICENOW_CLIENT_SECRET=$(echo "$SECRET_JSON" | jq -r .SERVICENOW_CLIENT_SECRET)

# Validate
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${SERVICENOW_INSTANCE:?SERVICENOW_INSTANCE is required}"
: "${SERVICENOW_CLIENT_ID:?SERVICENOW_CLIENT_ID is required}"
: "${SERVICENOW_CLIENT_SECRET:?SERVICENOW_CLIENT_SECRET is required}"

echo "Secrets loaded successfully."

# --- Run SQL migrations ---
echo "Running SQL migrations..."
MIGRATIONS_DIR="$(dirname "$0")/migrations"
if [ -d "$MIGRATIONS_DIR" ]; then
    for sql_file in $(ls "$MIGRATIONS_DIR"/*.sql | sort); do
        echo "  Applying: $(basename $sql_file)"
        psql "$DATABASE_URL" -f "$sql_file" -v ON_ERROR_STOP=0 2>&1 | grep -v "^$" || true
    done
    echo "Migrations complete."
else
    echo "WARNING: Migrations directory not found at $MIGRATIONS_DIR"
fi

# --- Start backend ---
echo "Starting backend..."
# Run in foreground so Docker tracks the process (no & — container would exit immediately otherwise)
exec uvicorn api.main:app --host 0.0.0.0 --port 8000