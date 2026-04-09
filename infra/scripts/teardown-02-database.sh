#!/bin/bash
# Teardown Step 2: RDS PostgreSQL database
# WARNING: ALL DATA WILL BE PERMANENTLY LOST
set -euo pipefail
cd "$(dirname "$0")/../terraform/02-database"
echo ""
echo "⚠️  WARNING: This will DELETE the RDS database."
echo "   All incident data, embeddings, analysis logs will be PERMANENTLY LOST."
echo ""
read -p "Type 'DELETE-DATABASE' to confirm: " confirm
if [[ "$confirm" != "DELETE-DATABASE" ]]; then
    echo "Aborted."
    exit 1
fi
terraform init -input=false > /dev/null 2>&1 || true
terraform destroy -auto-approve
echo "✓ Step 2 (Database) destroyed"
