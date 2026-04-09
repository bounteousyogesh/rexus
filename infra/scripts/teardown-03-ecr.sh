#!/bin/bash
# Teardown Step 3: ECR repositories and all Docker images
# WARNING: This deletes all pushed Docker images permanently
set -euo pipefail
cd "$(dirname "$0")/../terraform/03-ecr"
echo "Destroying ECR repositories (all images will be deleted)..."
terraform init -input=false > /dev/null 2>&1 || true
terraform destroy -auto-approve
echo "✓ Step 3 (ECR) destroyed"
