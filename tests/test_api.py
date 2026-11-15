"""Tests for the FastAPI backend and SSE streaming (C-1)."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest
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


def test_whatif_api_flow():
    client = TestClient(app)
    # Start parent run
    create_resp = client.post(
        "/runs",
        json={"persona": "robert", "request_text": PERSONAS["robert"]["example_request"]},
    )
    parent_id = create_resp.json()["run_id"]

    # Stream parent to completion
    with client.stream("GET", f"/runs/{parent_id}/events") as sse_resp:
        for _ in sse_resp.iter_lines():
            pass

    # Start what-if child run
    whatif_resp = client.post(
        f"/runs/{parent_id}/whatif",
        json={"field": "risk_tolerance", "value": "high"},
    )
    assert whatif_resp.status_code == 200
    child_id = whatif_resp.json()["run_id"]
    assert whatif_resp.json()["parent_run_id"] == parent_id

    # Stream child events
    child_events = []
    with client.stream("GET", f"/runs/{child_id}/events") as sse_resp:
        for line in sse_resp.iter_lines():
            if line.startswith("data: "):
                child_events.append(json.loads(line[len("data: ") :]))

    # Child run skips Agent 1 (profile)
    trace_nodes = {e["entry"]["node"] for e in child_events if e["type"] == "trace"}
    assert "profile" not in trace_nodes
    assert "screening" in trace_nodes

    # Fetch child state
    state_resp = client.get(f"/runs/{child_id}")
    assert state_resp.status_code == 200
    child_state = state_resp.json()
    assert child_state["parent_run_id"] == parent_id
    assert child_state["change"] == {"field": "risk_tolerance", "value": "high"}
    assert child_state["profile"]["risk_tolerance"] == "high"

    # Fetch diff
    diff_resp = client.get(f"/runs/{child_id}/diff")
    assert diff_resp.status_code == 200
    diff = diff_resp.json()
    assert "scenarios" in diff
    assert "capped" in diff["scenarios"]
    assert diff["scenarios"]["capped"]["weights"]["TSLA"]["old"] == pytest.approx(0.03)  # capacity low binds (#115)

    # Compare two runs via /runs/compare (C-9)
    compare_resp = client.get(f"/runs/compare?run_a={parent_id}&run_b={child_id}")
    assert compare_resp.status_code == 200
    comp = compare_resp.json()
    assert comp["run_a_id"] == parent_id
    assert comp["run_b_id"] == child_id
    assert "scenarios" in comp


def _custom(tolerance: str, horizon: int = 10) -> dict:
    return {
        "objective": "growth",
        "horizon_years": horizon,
        "risk_tolerance": tolerance,
        "risk_capacity": "moderate",
        "constraints": [],
        "preferences": ["likes_tech"],
        "budget_cad": 50000,
    }


def _wait_final(client: TestClient, run_id: str, timeout: float = 60) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/runs/{run_id}")
        if resp.status_code == 200 and resp.json().get("verification"):
            return resp.json()
        time.sleep(0.2)
    raise AssertionError(f"run {run_id} did not finish")


def test_custom_profiles_are_isolated_per_run():
    client = TestClient(app)
    text = "Je veux construire un portefeuille."
    a = client.post("/runs", json={"persona": "custom_user", "request_text": text,
                                   "profile_data": _custom("high", 15)}).json()["run_id"]
    b = client.post("/runs", json={"persona": "custom_user", "request_text": text,
                                   "profile_data": _custom("low", 3)}).json()["run_id"]
    sa, sb = _wait_final(client, a), _wait_final(client, b)
    assert sa["persona_data"]["risk_tolerance"] == "high"
    assert sb["persona_data"]["risk_tolerance"] == "low"
    assert sa["profile"]["risk_tolerance"] == "high" and sa["profile"]["horizon_years"] == 15
    assert sb["profile"]["risk_tolerance"] == "low" and sb["profile"]["horizon_years"] == 3


def test_personas_endpoint_unchanged_by_custom_runs():
    client = TestClient(app)
    before = client.get("/personas").json()
    run_id = client.post("/runs", json={"persona": "custom_user",
                                        "request_text": "Je veux construire un portefeuille.",
                                        "profile_data": _custom("moderate")}).json()["run_id"]
    _wait_final(client, run_id)
    after = client.get("/personas").json()
    assert set(after) == {"amira", "mateo", "robert"} and after == before
    assert PERSONAS["robert"]["risk_tolerance"] == "low_moderate"


@pytest.mark.parametrize("bad", [{"risk_tolerance": "yolo"}, {"risk_capacity": "huge"},
                                 {"horizon_years": 0}, {"horizon_years": "soon"}])
def test_invalid_custom_profile_is_rejected(bad):
    client = TestClient(app)
    resp = client.post("/runs", json={"persona": "custom_user", "request_text": "x",
                                      "profile_data": _custom("moderate") | bad})
    assert resp.status_code == 400


def test_unknown_persona_without_profile_is_rejected():
    client = TestClient(app)
    assert client.post("/runs", json={"persona": "custom_user", "request_text": "x"}).status_code == 400


def test_list_saved_runs_and_filter():
    client = TestClient(app)
    resp = client.get("/runs")
    assert resp.status_code == 200
    runs = resp.json()
    assert isinstance(runs, list)
    # Must contain at least the 3 golden demo runs
    golden_ids = {r["run_id"] for r in runs if r.get("is_golden")}
    assert "golden_robert_tsla" in golden_ids
    assert "golden_amira_build" in golden_ids
    assert "golden_mateo_build" in golden_ids

    # Filter by persona
    resp_robert = client.get("/runs?persona=robert")
    assert resp_robert.status_code == 200
    robert_runs = resp_robert.json()
    assert all(r["persona"] == "robert" for r in robert_runs)
    assert any(r["run_id"] == "golden_robert_tsla" for r in robert_runs)


def test_replay_golden_run_state_and_whatif():
    client = TestClient(app)
    # 1. Replay a golden run without any prior memory in store
    resp = client.get("/runs/golden_robert_tsla")
    assert resp.status_code == 200
    state = resp.json()
    assert state["run_id"] == "golden_robert_tsla"
    assert state["persona"] == "robert"
    assert len(state["scenarios"]) == 3
    assert len(state["trace"]) > 0
    assert state["verification"]["passed"] is True

    # 2. What-if on the replayed run (should rerun screening without Bedrock)
    resp_whatif = client.post(
        "/runs/golden_robert_tsla/whatif",
        json={"field": "risk_tolerance", "value": "high"},
    )
    assert resp_whatif.status_code == 200
    whatif_data = resp_whatif.json()
    child_id = whatif_data["run_id"]
    assert whatif_data["parent_run_id"] == "golden_robert_tsla"

    # Wait for whatif to complete
    child_state = _wait_final(client, child_id)
    assert child_state["persona"] == "robert"
    assert child_state["profile"]["risk_tolerance"] == "high"

    # 3. Diff against replayed parent
    resp_diff = client.get(f"/runs/{child_id}/diff")
    assert resp_diff.status_code == 200
    diff_data = resp_diff.json()
    assert diff_data["parent_run_id"] == "golden_robert_tsla"
    assert diff_data["child_run_id"] == child_id
    assert "scenarios" in diff_data


def test_custom_runs_do_not_grow_the_persona_table():
    client = TestClient(app)
    before = set(PERSONAS)
    for tol in ("high", "low", "moderate"):
        rid = client.post("/runs", json={"persona": "custom_user",
                                         "request_text": "Je veux construire un portefeuille.",
                                         "profile_data": _custom(tol)}).json()["run_id"]
        _wait_final(client, rid)
    assert set(PERSONAS) == before


def test_runs_are_private_to_their_owner():
    alice = TestClient(app, headers={"X-Client-Id": "alice"})
    bob = TestClient(app, headers={"X-Client-Id": "bob"})
    rid = alice.post("/runs", json={"persona": "robert",
                                    "request_text": PERSONAS["robert"]["example_request"]}).json()["run_id"]
    _wait_final(alice, rid)
    assert bob.get(f"/runs/{rid}").status_code == 404
    assert bob.post(f"/runs/{rid}/whatif", json={"field": "horizon_years", "value": 10}).status_code == 404
    assert bob.post(f"/runs/{rid}/answer", json={"text": "x"}).status_code == 404
    assert rid in {r["run_id"] for r in alice.get("/runs").json()}
    listed = bob.get("/runs").json()
    assert rid not in {r["run_id"] for r in listed}
    assert all(r["is_golden"] for r in listed)
    # golden demo runs stay readable by anyone
    assert bob.get("/runs/golden_robert_tsla").status_code == 200


def test_api_docs_are_not_public():
    client = TestClient(app)
    assert client.get("/openapi.json").status_code in (404, 200) and "openapi" not in client.get("/openapi.json").text[:200]
    assert "swagger" not in client.get("/docs").text.lower()


def test_rate_limit_per_ip(monkeypatch):
    from alphaforge.api import server

    monkeypatch.setattr(server, "RATE_LIMIT_RUNS", 2)
    monkeypatch.setattr(server, "_rate", server.defaultdict(server.deque))
    client = TestClient(app)
    body = {"persona": "robert", "request_text": PERSONAS["robert"]["example_request"]}
    codes = [client.post("/runs", json=body).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
