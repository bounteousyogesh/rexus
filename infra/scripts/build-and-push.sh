#!/usr/bin/env bash
###############################################################################
# build-and-push.sh — Build Docker images and push to ECR
#
# Usage (from repo root):
#   ./infra/scripts/build-and-push.sh [IMAGE_TAG]
#
# If IMAGE_TAG is not provided, defaults to "latest".
# Reads AWS credentials from environment or .env file.
#
# Examples:
#   ./infra/scripts/build-and-push.sh
#   ./infra/scripts/build-and-push.sh v1.2.3
#   IMAGE_TAG=$(git rev-parse --short HEAD) ./infra/scripts/build-and-push.sh "$IMAGE_TAG"
###############################################################################

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Load .env if present (provides AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
if [[ -f "${REPO_ROOT}/.env" ]]; then
  echo "[info] Loading credentials from ${REPO_ROOT}/.env"
  set -a
  # shellcheck disable=SC1090
  source "${REPO_ROOT}/.env"
  set +a
fi

IMAGE_TAG="${1:-latest}"
AWS_REGION="${AWS_REGION:-us-east-1}"
PROJECT="${PROJECT:-rexus}"
ENVIRONMENT="${ENVIRONMENT:-dev}"

# ── Validate prerequisites ─────────────────────────────────────────────────────

for cmd in aws docker; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "[error] Required command not found: $cmd"
    exit 1
  fi
done

if [[ -z "${AWS_ACCESS_KEY_ID:-}" ]]; then
  echo "[error] AWS_ACCESS_KEY_ID is not set. Ensure it is in .env or your environment."
  exit 1
fi

# ── Derive ECR registry URL ────────────────────────────────────────────────────

AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
BACKEND_REPO="${ECR_REGISTRY}/${PROJECT}-${ENVIRONMENT}-backend"
FRONTEND_REPO="${ECR_REGISTRY}/${PROJECT}-${ENVIRONMENT}-frontend"

echo ""
echo "============================================================"
echo " REX-US Build & Push"
echo "============================================================"
echo " AWS Account : ${AWS_ACCOUNT_ID}"
echo " Region      : ${AWS_REGION}"
echo " Image Tag   : ${IMAGE_TAG}"
echo " Backend ECR : ${BACKEND_REPO}"
echo " Frontend ECR: ${FRONTEND_REPO}"
echo "============================================================"
echo ""

# ── ECR Login ─────────────────────────────────────────────────────────────────

echo "[step 1/5] Authenticating with ECR..."
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR_REGISTRY}"
echo "[ok] ECR login successful"

# ── Build Backend ──────────────────────────────────────────────────────────────

echo ""
echo "[step 2/5] Building backend image..."
cd "${REPO_ROOT}"

docker build \
  --file infra/docker/Dockerfile.backend \
  --tag "${BACKEND_REPO}:${IMAGE_TAG}" \
  --tag "${BACKEND_REPO}:latest" \
  --label "git.commit=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)" \
  --label "git.branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)" \
  --label "build.date=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --progress=plain \
  .

echo "[ok] Backend image built: ${BACKEND_REPO}:${IMAGE_TAG}"

# ── Push Backend ───────────────────────────────────────────────────────────────

echo ""
echo "[step 3/5] Pushing backend image to ECR..."
docker push "${BACKEND_REPO}:${IMAGE_TAG}"
docker push "${BACKEND_REPO}:latest"
echo "[ok] Backend pushed successfully"

# ── Build Frontend ─────────────────────────────────────────────────────────────

echo ""
echo "[step 4/5] Building frontend image..."

docker build \
  --file infra/docker/Dockerfile.frontend \
  --tag "${FRONTEND_REPO}:${IMAGE_TAG}" \
  --tag "${FRONTEND_REPO}:latest" \
  --label "git.commit=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)" \
  --label "git.branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)" \
  --label "build.date=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --progress=plain \
  .

echo "[ok] Frontend image built: ${FRONTEND_REPO}:${IMAGE_TAG}"

# ── Push Frontend ──────────────────────────────────────────────────────────────

echo ""
echo "[step 5/5] Pushing frontend image to ECR..."
docker push "${FRONTEND_REPO}:${IMAGE_TAG}"
docker push "${FRONTEND_REPO}:latest"
echo "[ok] Frontend pushed successfully"

# ── Summary ────────────────────────────────────────────────────────────────────

echo ""
echo "============================================================"
echo " Build & Push Complete"
echo "============================================================"
echo " Backend  : ${BACKEND_REPO}:${IMAGE_TAG}"
echo " Frontend : ${FRONTEND_REPO}:${IMAGE_TAG}"
echo ""
echo " Next step — redeploy ECS services with the new image tag:"
echo ""
echo "   cd infra/terraform/06-ecs"
echo "   terraform apply -var='backend_image_tag=${IMAGE_TAG}' -var='frontend_image_tag=${IMAGE_TAG}'"
echo ""
echo " Or force a rolling update without changing the tag (when tag=latest):"
echo ""
echo "   aws ecs update-service \\"
echo "     --cluster ${PROJECT}-${ENVIRONMENT}-cluster \\"
echo "     --service ${PROJECT}-${ENVIRONMENT}-backend \\"
echo "     --force-new-deployment \\"
echo "     --region ${AWS_REGION}"
echo ""
echo "   aws ecs update-service \\"
echo "     --cluster ${PROJECT}-${ENVIRONMENT}-cluster \\"
echo "     --service ${PROJECT}-${ENVIRONMENT}-frontend \\"
echo "     --force-new-deployment \\"
echo "     --region ${AWS_REGION}"
echo "============================================================"
