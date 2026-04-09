#!/bin/bash
# Teardown Step 4: ALB, target groups, listeners
set -euo pipefail
cd "$(dirname "$0")/../terraform/04-alb"
echo "Destroying ALB, target groups, and listeners..."
terraform init -input=false > /dev/null 2>&1 || true
terraform destroy -auto-approve
echo "✓ Step 4 (ALB) destroyed"
