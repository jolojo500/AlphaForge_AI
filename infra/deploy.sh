#!/usr/bin/env bash
# Deploy or update AlphaForge AI on AWS (PRD §8, C-6).
# Usage:
#   ./infra/deploy.sh          # Full deployment / provision if not exists
#   ./infra/deploy.sh update   # Fast redeploy of latest code to existing instance via SSM
#
# All AWS resources are tagged project=alphaforge.

set -euo pipefail

ACTION="${1:-deploy}"
export AWS_REGION="${AWS_REGION:-us-east-1}"
if [ -z "${AWS_PROFILE:-}" ] && aws configure list-profiles 2>/dev/null | grep -q "^datathon$"; then
    export AWS_PROFILE="datathon"
fi

IMAGE_NAME="alphaforge"
ECR_REPO_NAME="alphaforge"
EC2_INSTANCE_NAME="AlphaForge-Server"
SG_NAME="alphaforge-sg"
EC2_ROLE_NAME="alphaforge-ec2-role"
EC2_PROFILE_NAME="alphaforge-ec2-instance-profile"
DYNAMODB_TABLE="${AF_DYNAMODB_TABLE:-alphaforge-traces}"

echo "============================================="
echo "       AlphaForge AI AWS Deployment"
echo "============================================="
echo "Action:      ${ACTION}"
echo "AWS Region:  ${AWS_REGION}"
if [ -n "${AWS_PROFILE:-}" ]; then
    echo "AWS Profile: ${AWS_PROFILE}"
fi

# 1. Identity & S3 / DynamoDB references
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "AWS Account: ${ACCOUNT_ID}"
S3_BUCKET="${AF_S3_BUCKET:-alphaforge-data-${ACCOUNT_ID}}"
echo "S3 Bucket:   ${S3_BUCKET}"
echo "Table:       ${DYNAMODB_TABLE}"
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}"

# Build and Push
build_and_push() {
    echo "--- 1. Ensuring ECR Repository ---"
    if ! aws ecr describe-repositories --repository-names "${ECR_REPO_NAME}" >/dev/null 2>&1; then
        echo "Creating ECR repository ${ECR_REPO_NAME}..."
        aws ecr create-repository \
            --repository-name "${ECR_REPO_NAME}" \
            --tags Key=project,Value=alphaforge \
            --image-scanning-configuration scanOnPush=false
    fi

    echo "--- 2. Building & Pushing Docker Image ---"
    echo "Logging in to ECR..."
    aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

    echo "Building multi-stage Docker image..."
    docker build -t "${IMAGE_NAME}:latest" -f infra/Dockerfile .
    docker tag "${IMAGE_NAME}:latest" "${ECR_URI}:latest"

    echo "Pushing Docker image to ${ECR_URI}:latest..."
    docker push "${ECR_URI}:latest"
}

# Fast redeploy via SSM
redeploy_via_ssm() {
    echo "--- Fast Redeploy to Existing Instance via SSM ---"
    INSTANCE_ID=$(aws ec2 describe-instances \
        --filters "Name=tag:project,Values=alphaforge" "Name=tag:Name,Values=${EC2_INSTANCE_NAME}" "Name=instance-state-name,Values=running" \
        --query "Reservations[0].Instances[0].InstanceId" --output text 2>/dev/null || true)

    if [ -z "${INSTANCE_ID}" ] || [ "${INSTANCE_ID}" = "None" ]; then
        echo "ERROR: No running instance named ${EC2_INSTANCE_NAME} found. Run full deploy first."
        exit 1
    fi
    echo "Target EC2 Instance: ${INSTANCE_ID}"

    PUBLIC_IP=$(aws ec2 describe-instances --instance-ids "${INSTANCE_ID}" --query "Reservations[0].Instances[0].PublicIpAddress" --output text)
    echo "Public IP: ${PUBLIC_IP}"

    echo "Sending update command to ${INSTANCE_ID} via SSM..."
    DOCKER_CMD="aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com && docker pull ${ECR_URI}:latest && docker rm -f alphaforge || true && docker run -d --name alphaforge --restart always -p 80:8000 --log-driver awslogs --log-opt awslogs-group=/alphaforge/app --log-opt awslogs-region=${AWS_REGION} --log-opt awslogs-create-group=true -e AF_S3_BUCKET=${S3_BUCKET} -e AF_DYNAMODB_TABLE=${DYNAMODB_TABLE} -e AF_TRACE_BACKEND=dynamodb -e AWS_REGION=${AWS_REGION} ${ECR_URI}:latest"

    CMD_ID=$(aws ssm send-command \
        --instance-ids "${INSTANCE_ID}" \
        --document-name "AWS-RunShellScript" \
        --parameters "commands=[\"${DOCKER_CMD}\"]" \
        --comment "AlphaForge redeploy" \
        --query "Command.CommandId" --output text)

    echo "SSM Command dispatched: ${CMD_ID}. Waiting for execution..."
    while true; do
        CMD_STATUS=$(aws ssm get-command-invocation \
            --command-id "${CMD_ID}" \
            --instance-id "${INSTANCE_ID}" \
            --query "Status" --output text 2>/dev/null || echo "Pending")
        echo "SSM Status: ${CMD_STATUS}"
        if [ "${CMD_STATUS}" = "Success" ]; then
            echo "SSM Command succeeded!"
            break
        elif [ "${CMD_STATUS}" = "Failed" ] || [ "${CMD_STATUS}" = "Cancelled" ] || [ "${CMD_STATUS}" = "TimedOut" ]; then
            echo "ERROR: SSM command failed with status ${CMD_STATUS}"
            aws ssm get-command-invocation --command-id "${CMD_ID}" --instance-id "${INSTANCE_ID}" --query "StandardErrorContent" --output text
            exit 1
        fi
        sleep 3
    done

    echo "Verifying /health on http://${PUBLIC_IP}/health..."
    for i in {1..15}; do
        if curl -s -f "http://${PUBLIC_IP}/health" >/dev/null 2>&1; then
            echo "Health check PASSED: http://${PUBLIC_IP}/health"
            break
        fi
        echo "Waiting for container startup ($i/15)..."
        sleep 2
    done

    echo "============================================="
    echo "       AlphaForge Redeployment SUCCESS!"
    echo "============================================="
    echo "Public URL:   http://${PUBLIC_IP}/"
    echo "Health Check: http://${PUBLIC_IP}/health"
}

# Full provisioning deploy
full_deploy() {
    build_and_push

    # Check if instance already exists and is running; if so, redeploy into it
    EXISTING_INSTANCE_ID=$(aws ec2 describe-instances \
        --filters "Name=tag:project,Values=alphaforge" "Name=tag:Name,Values=${EC2_INSTANCE_NAME}" "Name=instance-state-name,Values=running" \
        --query "Reservations[0].Instances[0].InstanceId" --output text 2>/dev/null || true)

    if [ -n "${EXISTING_INSTANCE_ID}" ] && [ "${EXISTING_INSTANCE_ID}" != "None" ]; then
        echo "Instance ${EXISTING_INSTANCE_ID} is already running. Performing redeploy..."
        redeploy_via_ssm
        return
    fi

    echo "--- 3. Provisioning EC2 Infrastructure ---"
    # VPC & Subnet
    VPC_ID=$(aws ec2 describe-vpcs --filters "Name=is-default,Values=true" --query "Vpcs[0].VpcId" --output text)
    SUBNET_ID=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=${VPC_ID}" --query "Subnets[?MapPublicIpOnLaunch==\`true\`][0].SubnetId" --output text)

    # Security Group (Port 80 only)
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
    fi

    # IAM Role & Instance Profile
    if ! aws iam get-role --role-name "${EC2_ROLE_NAME}" >/dev/null 2>&1; then
        echo "Creating EC2 IAM role ${EC2_ROLE_NAME}..."
        aws iam create-role \
            --role-name "${EC2_ROLE_NAME}" \
            --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
            --tags Key=project,Value=alphaforge
    fi

    aws iam attach-role-policy --role-name "${EC2_ROLE_NAME}" --policy-arn "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
    aws iam attach-role-policy --role-name "${EC2_ROLE_NAME}" --policy-arn "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"

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

    if ! aws iam get-instance-profile --instance-profile-name "${EC2_PROFILE_NAME}" >/dev/null 2>&1; then
        echo "Creating IAM instance profile ${EC2_PROFILE_NAME}..."
        aws iam create-instance-profile \
            --instance-profile-name "${EC2_PROFILE_NAME}" \
            --tags Key=project,Value=alphaforge
        aws iam add-role-to-instance-profile \
            --instance-profile-name "${EC2_PROFILE_NAME}" \
            --role-name "${EC2_ROLE_NAME}"
    fi

    # AMI
    AMI_ID=$(aws ssm get-parameter --name "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64" --query "Parameter.Value" --output text)

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
  -p 80:8000 \
  --log-driver awslogs \
  --log-opt awslogs-group=/alphaforge/app \
  --log-opt awslogs-region="${AWS_REGION}" \
  --log-opt awslogs-create-group=true \
  -e AF_S3_BUCKET="${S3_BUCKET}" \
  -e AF_DYNAMODB_TABLE="${DYNAMODB_TABLE}" \
  -e AF_TRACE_BACKEND="dynamodb" \
  -e AWS_REGION="${AWS_REGION}" \
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
        if curl -s -f "http://${PUBLIC_IP}/health" >/dev/null 2>&1; then
            echo "Health check PASSED!"
            break
        fi
        echo "Waiting for Docker bootstrap ($i/30)..."
        sleep 5
    done

    echo "============================================="
    echo "       AlphaForge Deployment SUCCESS!"
    echo "============================================="
    echo "Public URL:   http://${PUBLIC_IP}/"
    echo "Health Check: http://${PUBLIC_IP}/health"
}

if [ "${ACTION}" = "update" ]; then
    build_and_push
    redeploy_via_ssm
else
    full_deploy
fi
