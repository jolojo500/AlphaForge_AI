#!/usr/bin/env bash
# Fallback if App Runner is blocked: run the same image on a single EC2 instance.
# Prerequisite: the image was pushed to ECR (steps 1-3 of deploy_apprunner.sh), and an instance
# profile exists whose role carries infra/policy-runtime.json plus ECR read access.
#   INSTANCE_PROFILE=alphaforge-ec2 SUBNET_ID=subnet-... SG_ID=sg-... infra/deploy_ec2.sh
# The security group must allow inbound TCP 80 from the viewers.
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
NAME="${AF_SERVICE_NAME:-alphaforge}"
TABLE="${AF_TRACE_TABLE:-alphaforge-traces}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
REGISTRY="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
TAG="${AF_IMAGE_TAG:-$(git rev-parse --short HEAD)}"
: "${INSTANCE_PROFILE:?set INSTANCE_PROFILE}" "${SUBNET_ID:?set SUBNET_ID}" "${SG_ID:?set SG_ID}"

AMI="$(aws ssm get-parameter --region "$REGION" --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 --query Parameter.Value --output text)"

USER_DATA="#!/bin/bash
dnf install -y docker
systemctl enable --now docker
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $REGISTRY
docker run -d --restart always -p 80:8080 \\
  -e AWS_REGION=$REGION -e AF_TRACE_BACKEND=dynamodb -e AF_TRACE_TABLE=$TABLE -e AF_NEWS_MODE=cache \\
  $REGISTRY/$NAME:$TAG
"

aws ec2 run-instances --region "$REGION" --image-id "$AMI" --instance-type t3.small \
  --iam-instance-profile "Name=$INSTANCE_PROFILE" --subnet-id "$SUBNET_ID" --security-group-ids "$SG_ID" \
  --metadata-options "HttpTokens=required,HttpEndpoint=enabled" \
  --user-data "$USER_DATA" --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME}]" \
  --query 'Instances[0].InstanceId' --output text
echo "Wait ~2 minutes, then open http://<public-ip>/ (aws ec2 describe-instances)."
