import json
import time

import pytest
from fastapi.testclient import TestClient

from alphaforge.api.server import create_app
from alphaforge.graph import build_graph
from alphaforge.personas import PERSONAS
from alphaforge.trace_store import LocalStore

NODES = {"profile", "screening", "quant", "macro", "events", "scenarios", "red_team", "explain", "verifier"}


@pytest.fixture
def client(tmp_path):
    app = create_app(store=LocalStore(tmp_path / "runs"), graph=build_graph(), dist=tmp_path / "nodist")
    return TestClient(app)


def sse(client, run_id, after=None, headers=None):
    url = f"/runs/{run_id}/events" + (f"?after={after}" if after is not None else "")
    events = []
    with client.stream("GET", url, headers=headers or {}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
    return events


def start(client, persona, text=None, **extra):
    body = {"persona": persona, "request_text": PERSONAS[persona]["example_request"] if text is None else text, **extra}
    r = client.post("/runs", json=body)
    assert r.status_code == 201, r.text
    return r.json()["run_id"]


def wait_done(client, run_id):
    for _ in range(100):
        data = client.get(f"/runs/{run_id}").json()
        if data["status"] != "running":
            return data
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_health_and_personas(client):
    assert client.get("/health").json() == {"status": "ok"}
    personas = client.get("/personas").json()
    assert {p["id"] for p in personas} == {"amira", "mateo", "robert"}
    assert all(p["label"] and p["example_request"] and p["risk_tolerance"] for p in personas)


def test_cors_allows_vite_dev_origin_only(client):
    ok = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    other = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_full_run_streams_one_trace_per_node_then_final(client):
    run_id = start(client, "robert")
    events = sse(client, run_id)
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert {e["entry"]["node"] for e in events if e["type"] == "trace"} == NODES
    assert events[-1] == {"seq": len(events), "type": "final", "run_id": run_id}
    data = client.get(f"/runs/{run_id}").json()
    assert data["status"] == "done" and data["diff"] is None
    state = data["state"]
    assert state["profile"]["requested_idea"] == {"ticker": "TSLA", "weight": 0.25}
    assert state["verification"]["passed"] is True
    assert len(state["scenarios"]) == 3 and state["evidence"]


def test_sse_replay_from_last_event_id_and_query(client):
    run_id = start(client, "amira")
    full = sse(client, run_id)
    tail = sse(client, run_id, headers={"Last-Event-ID": "5"})
    assert [e["seq"] for e in tail] == [e["seq"] for e in full[5:]]
    assert [e["seq"] for e in sse(client, run_id, after=len(full))] == []
    assert sse(client, run_id, after=len(full) - 1)[0]["type"] == "final"


def test_interrupt_answer_and_resume(client):
    run_id = start(client, "amira", text="")
    events = sse(client, run_id)
    assert events[-1]["type"] == "interrupt" and events[-1]["question"]
    data = client.get(f"/runs/{run_id}").json()
    assert data["status"] == "waiting" and data["question"] == events[-1]["question"]
    r = client.post(f"/runs/{run_id}/answer", json={"text": PERSONAS["amira"]["example_request"]})
    assert r.status_code == 202
    rest = sse(client, run_id, after=events[-1]["seq"])
    assert rest[-1]["type"] == "final" and rest[0]["seq"] == events[-1]["seq"] + 1
    done = client.get(f"/runs/{run_id}").json()
    assert done["status"] == "done" and done["state"]["request_text"] == PERSONAS["amira"]["example_request"]


def test_answer_rejected_when_not_waiting(client):
    run_id = start(client, "robert")
    wait_done(client, run_id)
    assert client.post(f"/runs/{run_id}/answer", json={"text": "x"}).status_code == 409
    assert client.post(f"/runs/{run_id}/answer", json={"text": ""}).status_code == 422


def test_whatif_creates_linked_run_with_diff(client):
    parent = start(client, "robert")
    wait_done(client, parent)
    r = client.post(f"/runs/{parent}/whatif", json={"field": "exclude_ticker", "value": "XIU.TO"})
    assert r.status_code == 201 and r.json()["parent_run_id"] == parent
    child = r.json()["run_id"]
    events = sse(client, child)
    assert "profile" not in {e["entry"]["node"] for e in events if e["type"] == "trace"}
    data = wait_done(client, child)
    assert data["parent_run_id"] == parent and data["change"] == {"field": "exclude_ticker", "value": "XIU.TO"}
    assert data["diff"]["eligible_universe"]["removed"] == ["XIU.TO"]
    assert set(data["diff"]["scenarios"]) == {"as_requested", "capped", "profile_baseline"}


@pytest.mark.parametrize(
    "body", [{"field": "horizon_years", "value": 0}, {"field": "nope", "value": 1}, {"field": "as_of_date", "value": "2031-01-01"}]
)
def test_whatif_validation_errors_are_422(client, body):
    parent = start(client, "robert")
    wait_done(client, parent)
    assert client.post(f"/runs/{parent}/whatif", json=body).status_code == 422


def test_whatif_requires_finished_parent(client):
    run_id = start(client, "amira", text="")
    sse(client, run_id)  # now waiting
    r = client.post(f"/runs/{run_id}/whatif", json={"field": "horizon_years", "value": 5})
    assert r.status_code == 409


def test_input_validation_and_unknown_ids(client):
    assert client.post("/runs", json={"persona": "bob", "request_text": "x"}).status_code == 422
    assert client.post("/runs", json={"persona": "amira", "request_text": "x" * 2001}).status_code == 422
    assert client.post("/runs", json={"persona": "amira", "as_of_date": "2035-01-01"}).status_code == 422
    for path in ("/runs/nope", "/runs/nope/events", "/runs/..%2Fetc/events"):
        assert client.get(path).status_code == 404
    assert client.post("/runs/nope/whatif", json={"field": "horizon_years", "value": 5}).status_code == 404


def test_runs_survive_a_restart_through_the_store(client, tmp_path):
    run_id = start(client, "robert")
    original = wait_done(client, run_id)
    fresh = TestClient(create_app(store=LocalStore(tmp_path / "runs"), graph=build_graph(), dist=tmp_path / "nodist"))
    again = fresh.get(f"/runs/{run_id}").json()
    assert again["status"] == "done" and again["state"] == original["state"]
    assert [e["type"] for e in sse(fresh, run_id)][-1] == "final"
    r = fresh.post(f"/runs/{run_id}/whatif", json={"field": "horizon_years", "value": 8})
    assert r.status_code == 201  # what-if works from a persisted state


def test_node_failure_becomes_an_error_event(tmp_path):
    class Boom:
        def stream(self, *a, **k):
            raise RuntimeError("secret internal detail")

    c = TestClient(create_app(store=LocalStore(tmp_path / "r"), graph=Boom(), dist=tmp_path / "x"))
    run_id = start(c, "robert")
    events = sse(c, run_id)
    assert events[-1]["type"] == "error" and "secret" not in json.dumps(events)
    data = c.get(f"/runs/{run_id}").json()
    assert data["status"] == "error" and data["state"] is None


def test_frontend_is_served_with_spa_fallback(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "a.js").write_text("console.log(1)")
    c = TestClient(create_app(store=LocalStore(tmp_path / "r"), graph=build_graph(), dist=dist))
    assert c.get("/").text == "<html>app</html>"
    assert c.get("/assets/a.js").text == "console.log(1)"
    assert c.get("/some/client/route").text == "<html>app</html>"
    assert c.get("/health").json() == {"status": "ok"}  # API routes win over static files
