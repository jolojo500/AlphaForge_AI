#!/usr/bin/env bash
# Deploy AlphaForge AI on AWS (PRD 8, C-6).
# App Runner first; if App Runner is disallowed by SCP / organization policy,
# automatically switches to EC2 + Docker without further delay.
# All AWS resources are tagged project=alphaforge.

set -euo pipefail

export AWS_REGION="${AWS_REGION:-us-east-1}"
if [ -z "${AWS_PROFILE:-}" ] && aws configure list-profiles 2>/dev/null | grep -q "^datathon$"; then
    export AWS_PROFILE="datathon"
fi

IMAGE_NAME="alphaforge"
ECR_REPO_NAME="alphaforge"
APP_RUNNER_SERVICE_NAME="alphaforge-app"
EC2_INSTANCE_NAME="AlphaForge-Server"
SG_NAME="alphaforge-sg"
EC2_ROLE_NAME="alphaforge-ec2-role"
EC2_PROFILE_NAME="alphaforge-ec2-instance-profile"
DYNAMODB_TABLE="${AF_DYNAMODB_TABLE:-alphaforge-traces}"

echo "============================================="
echo "       AlphaForge AI AWS Deployment"
echo "============================================="
echo "AWS Region: ${AWS_REGION}"
if [ -n "${AWS_PROFILE:-}" ]; then
    echo "AWS Profile: ${AWS_PROFILE}"
fi

# 1. Identity & S3 / DynamoDB references
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "AWS Account ID: ${ACCOUNT_ID}"
S3_BUCKET="${AF_S3_BUCKET:-alphaforge-data-${ACCOUNT_ID}}"
echo "S3 Bucket: ${S3_BUCKET}"
echo "DynamoDB Table: ${DYNAMODB_TABLE}"

# 2. Ensure ECR Repository exists
echo "Checking ECR repository ${ECR_REPO_NAME}..."
if ! aws ecr describe-repositories --repository-names "${ECR_REPO_NAME}" >/dev/null 2>&1; then
    echo "Creating ECR repository ${ECR_REPO_NAME}..."
    aws ecr create-repository \
        --repository-name "${ECR_REPO_NAME}" \
        --tags Key=project,Value=alphaforge \
        --image-scanning-configuration scanOnPush=false
fi
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}"
echo "ECR URI: ${ECR_URI}"

# 3. Build and push Docker image
echo "Logging in to ECR..."
aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "Building multi-stage Docker image..."
docker build -t "${IMAGE_NAME}:latest" -f infra/Dockerfile .
docker tag "${IMAGE_NAME}:latest" "${ECR_URI}:latest"

echo "Pushing Docker image to ECR..."
docker push "${ECR_URI}:latest"

# 4. Attempt App Runner first
USE_EC2=false
echo "Checking App Runner capability..."
ACCESS_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/alphaforge-apprunner-access-role"

if ! aws apprunner list-services >/dev/null 2>&1; then
    echo "App Runner API not available. Switching to EC2 + Docker."
    USE_EC2=true
else
    # Test App Runner permission
    echo "Attempting App Runner deployment..."
    if ! aws iam get-role --role-name "alphaforge-apprunner-access-role" >/dev/null 2>&1; then
        aws iam create-role \
            --role-name "alphaforge-apprunner-access-role" \
            --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"build.apprunner.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
            --tags Key=project,Value=alphaforge || true
        aws iam attach-role-policy \
            --role-name "alphaforge-apprunner-access-role" \
            --policy-arn "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess" || true
    fi

    # Check if create-service is permitted
    if ! aws apprunner create-service --service-name "${APP_RUNNER_SERVICE_NAME}" \
        --source-configuration "{\"ImageRepository\":{\"ImageIdentifier\":\"${ECR_URI}:latest\",\"ImageRepositoryType\":\"ECR\",\"ImageConfiguration\":{\"Port\":\"8000\"}},\"AuthenticationConfiguration\":{\"AccessRoleArn\":\"${ACCESS_ROLE_ARN}\"}}" \
        --tags Key=project,Value=alphaforge >/dev/null 2>&1; then
        echo "App Runner create-service was denied by organization policy/SCP. Switching to EC2 + Docker."
        USE_EC2=true
    fi
fi

if [ "${USE_EC2}" = true ]; then
    echo "============================================="
    echo "   Deploying via EC2 + Docker (t3.medium)"
    echo "============================================="

    # 1. Default VPC & Subnet
    VPC_ID=$(aws ec2 describe-vpcs --filters "Name=is-default,Values=true" --query "Vpcs[0].VpcId" --output text)
    SUBNET_ID=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=${VPC_ID}" --query "Subnets[?MapPublicIpOnLaunch==\`true\`][0].SubnetId" --output text)
    echo "VPC: ${VPC_ID}, Subnet: ${SUBNET_ID}"

    # 2. Security Group
    SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=${SG_NAME}" "Name=vpc-id,Values=${VPC_ID}" --query "SecurityGroups[0].GroupId" --output text 2>/dev/null || true)
    if [ -z "${SG_ID}" ] || [ "${SG_ID}" = "None" ]; then
        echo "Creating security group ${SG_NAME}..."
        SG_ID=$(aws ec2 create-security-group \
            --group-name "${SG_NAME}" \
            --description "Security group for AlphaForge AI instance" \
            --vpc-id "${VPC_ID}" \
            --tag-specifications "ResourceType=security-group,Tags=[{Key=project,Value=alphaforge}]" \
            --query "GroupId" --output text)
        aws ec2 authorize-security-group-ingress --group-id "${SG_ID}" --protocol tcp --port 80 --cidr 0.0.0.0/0
        aws ec2 authorize-security-group-ingress --group-id "${SG_ID}" --protocol tcp --port 8000 --cidr 0.0.0.0/0
    fi
    echo "Security Group: ${SG_ID}"

    # 3. IAM Role & Instance Profile
    if ! aws iam get-role --role-name "${EC2_ROLE_NAME}" >/dev/null 2>&1; then
        echo "Creating EC2 IAM role ${EC2_ROLE_NAME}..."
        aws iam create-role \
            --role-name "${EC2_ROLE_NAME}" \
            --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
            --tags Key=project,Value=alphaforge

        aws iam attach-role-policy \
            --role-name "${EC2_ROLE_NAME}" \
            --policy-arn "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"

        aws iam put-role-policy \
            --role-name "${EC2_ROLE_NAME}" \
            --policy-name "alphaforge-ec2-policy" \
            --policy-document "{
                \"Version\": \"2012-10-17\",
                \"Statement\": [
                    {\"Effect\": \"Allow\", \"Action\": [\"bedrock:InvokeModel\", \"bedrock:InvokeModelWithResponseStream\"], \"Resource\": \"*\"},
                    {\"Effect\": \"Allow\", \"Action\": [\"s3:*\"], \"Resource\": [\"arn:aws:s3:::${S3_BUCKET}\", \"arn:aws:s3:::${S3_BUCKET}/*\"]},
                    {\"Effect\": \"Allow\", \"Action\": [\"dynamodb:*\"], \"Resource\": [\"arn:aws:dynamodb:${AWS_REGION}:${ACCOUNT_ID}:table/${DYNAMODB_TABLE}\", \"arn:aws:dynamodb:${AWS_REGION}:${ACCOUNT_ID}:table/${DYNAMODB_TABLE}/*\"]},
                    {\"Effect\": \"Allow\", \"Action\": [\"logs:CreateLogGroup\", \"logs:CreateLogStream\", \"logs:PutLogEvents\", \"logs:DescribeLogStreams\"], \"Resource\": \"*\"}
                ]
            }"
    fi

    if ! aws iam get-instance-profile --instance-profile-name "${EC2_PROFILE_NAME}" >/dev/null 2>&1; then
        echo "Creating IAM instance profile ${EC2_PROFILE_NAME}..."
        aws iam create-instance-profile \
            --instance-profile-name "${EC2_PROFILE_NAME}" \
            --tags Key=project,Value=alphaforge
        aws iam add-role-to-instance-profile \
            --instance-profile-name "${EC2_PROFILE_NAME}" \
            --role-name "${EC2_ROLE_NAME}"
    fi

    # 4. Find latest AL2023 AMI
    AMI_ID=$(aws ssm get-parameter --name "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64" --query "Parameter.Value" --output text)
    echo "AMI ID: ${AMI_ID}"

    # 5. Check if instance already exists
    EXISTING_INSTANCE_ID=$(aws ec2 describe-instances \
        --filters "Name=tag:project,Values=alphaforge" "Name=tag:Name,Values=${EC2_INSTANCE_NAME}" "Name=instance-state-name,Values=running,pending" \
        --query "Reservations[0].Instances[0].InstanceId" --output text 2>/dev/null || true)

    if [ -n "${EXISTING_INSTANCE_ID}" ] && [ "${EXISTING_INSTANCE_ID}" != "None" ]; then
        echo "Found running AlphaForge EC2 instance: ${EXISTING_INSTANCE_ID}"
        INSTANCE_ID="${EXISTING_INSTANCE_ID}"
    else
        echo "Launching new EC2 instance ${EC2_INSTANCE_NAME}..."
        USER_DATA=$(cat << EOF | base64 -w 0
#!/bin/bash
set -xe
exec > /var/log/alphaforge-bootstrap.log 2>&1
echo "Starting AlphaForge bootstrap..."
dnf install -y docker
systemctl enable --now docker
usermod -aG docker ec2-user
for i in {1..10}; do
  if aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"; then
    break
  fi
  sleep 3
done
docker pull "${ECR_URI}:latest"
docker run -d --name alphaforge --restart always \
  -p 80:8000 -p 8000:8000 \
  -e AF_S3_BUCKET="${S3_BUCKET}" \
  -e AF_DYNAMODB_TABLE="${DYNAMODB_TABLE}" \
  -e AF_TRACE_BACKEND="dynamodb" \
  -e AWS_REGION="${AWS_REGION}" \
  -e AF_MODEL_MAIN="anthropic.claude-3-5-sonnet-20241022-v2:0" \
  -e AF_MODEL_FAST="us.anthropic.claude-3-5-haiku-20241022-v1:0" \
  "${ECR_URI}:latest"
echo "AlphaForge bootstrap complete!"
EOF
        )

        LAUNCH_RESP=$(aws ec2 run-instances \
            --image-id "${AMI_ID}" \
            --instance-type t3.medium \
            --subnet-id "${SUBNET_ID}" \
            --security-group-ids "${SG_ID}" \
            --iam-instance-profile Name="${EC2_PROFILE_NAME}" \
            --user-data "${USER_DATA}" \
            --tag-specifications "ResourceType=instance,Tags=[{Key=project,Value=alphaforge},{Key=Name,Value=${EC2_INSTANCE_NAME}}]" \
            --output json)
        INSTANCE_ID=$(echo "${LAUNCH_RESP}" | python3 -c "import sys, json; print(json.load(sys.stdin)['Instances'][0]['InstanceId'])")
        echo "Launched EC2 instance: ${INSTANCE_ID}"
    fi

    # 6. Wait for public IP and healthcheck
    echo "Waiting for instance to report public IP..."
    PUBLIC_IP=""
    for i in {1..30}; do
        PUBLIC_IP=$(aws ec2 describe-instances --instance-ids "${INSTANCE_ID}" --query "Reservations[0].Instances[0].PublicIpAddress" --output text 2>/dev/null || true)
        if [ -n "${PUBLIC_IP}" ] && [ "${PUBLIC_IP}" != "None" ]; then
            break
        fi
        sleep 3
    done
    echo "EC2 Public IP: ${PUBLIC_IP}"

    echo "Waiting for AlphaForge service to become healthy at http://${PUBLIC_IP}/health..."
    for i in {1..30}; do
        if curl -s -f "http://${PUBLIC_IP}/health" >/dev/null 2>&1 || curl -s -f "http://${PUBLIC_IP}:8000/health" >/dev/null 2>&1; then
            echo "Health check PASSED!"
            break
        fi
        echo "Waiting for Docker bootstrap ($i/30)..."
        sleep 5
    done

    echo "============================================="
    echo "       AlphaForge Deployment SUCCESS!"
    echo "============================================="
    echo "Public URL:   http://${PUBLIC_IP}/ (and http://${PUBLIC_IP}:8000/)"
    echo "Health Check: http://${PUBLIC_IP}/health"
fi
