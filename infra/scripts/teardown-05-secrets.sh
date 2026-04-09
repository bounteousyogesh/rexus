#!/bin/bash
# Teardown Step 5: Secrets Manager entries + SSM parameters
set -euo pipefail
cd "$(dirname "$0")/../terraform/05-secrets"
echo "Destroying Secrets Manager entries and config parameters..."
terraform init -input=false > /dev/null 2>&1 || true
terraform destroy -auto-approve
echo "✓ Step 5 (Secrets) destroyed"
