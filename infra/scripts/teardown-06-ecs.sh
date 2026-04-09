#!/bin/bash
# Teardown Step 6: ECS services, tasks, IAM roles
# Run this FIRST — stops all running containers
set -euo pipefail
cd "$(dirname "$0")/../terraform/06-ecs"
echo "Destroying ECS services, tasks, and IAM roles..."
terraform init -input=false > /dev/null 2>&1 || true
terraform destroy -auto-approve
echo "✓ Step 6 (ECS) destroyed"
