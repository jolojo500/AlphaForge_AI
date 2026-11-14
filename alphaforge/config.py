"""Environment-driven settings. Orchestrator-owned (PRD 3.1)."""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STARTER_DIR = Path(
    os.getenv("AF_STARTER_DIR", REPO_ROOT / "Datathon2026" / "alphaforge_starter")
)
CACHE_DIR = Path(os.getenv("AF_CACHE_DIR", REPO_ROOT / "data" / "cache"))

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
MODEL_MAIN = os.getenv("AF_MODEL_MAIN", "global.anthropic.claude-sonnet-5-5")
MODEL_FAST = os.getenv("AF_MODEL_FAST", "global.anthropic.claude-haiku-5-5")

NEWS_MODE = os.getenv("AF_NEWS_MODE", "cache")  # cache | live
TRACE_BACKEND = os.getenv("AF_TRACE_BACKEND", "local")  # local | dynamodb
S3_BUCKET = os.getenv("AF_S3_BUCKET") or None

# Last date covered by the starter dataset; default "today" for every run.
DEFAULT_AS_OF = dt.date(2026, 11, 12)

MAX_RED_TEAM_LOOPS = 2
MAX_EXPLAIN_RETRIES = 1
