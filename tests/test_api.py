"""Tests for the FastAPI backend and SSE streaming (C-1)."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

from alphaforge.api.server import InMemoryRunStore, app, set_store
from alphaforge.personas import PERSONAS
from alphaforge.state import SCENARIO_NAMES

EXPECTED_NODES = {
    "profile",
    "screening",
    "quant",
    "macro",
    "events",
    "scenarios",
    "red_team",
    "explain",
    "verifier",
}


def setup_function():
    # Fresh in-memory store before each test
    set_store(InMemoryRunStore())


def test_health():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_personas():
    client = TestClient(app)
    resp = client.get("/personas")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == set(PERSONAS.keys())
    assert data["robert"]["label"] == PERSONAS["robert"]["label"]


def test_create_run_unknown_persona():
    client = TestClient(app)
    resp = client.post("/runs", json={"persona": "invalid", "request_text": "hello"})
    assert resp.status_code == 400
    assert "Unknown persona" in resp.json()["detail"]


def test_full_run_streaming_and_get_state():
    client = TestClient(app)
    # Start a run with Robert
    create_resp = client.post(
        "/runs",
        json={"persona": "robert", "request_text": PERSONAS["robert"]["example_request"]},
    )
    assert create_resp.status_code == 200
    run_id = create_resp.json()["run_id"]
    assert run_id

    # Stream SSE events
    events = []
    with client.stream("GET", f"/runs/{run_id}/events") as sse_resp:
        assert sse_resp.status_code == 200
        for line in sse_resp.iter_lines():
            if line.startswith("data: "):
                payload = json.loads(line[len("data: ") :])
                events.append(payload)

    # Check event sequence
    event_types = [e["type"] for e in events]
    assert "final" in event_types
    final_event = next(e for e in events if e["type"] == "final")
    assert final_event["run_id"] == run_id

    trace_nodes = {e["entry"]["node"] for e in events if e["type"] == "trace"}
    assert trace_nodes == EXPECTED_NODES

    # Check GET /runs/{run_id}
    state_resp = client.get(f"/runs/{run_id}")
    assert state_resp.status_code == 200
    state = state_resp.json()
    assert state["persona"] == "robert"
    assert state["profile"]["persona"] == "robert"
    assert [s["name"] for s in state["scenarios"]] == list(SCENARIO_NAMES)
    assert state["verification"]["passed"] is True


def test_interrupt_and_resume_flow():
    client = TestClient(app)
    # Empty request text triggers an interrupt in the profile stub
    create_resp = client.post(
        "/runs",
        json={"persona": "amira", "request_text": ""},
    )
    assert create_resp.status_code == 200
    run_id = create_resp.json()["run_id"]

    # Stream until interrupt
    events_before = []
    with client.stream("GET", f"/runs/{run_id}/events") as sse_resp:
        for line in sse_resp.iter_lines():
            if line.startswith("data: "):
                payload = json.loads(line[len("data: ") :])
                events_before.append(payload)
                if payload.get("type") == "interrupt":
                    # We break the connection to simulate answering
                    break

    interrupt_events = [e for e in events_before if e["type"] == "interrupt"]
    assert len(interrupt_events) == 1
    assert interrupt_events[0]["question"]

    # Trying to answer with invalid id gives 404
    bad_answer = client.post("/runs/non_existent/answer", json={"text": "hello"})
    assert bad_answer.status_code == 404

    # Post answer to resume
    answer_resp = client.post(
        f"/runs/{run_id}/answer",
        json={"text": PERSONAS["amira"]["example_request"]},
    )
    assert answer_resp.status_code == 200
    assert answer_resp.json()["status"] == "resumed"

    # Stream after resuming
    events_after = []
    with client.stream("GET", f"/runs/{run_id}/events") as sse_resp:
        for line in sse_resp.iter_lines():
            if line.startswith("data: "):
                payload = json.loads(line[len("data: ") :])
                events_after.append(payload)

    # The reconnected stream replayed earlier events and received the new final event
    assert any(e["type"] == "final" and e["run_id"] == run_id for e in events_after)

    # State is completed
    state_resp = client.get(f"/runs/{run_id}")
    assert state_resp.status_code == 200
    assert state_resp.json()["verification"]["passed"] is True


def test_answer_when_not_interrupted():
    client = TestClient(app)
    # Robert does not interrupt
    create_resp = client.post(
        "/runs",
        json={"persona": "robert", "request_text": PERSONAS["robert"]["example_request"]},
    )
    run_id = create_resp.json()["run_id"]

    # Wait briefly for completion
    time.sleep(0.1)

    resp = client.post(f"/runs/{run_id}/answer", json={"text": "irrelevant"})
    assert resp.status_code == 400
    assert "not awaiting an answer" in resp.json()["detail"]


def test_error_handling_in_stream():
    client = TestClient(app)

    def failing_stream(*args, **kwargs):
        yield {"type": "trace", "entry": {"node": "profile", "summary": "starting"}}
        raise RuntimeError("Something exploded")

    with patch("alphaforge.api.server.stream_run", failing_stream):
        create_resp = client.post(
            "/runs",
            json={"persona": "robert", "request_text": "explode"},
        )
        run_id = create_resp.json()["run_id"]

        events = []
        with client.stream("GET", f"/runs/{run_id}/events") as sse_resp:
            for line in sse_resp.iter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[len("data: ") :]))

        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert "Something exploded" in error_events[0]["error"]

        # GET /runs/{run_id} returns 500
        state_resp = client.get(f"/runs/{run_id}")
        assert state_resp.status_code == 500


def test_spa_fallback_when_dist_exists():
    client = TestClient(app)
    with tempfile.TemporaryDirectory() as tmp_dist:
        dist_path = Path(tmp_dist)
        index_html = dist_path / "index.html"
        index_html.write_text("<!doctype html><html><body>SPA</body></html>")
        asset_file = dist_path / "app.js"
        asset_file.write_text("console.log('app');")

        with patch("alphaforge.api.server.DIST_DIR", dist_path):
            # Root path returns index.html
            r_root = client.get("/")
            assert r_root.status_code == 200
            assert "SPA" in r_root.text

            # Static asset returns asset content
            r_asset = client.get("/app.js")
            assert r_asset.status_code == 200
            assert "console.log('app')" in r_asset.text

            # Unknown route falls back to index.html
            r_spa = client.get("/robert/scenarios")
            assert r_spa.status_code == 200
            assert "SPA" in r_spa.text
