# Stage 1: Build Frontend
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Stage 2: Python Backend & SPA Host
FROM python:3.12-slim AS runner

# Install uv binary
COPY --from=ghcr.io/astral-sh/uv:0.5.21 /uv /uvx /bin/

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000 \
    PATH="/app/.venv/bin:$PATH"

# Install Python dependencies into virtual environment
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code, infra tools, and data
COPY alphaforge /app/alphaforge
COPY infra /app/infra
COPY Datathon2026 /app/Datathon2026
COPY data /app/data
COPY tests/fixtures /app/tests/fixtures

# Copy built frontend distribution
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

EXPOSE 8000

CMD ["uvicorn", "alphaforge.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
