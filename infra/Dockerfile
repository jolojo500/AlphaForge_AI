# One container: FastAPI backend that also serves the built React frontend.
# Build from the repository root:  docker build -f infra/Dockerfile -t alphaforge .

FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS app
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alphaforge ./alphaforge
COPY data ./data
COPY Datathon2026/alphaforge_starter ./Datathon2026/alphaforge_starter
COPY --from=web /web/dist ./frontend/dist
RUN uv sync --frozen --no-dev

# Credentials never live in the image: the platform supplies them through an IAM role.
ENV AWS_REGION=us-east-1 \
    AF_TRACE_BACKEND=local \
    AF_NEWS_MODE=cache \
    PORT=8080

RUN useradd --create-home app && mkdir -p /app/data/runs && chown -R app /app/data
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,os;urllib.request.urlopen('http://localhost:%s/health' % os.environ.get('PORT','8080'))"
CMD ["sh", "-c", "exec /app/.venv/bin/uvicorn alphaforge.api.server:app --host 0.0.0.0 --port ${PORT}"]
