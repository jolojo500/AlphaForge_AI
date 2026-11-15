"""Tests for public API auth, run ownership and rate limits (C-11)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from starlette.testclient import TestClient

from alphaforge.api.server import InMemoryRunStore, app, reset_limits, set_store
from alphaforge.personas import PERSONAS

REPO_ROOT = Path(__file__).resolve().parent.parent


def setup_function():
    set_store(InMemoryRunStore())
    reset_limits()


def _create(client: TestClient, persona: str = "robert", text: str | None = None) -> str:
    resp = client.post(
        "/runs",
        json={
            "persona": persona,
            "request_text": text if text is not None else PERSONAS[persona]["example_request"],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["run_id"]


def _wait_listed(client: TestClient, run_id: str, timeout: float = 30) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        runs = client.get("/runs").json()
        for run in runs:
            if run["run_id"] == run_id:
                return run
        time.sleep(0.1)
    raise AssertionError(f"run {run_id} was not listed")


def test_second_session_cannot_read_or_steer_first_session_run():
    first = TestClient(app)
    second = TestClient(app)

    run_id = _create(first)

    assert second.get(f"/runs/{run_id}").status_code == 404
    assert second.get(f"/runs/{run_id}/events").status_code == 404
    assert second.post(f"/runs/{run_id}/answer", json={"text": "hello"}).status_code == 404
    assert (
        second.post(
            f"/runs/{run_id}/whatif",
            json={"field": "risk_tolerance", "value": "high"},
        ).status_code
        == 404
    )

    # The owner still has access.
    assert first.get(f"/runs/{run_id}").status_code in (200, 202)


def test_list_runs_returns_golden_and_only_callers_own_runs():
    first = TestClient(app)
    second = TestClient(app)

    first_run = _create(first)
    second_run = _create(second)

    # In-flight runs are visible to their owner immediately, and never to another session.
    first_ids = {run["run_id"] for run in first.get("/runs").json()}
    assert first_run in first_ids
    assert second_run not in first_ids
    assert {"golden_robert_tsla", "golden_amira_build", "golden_mateo_build"} <= first_ids

    second_ids = {run["run_id"] for run in second.get("/runs").json()}
    assert second_run in second_ids
    assert first_run not in second_ids

    # Completed runs stay visible after persistence.
    _wait_listed(first, first_run)
    _wait_listed(second, second_run)
    assert first_run in {run["run_id"] for run in first.get("/runs").json()}
    assert second_run in {run["run_id"] for run in second.get("/runs").json()}


def test_post_runs_is_rate_limited(monkeypatch):
    monkeypatch.setenv("AF_RATE_LIMIT_PER_MINUTE", "2")
    monkeypatch.setenv("AF_DAILY_RUN_CAP", "100")
    reset_limits()
    client = TestClient(app)

    assert _create(client)
    assert _create(client)

    limited = client.post(
        "/runs", json={"persona": "robert", "request_text": "one too many"}
    )
    assert limited.status_code == 429
    assert "Rate limit" in limited.json()["detail"]


def test_daily_global_run_cap(monkeypatch):
    monkeypatch.setenv("AF_DAILY_RUN_CAP", "1")
    monkeypatch.setenv("AF_RATE_LIMIT_PER_MINUTE", "100")
    reset_limits()
    client = TestClient(app)

    assert _create(client)

    capped = client.post(
        "/runs", json={"persona": "robert", "request_text": "one too many"}
    )
    assert capped.status_code == 429
    assert "Daily run cap" in capped.json()["detail"]


def test_demo_token_required_on_write_endpoints_when_configured(monkeypatch):
    monkeypatch.setenv("AF_DEMO_TOKEN", "demo-secret")
    monkeypatch.setenv("AF_RATE_LIMIT_PER_MINUTE", "100")
    reset_limits()
    client = TestClient(app)

    unauthorized = client.post(
        "/runs", json={"persona": "robert", "request_text": "hello"}
    )
    assert unauthorized.status_code == 401

    authorized = client.post(
        "/runs",
        headers={"X-Demo-Token": "demo-secret"},
        json={"persona": "robert", "request_text": "hello"},
    )
    assert authorized.status_code == 200


def test_docs_and_openapi_disabled_when_prod():
    env = os.environ.copy()
    env["AF_ENV"] = "prod"
    env["AF_LLM_OFFLINE"] = "1"
    output = subprocess.check_output(
        [
            sys.executable,
            "-c",
            (
                "import json; from alphaforge.api.server import app; "
                "print(json.dumps([app.docs_url, app.redoc_url, app.openapi_url]))"
            ),
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
    )
    assert json.loads(output.strip().splitlines()[-1]) == [None, None, None]
