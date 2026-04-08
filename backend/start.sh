#!/bin/sh
set -e
 
echo "Fetching secrets from AWS Secrets Manager..."
 
# Required inputs
SECRET_NAME=${SECRET_NAME:dt-app-secrets}
AWS_REGION=${AWS_REGION:us-east-1}
 
# Fetch secret JSON
SECRET_JSON=$(aws secretsmanager get-secret-value \
  --region $AWS_REGION \
  --secret-id $SECRET_NAME \
  --query SecretString \
  --output text)
 
# Export environment variables
export DATABASE_URL=$(echo $SECRET_JSON | jq -r .DATABASE_URL)
export SERVICENOW_INSTANCE=$(echo $SECRET_JSON | jq -r .SERVICENOW_INSTANCE)
export SERVICENOW_CLIENT_ID=$(echo $SECRET_JSON | jq -r .SERVICENOW_CLIENT_ID)
export SERVICENOW_CLIENT_SECRET=$(echo $SECRET_JSON | jq -r .SERVICENOW_CLIENT_SECRET)
 
# Validate
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${SERVICENOW_INSTANCE:?SERVICENOW_INSTANCE is required}"
: "${SERVICENOW_CLIENT_ID:?SERVICENOW_CLIENT_ID is required}"
: "${SERVICENOW_CLIENT_SECRET:?SERVICENOW_CLIENT_SECRET is required}"
 
echo "Secrets loaded successfully."
 
# --- Start backend ---
echo "Starting backend..."
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 &