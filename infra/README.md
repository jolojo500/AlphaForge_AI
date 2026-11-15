# AlphaForge AI — Infrastructure & AWS Deployment (PRD §8, C-6)

This document describes the cloud infrastructure, deployment pipeline, created AWS resources, environment variables, and teardown procedures for **AlphaForge AI** (Datathon PolyFinances 2026).

---

## 1. Live Public Endpoint

- **Public Web Application & API**: [http://18.206.125.42/](http://18.206.125.42/) (also available on port 8000: [http://18.206.125.42:8000/](http://18.206.125.42:8000/))
- **Health Check Endpoint**: [http://18.206.125.42/health](http://18.206.125.42/health) (`{"status":"ok"}`)
- **Persona List Endpoint**: [http://18.206.125.42/personas](http://18.206.125.42/personas)

All three personas (`amira`, `mateo`, `robert`) run live with real-time SSE streaming (`/runs/{id}/events`), interactive What-If scenario comparisons (`/runs/{id}/whatif`), and automated trace persistence in DynamoDB + S3.

---

## 2. Architecture Overview

AlphaForge AI is packaged as a single self-contained Docker image using a multi-stage build:
1. **Frontend Builder (`node:22-alpine`)**: Builds the React 18 + Vite + Tailwind + shadcn/ui Single Page Application (`frontend/dist/`).
2. **Python Runtime (`python:3.12-slim`)**: Uses `uv` for reproducible virtual environment dependencies, serves FastAPI backend routes and SSE events, and serves static SPA assets at `/` with HTML5 pushState fallback.
3. **AWS Services**:
   - **EC2 Instance (`AlphaForge-Server`, t3.medium)**: Runs Docker container serving on ports 80 and 8000.
   - **Amazon ECR (`alphaforge`)**: Stores versioned container image layers.
   - **Amazon S3 (`alphaforge-data-908027403910`)**: Stores starter dataset (`starter/`), calculation caches (`cache/`), and offloaded full graph run states (`runs/<run_id>.json`).
   - **Amazon DynamoDB (`alphaforge-traces`)**: Stores run execution records, node trace timelines, and validation flags (`PAY_PER_REQUEST`).
   - **Amazon Bedrock**: LLM invocation for LangGraph multi-agent orchestration (`Claude 3.5 Sonnet v2` and `Claude 3.5 Haiku`).

> **Note on App Runner vs EC2**: The deployment script (`infra/deploy.sh`) attempts AWS App Runner first per spec. Because the workshop AWS account SCP (Service Control Policy) restricts `apprunner:CreateService`, the deployment script automatically switches to an isolated EC2 (`t3.medium`) instance running Docker without touching the workshop's `WebIDE` instance or `kiro-ide-browser` stack.

---

## 3. Inventory of AWS Resources Created

All created resources are tagged with `project=alphaforge`.

| Resource | AWS Type | Identifier / ARN | Purpose |
|---|---|---|---|
| **EC2 Server** | `AWS::EC2::Instance` | `i-0ec3c5dff3ac51dc4` (`18.206.125.42`) | Hosts AlphaForge Docker container on ports 80 and 8000. |
| **Security Group** | `AWS::EC2::SecurityGroup` | `sg-042067e98ce0e9cff` (`alphaforge-sg`) | Allows inbound TCP 80 and 8000 from `0.0.0.0/0`. |
| **EC2 Instance Profile** | `AWS::IAM::InstanceProfile` | `alphaforge-ec2-instance-profile` | Attaches IAM role to the EC2 server. |
| **EC2 IAM Role** | `AWS::IAM::Role` | `arn:aws:iam::908027403910:role/alphaforge-ec2-role` | Grants permissions for Bedrock, S3, DynamoDB, and CloudWatch. |
| **ECR Repository** | `AWS::ECR::Repository` | `908027403910.dkr.ecr.us-east-1.amazonaws.com/alphaforge` | Stores Docker container images. |
| **S3 Bucket** | `AWS::S3::Bucket` | `alphaforge-data-908027403910` | Versioned object storage for starter data, caches, and run states. |
| **DynamoDB Table** | `AWS::DynamoDB::Table` | `alphaforge-traces` | On-demand table for run audit records, verification, and traces. |

---

## 4. Environment Variables

| Variable | Default Value | Description |
|---|---|---|
| `AF_MODEL_MAIN` | `anthropic.claude-3-5-sonnet-20241022-v2:0` | Amazon Bedrock model ID for main reasoning and explanations. |
| `AF_MODEL_FAST` | `us.anthropic.claude-3-5-haiku-20241022-v1:0` | Amazon Bedrock model ID for screening and fast tasks. |
| `AF_S3_BUCKET` | `alphaforge-data-908027403910` | S3 bucket holding dataset, caches, and offloaded run states. |
| `AF_DYNAMODB_TABLE` | `alphaforge-traces` | DynamoDB table name for storing run traces. |
| `AF_TRACE_BACKEND` | `dynamodb` | Trace storage backend: `dynamodb` (AWS) or `local` (offline). |
| `AWS_REGION` | `us-east-1` | AWS region for all resources. |
| `AWS_PROFILE` | `datathon` | AWS CLI / SDK profile (if using local named profile). |

---

## 5. Deployment Instructions

### Automated Deployment

Run the idempotent deployment script:

```bash
export AWS_PROFILE=datathon
export AWS_REGION=us-east-1
./infra/deploy.sh
```

The script performs:
1. ECR repository creation with `project=alphaforge` tag.
2. IAM role and instance profile configuration with scoped permissions.
3. Multi-stage Docker build (`infra/Dockerfile`) and push to ECR.
4. App Runner service check and automatic fallback to EC2 (`t3.medium`).
5. Security group provisioning (allowing ports 80 and 8000).
6. Cloud-init bootstrap launching the Docker container.
7. Verification of the `/health` endpoint on the public URL.

### Local Docker Build & Test

To build and run locally without AWS:

```bash
# Build the multi-stage image
docker build -t alphaforge:local -f infra/Dockerfile .

# Run container locally
docker run -p 8000:8000 \
  -e AF_TRACE_BACKEND=local \
  alphaforge:local

# Verify
curl http://localhost:8000/health
```

---

## 6. Teardown Instructions

To clean up all AWS resources created for Track C:

```bash
export AWS_PROFILE=datathon
export AWS_REGION=us-east-1

# 1. Terminate EC2 instance
aws ec2 terminate-instances --instance-ids i-0ec3c5dff3ac51dc4
aws ec2 wait instance-terminated --instance-ids i-0ec3c5dff3ac51dc4

# 2. Delete Security Group
aws ec2 delete-security-group --group-id sg-042067e98ce0e9cff

# 3. Clean up EC2 IAM Role & Instance Profile
aws iam remove-role-from-instance-profile --instance-profile-name alphaforge-ec2-instance-profile --role-name alphaforge-ec2-role
aws iam delete-instance-profile --instance-profile-name alphaforge-ec2-instance-profile
aws iam delete-role-policy --role-name alphaforge-ec2-role --policy-name alphaforge-ec2-policy
aws iam detach-role-policy --role-name alphaforge-ec2-role --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly
aws iam detach-role-policy --role-name alphaforge-ec2-role --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam delete-role --role-name alphaforge-ec2-role

# 4. Delete ECR Repository
aws ecr delete-repository --repository-name alphaforge --force

# 5. (Optional) Delete S3 Bucket and DynamoDB Table
# aws dynamodb delete-table --table-name alphaforge-traces
# aws s3 rb s3://alphaforge-data-908027403910 --force
```
