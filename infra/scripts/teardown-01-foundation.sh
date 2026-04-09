#!/bin/bash
# Teardown Step 1: VPC, subnets, gateways, security groups
# Run this LAST — other resources depend on the VPC
set -euo pipefail
cd "$(dirname "$0")/../terraform/01-foundation"
echo "Destroying VPC, subnets, NAT gateway, and security groups..."
terraform init -input=false > /dev/null 2>&1 || true
terraform destroy -auto-approve
echo "✓ Step 1 (Foundation) destroyed"
echo ""
echo "All REX-US AWS resources have been removed."
