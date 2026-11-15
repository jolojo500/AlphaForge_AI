# Deployment

One container serves the FastAPI backend and the built React frontend (PRD 2, Models and AWS).

| File | Purpose |
|---|---|
| `Dockerfile` | Multi-stage build: `npm run build`, then Python 3.12 with `uv`. Build from the repo root. |
| `deploy_apprunner.sh` | Creates the DynamoDB table and ECR repo, pushes the image, creates the App Runner service. |
| `deploy_ec2.sh` | Fallback on a single EC2 instance if App Runner is blocked (decision: Sunday 14:00). |
| `policy-runtime.json` | Least-privilege runtime policy: Bedrock invoke and the `alphaforge-traces` table. |

## Run locally without Docker

```bash
cd frontend && npm ci && npm run build && cd ..
uv run uvicorn alphaforge.api.server:app --port 8000   # serves the API and frontend/dist
```

## Deploy

```bash
# credentials come from the environment or AWS_PROFILE; nothing is baked into the image
infra/deploy_apprunner.sh
```

The container reads `AWS_REGION`, `AF_TRACE_BACKEND`, `AF_TRACE_TABLE` and `AF_NEWS_MODE`.
Bedrock and DynamoDB are reached through the instance role. If AWS calls fail (for example an
expired token), the app keeps working: traces fall back to local files and the LLM nodes fall
back to their deterministic paths.

Not verified in the workshop environment: no Docker daemon was available, so the image build
and both scripts were checked for syntax only.
