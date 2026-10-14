#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="${SCRIPT_DIR}/../service"
REGION="${AWS_REGION:-}"
SERVICE_NAME="${ECS_SERVICE_NAME:-ginani-visionfit-api}"
REPOSITORY="${ECR_REPOSITORY:-ginani-visionfit-api}"
EXECUTION_ROLE="${ECS_EXECUTION_ROLE_ARN:-}"
INFRASTRUCTURE_ROLE="${ECS_INFRASTRUCTURE_ROLE_ARN:-}"
CORS_ORIGINS="${VISIONFIT_CORS_ORIGINS:-http://localhost:5173}"

for tool in aws docker python3; do
  command -v "$tool" >/dev/null || { echo "Required command not found: $tool" >&2; exit 1; }
done
[[ -n "$REGION" ]] || { echo "Set AWS_REGION to the AWS region for your grant." >&2; exit 1; }
[[ -n "$EXECUTION_ROLE" ]] || { echo "Set ECS_EXECUTION_ROLE_ARN to the ecsTaskExecutionRole ARN." >&2; exit 1; }
[[ -n "$INFRASTRUCTURE_ROLE" ]] || { echo "Set ECS_INFRASTRUCTURE_ROLE_ARN to the ecsInfrastructureRoleForExpressServices ARN." >&2; exit 1; }

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
IMAGE_TAG="${VISIONFIT_IMAGE_TAG:-$(date -u +%Y%m%d-%H%M%S)}"
IMAGE="${REGISTRY}/${REPOSITORY}:${IMAGE_TAG}"

if ! aws ecr describe-repositories --repository-names "$REPOSITORY" --region "$REGION" >/dev/null 2>&1; then
  aws ecr create-repository --repository-name "$REPOSITORY" \
    --image-scanning-configuration scanOnPush=true --region "$REGION" >/dev/null
fi

aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$REGISTRY"
docker build --platform linux/amd64 -t "$IMAGE" "$SERVICE_DIR"
docker push "$IMAGE"

export IMAGE CORS_ORIGINS
CONTAINER_JSON="$(python3 -c 'import json,os; print(json.dumps({"image":os.environ["IMAGE"],"containerPort":8080,"environment":[{"name":"VISIONFIT_CORS_ORIGINS","value":os.environ["CORS_ORIGINS"]}]}))')"

aws ecs create-express-gateway-service \
  --service-name "$SERVICE_NAME" \
  --execution-role-arn "$EXECUTION_ROLE" \
  --infrastructure-role-arn "$INFRASTRUCTURE_ROLE" \
  --primary-container "$CONTAINER_JSON" \
  --health-check-path /api/health \
  --cpu 1024 \
  --memory 2048 \
  --scaling-target '{"minTaskCount":1,"maxTaskCount":1}' \
  --monitor-resources DEPLOYMENT \
  --region "$REGION"

echo "Deployment request submitted. Check the Amazon ECS console for the service URL and status."
