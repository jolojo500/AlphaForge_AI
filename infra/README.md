# AlphaForge AI — Infrastructure & AWS Deployment (PRD §8, C-6)

This document describes the cloud infrastructure, deployment pipeline, created AWS resources, environment variables, redeployment workflows, and teardown procedures for **AlphaForge AI** (Datathon PolyFinances 2026).

---

## 1. Live Public Endpoint

- **Public Web Application & API**: [https://d1br9rnvwb43a5.cloudfront.net/](https://d1br9rnvwb43a5.cloudfront.net/) (HTTP Port 80)
- **Health Check Endpoint**: [https://d1br9rnvwb43a5.cloudfront.net/health](https://d1br9rnvwb43a5.cloudfront.net/health) (`{"status":"ok"}`)
- **Persona List Endpoint**: [https://d1br9rnvwb43a5.cloudfront.net/personas](https://d1br9rnvwb43a5.cloudfront.net/personas)
- **CloudWatch Logs**: `/alphaforge/app` (us-east-1)

All three personas (`amira`, `mateo`, `robert`) run live with real-time SSE streaming (`/runs/{id}/events`), interactive What-If scenario comparisons (`/runs/{id}/whatif`), and automated trace persistence in DynamoDB + S3.

---

## 2. Architecture Overview

AlphaForge AI is packaged as a single self-contained Docker image using a multi-stage build:
1. **Frontend Builder (`node:22-alpine`)**: Builds the React 18 + Vite + Tailwind + shadcn/ui Single Page Application (`frontend/dist/`).
2. **Python Runtime (`python:3.12-slim`)**: Uses `uv` for reproducible virtual environment dependencies, serves FastAPI backend routes and SSE events, and serves static SPA assets at `/` with HTML5 pushState fallback.
3. **AWS Services**:
   - **EC2 Instance (`AlphaForge-Server`, t3.medium)**: Runs Docker container serving on port 80.
   - **Amazon ECR (`alphaforge`)**: Stores versioned container image layers.
   - **Amazon S3 (`alphaforge-data-908027403910`)**: Stores starter dataset (`starter/`), calculation caches (`cache/`), and offloaded full graph run states (`runs/<run_id>.json`).
   - **Amazon DynamoDB (`alphaforge-traces`)**: Stores run execution records, node trace timelines, and validation flags (`PAY_PER_REQUEST`).
   - **Amazon CloudWatch (`/alphaforge/app`)**: Container logs streamed in real time via the Docker `awslogs` driver.
   - **AWS Systems Manager (SSM)**: Fast, non-disruptive continuous redeployment via SSM `send-command`.
   - **Amazon Bedrock**: LLM invocation for LangGraph multi-agent orchestration (`global.anthropic.claude-sonnet-5-5` and `global.anthropic.claude-haiku-5-5`).

---

## 3. Inventory of AWS Resources Created

All created resources are tagged with `project=alphaforge`.

| Resource | AWS Type | Identifier / ARN | Purpose |
|---|---|---|---|
| **EC2 Server** | `AWS::EC2::Instance` | `i-0ec3c5dff3ac51dc4` (`18.206.125.42`) | Hosts AlphaForge Docker container on port 80. |
| **Security Group** | `AWS::EC2::SecurityGroup` | `sg-042067e98ce0e9cff` (`alphaforge-sg`) | Allows inbound TCP 80 from `0.0.0.0/0`. |
| **EC2 Instance Profile** | `AWS::IAM::InstanceProfile` | `alphaforge-ec2-instance-profile` | Attaches IAM role to the EC2 server. |
| **EC2 IAM Role** | `AWS::IAM::Role` | `arn:aws:iam::908027403910:role/alphaforge-ec2-role` | Scoped permissions for Bedrock, S3, DynamoDB, SSM, and CloudWatch. |
| **ECR Repository** | `AWS::ECR::Repository` | `908027403910.dkr.ecr.us-east-1.amazonaws.com/alphaforge` | Stores Docker container images. |
| **S3 Bucket** | `AWS::S3::Bucket` | `alphaforge-data-908027403910` | Versioned object storage for starter data, caches, and run states. |
| **DynamoDB Table** | `AWS::DynamoDB::Table` | `alphaforge-traces` | On-demand table for run audit records, verification, and traces. |
| **CloudWatch Log Group** | `AWS::Logs::LogGroup` | `/alphaforge/app` | Real-time container application logs. |

---

## 4. Environment Variables

| Variable | Default Value | Description |
|---|---|---|
| `AF_MODEL_MAIN` | `global.anthropic.claude-sonnet-5-5` | Bedrock model ID for main reasoning and explanations (PRD §2 default). |
| `AF_MODEL_FAST` | `global.anthropic.claude-haiku-5-5` | Bedrock model ID for screening and fast tasks (PRD §2 default). |
| `AF_S3_BUCKET` | `alphaforge-data-908027403910` | S3 bucket holding dataset, caches, and offloaded run states. |
| `AF_DYNAMODB_TABLE` | `alphaforge-traces` | DynamoDB table name for storing run traces. |
| `AF_TRACE_BACKEND` | `dynamodb` | Trace storage backend: `dynamodb` (AWS) or `local` (offline). |
| `AF_NEWS_MODE` | `cache` (local) / `live` (EC2) | News retrieval mode: `live` fetches fresh company news and web search; `cache` uses committed SEC filings/searches only. |
| `FINNHUB_API_KEY` | *(None / SSM)* | Finnhub API key for live company news. Resolved from env or SSM Parameter Store `/alphaforge/finnhub_api_key`. |
| `TAVILY_API_KEY` | *(None / SSM)* | Tavily Search API key for live web search. Resolved from env or SSM Parameter Store `/alphaforge/tavily_api_key`. |
| `AWS_REGION` | `us-east-1` | AWS region for all resources. |
| `AWS_PROFILE` | `datathon` | AWS CLI / SDK profile (if using local named profile). |

---

### 4.1 Secrets Management & Live News API Keys (B-9)

In compliance with strict security requirements (PRD §8), API secrets are **never committed to the repository, never built into Docker images, and never hardcoded**:

- **Resolution Precedence** (`alphaforge.secrets.get_secret`):
  1. Container environment variables (`FINNHUB_API_KEY`, `TAVILY_API_KEY`).
  2. AWS Systems Manager (SSM) Parameter Store:
     - `/alphaforge/finnhub_api_key`
     - `/alphaforge/tavily_api_key`
  3. Seamless cache fallback with diagnostic evidence warning (zero crashes).

- **Setting Keys via AWS CLI**:
  ```bash
  export AWS_PROFILE=datathon
  export AWS_REGION=us-east-1

  # Finnhub API Key (Company News)
  aws ssm put-parameter \
    --name "/alphaforge/finnhub_api_key" \
    --value "<YOUR_FINNHUB_API_KEY>" \
    --type SecureString \
    --overwrite

  # Tavily API Key (Live Web Search)
  aws ssm put-parameter \
    --name "/alphaforge/tavily_api_key" \
    --value "<YOUR_TAVILY_API_KEY>" \
    --type SecureString \
    --overwrite
  ```

- **IAM Permissions**:
  The EC2 IAM role `alphaforge-ec2-role` includes scoped permissions for SSM Parameter Store:
  `arn:aws:ssm:us-east-1:<ACCOUNT_ID>:parameter/alphaforge/*` and Secrets Manager `arn:aws:secretsmanager:us-east-1:<ACCOUNT_ID>:secret:/alphaforge/*`.

- **Resilience & Graceful Degradation**:
  - **No key configured**: Agent 2 falls back to the local SEC EDGAR filings and cached search results, logging a warning in evidence (`news_warning`).
  - **Rate limits (HTTP 429)**: Handled gracefully without raising; falls back to cache with an explicit warning evidence entry.
  - **Timeouts**: Handled gracefully without raising; falls back to cache with an explicit warning evidence entry.
  - **Zero hallucinated data**: The platform never fabricates news items or returns fake numbers.

---

## 5. Deployment & Redeployment Instructions

### Continuous Redeployment (`update`)

When other tracks merge nodes into `main`, update the live deployment without recreating resources:

```bash
export AWS_PROFILE=datathon
export AWS_REGION=us-east-1

# Option 1: Fast redeploy script
./infra/redeploy.sh

# Option 2: deploy.sh update argument
./infra/deploy.sh update
```

The script:
1. Builds the latest multi-stage Docker image from the current codebase.
2. Pushes `alphaforge:latest` to ECR.
3. Dispatches an AWS SSM `AWS-RunShellScript` command to `AlphaForge-Server` (`i-0ec3c5dff3ac51dc4`).
4. Pulls the latest image and restarts the container with the `awslogs` driver.
5. Polls until the `/health` endpoint is confirmed 200 OK.

### Initial Full Provisioning (`deploy`)

```bash
export AWS_PROFILE=datathon
export AWS_REGION=us-east-1
./infra/deploy.sh
```

### Local Docker Build & Test

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

# 5. Delete CloudWatch Log Group
aws logs delete-log-group --log-group-name /alphaforge/app

# 6. (Optional) Delete S3 Bucket and DynamoDB Table
# aws dynamodb delete-table --table-name alphaforge-traces
# aws s3 rb s3://alphaforge-data-908027403910 --force
```

## HTTPS (#112)

The public URL is **https://d1br9rnvwb43a5.cloudfront.net/** (CloudFront distribution `E28Y8O0PL1SV9A`, tag `project=alphaforge`). CloudFront terminates TLS with its default certificate, redirects HTTP to HTTPS, disables caching (API + server-sent events) and forwards all viewer headers. `infra/cloudfront.sh` creates it idempotently; with `AF_LOCK_ORIGIN=1` it also restricts the instance's port 80 to CloudFront's origin-facing prefix list, so the bare IP no longer serves the app in clear text. The app sets HSTS, CSP, `X-Frame-Options` and `X-Content-Type-Options` on every response.
