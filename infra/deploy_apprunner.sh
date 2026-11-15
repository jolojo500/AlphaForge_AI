#!/usr/bin/env bash
# Build the image, push it to ECR and create or update the App Runner service.
# Needs: docker, aws CLI with working credentials (env vars or AWS_PROFILE). No secrets are
# written anywhere. Run from the repository root:  infra/deploy_apprunner.sh
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
NAME="${AF_SERVICE_NAME:-alphaforge}"
TABLE="${AF_TRACE_TABLE:-alphaforge-traces}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
REPO="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$NAME"
TAG="${AF_IMAGE_TAG:-$(git rev-parse --short HEAD)}"
INSTANCE_ROLE="${NAME}-instance"
ACCESS_ROLE="${NAME}-ecr-access"

echo "==> DynamoDB table $TABLE"
aws dynamodb describe-table --table-name "$TABLE" --region "$REGION" >/dev/null 2>&1 ||
  aws dynamodb create-table --table-name "$TABLE" --region "$REGION" \
    --attribute-definitions AttributeName=run_id,AttributeType=S \
    --key-schema AttributeName=run_id,KeyType=HASH --billing-mode PAY_PER_REQUEST >/dev/null

echo "==> ECR repository $NAME"
aws ecr describe-repositories --repository-names "$NAME" --region "$REGION" >/dev/null 2>&1 ||
  aws ecr create-repository --repository-name "$NAME" --region "$REGION" >/dev/null

echo "==> Build and push $REPO:$TAG"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
docker build -f infra/Dockerfile -t "$REPO:$TAG" .
docker push "$REPO:$TAG"

role_arn() { aws iam get-role --role-name "$1" --query Role.Arn --output text 2>/dev/null; }

echo "==> IAM roles"
if ! INSTANCE_ARN="$(role_arn "$INSTANCE_ROLE")"; then
  INSTANCE_ARN="$(aws iam create-role --role-name "$INSTANCE_ROLE" --query Role.Arn --output text \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"tasks.apprunner.amazonaws.com"},"Action":"sts:AssumeRole"}]}')"
fi
aws iam put-role-policy --role-name "$INSTANCE_ROLE" --policy-name runtime --policy-document "file://infra/policy-runtime.json"
if ! ACCESS_ARN="$(role_arn "$ACCESS_ROLE")"; then
  ACCESS_ARN="$(aws iam create-role --role-name "$ACCESS_ROLE" --query Role.Arn --output text \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"build.apprunner.amazonaws.com"},"Action":"sts:AssumeRole"}]}')"
  aws iam attach-role-policy --role-name "$ACCESS_ROLE" --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess
  sleep 10  # let IAM propagate
fi

SOURCE="{\"ImageRepository\":{\"ImageIdentifier\":\"$REPO:$TAG\",\"ImageRepositoryType\":\"ECR\",\"ImageConfiguration\":{\"Port\":\"8080\",\"RuntimeEnvironmentVariables\":{\"AWS_REGION\":\"$REGION\",\"AF_TRACE_BACKEND\":\"dynamodb\",\"AF_TRACE_TABLE\":\"$TABLE\",\"AF_NEWS_MODE\":\"cache\"}}},\"AuthenticationConfiguration\":{\"AccessRoleArn\":\"$ACCESS_ARN\"},\"AutoDeploymentsEnabled\":false}"

echo "==> App Runner service $NAME"
SERVICE_ARN="$(aws apprunner list-services --region "$REGION" --query "ServiceSummaryList[?ServiceName=='$NAME'].ServiceArn | [0]" --output text)"
if [ "$SERVICE_ARN" = "None" ] || [ -z "$SERVICE_ARN" ]; then
  aws apprunner create-service --region "$REGION" --service-name "$NAME" --source-configuration "$SOURCE" \
    --instance-configuration "Cpu=1024,Memory=2048,InstanceRoleArn=$INSTANCE_ARN" \
    --health-check-configuration "Protocol=HTTP,Path=/health" --query Service.ServiceUrl --output text
else
  aws apprunner update-service --region "$REGION" --service-arn "$SERVICE_ARN" --source-configuration "$SOURCE" \
    --query Service.ServiceUrl --output text
fi
echo "Open https://<ServiceUrl above> once the service status is RUNNING (aws apprunner describe-service)."
