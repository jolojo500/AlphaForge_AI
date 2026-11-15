"""Tests for bounded server state: custom personas, worker pool, run eviction (C-13)."""

from __future__ import annotations

import datetime as dt
import threading
import time
from unittest.mock import patch

from starlette.testclient import TestClient

from alphaforge.api import server
from alphaforge.api.server import InMemoryRunStore, RunPool, app, set_store
from alphaforge.graph import build_graph, initial_state, set_graph
from alphaforge.personas import PERSONAS
from alphaforge.state import GraphState
from alphaforge.trace_store import LocalJsonTraceStore


def _custom(tolerance: str = "moderate", horizon: int = 10) -> dict:
    return {
        "objective": "growth",
        "horizon_years": horizon,
        "risk_tolerance": tolerance,
        "risk_capacity": "moderate",
        "constraints": [],
        "preferences": ["likes_tech"],
        "budget_cad": 50_000,
    }


def _fast_stream(inputs: dict, thread_id: str):
    """Offline stand-in for stream_run: finish immediately with the input state."""
    yield {
        "type": "final",
        "state": GraphState(
            as_of_date=inputs["as_of_date"],
            persona=inputs["persona"],
            request_text=inputs.get("request_text", ""),
            persona_data=inputs.get("persona_data"),
        ),
    }


def _wait_status(run_id: str, status: str, timeout: float = 10) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = server.get_store().get(run_id)
        if run is not None and run.status == status:
            return
        time.sleep(0.02)
    raise AssertionError(f"run {run_id} never reached status {status}")


def _wait_final(client: TestClient, run_id: str, timeout: float = 30) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/runs/{run_id}")
        if resp.status_code == 200 and resp.json().get("verification"):
            return resp.json()
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish")


def test_100_custom_runs_do_not_grow_personas(tmp_path):
    set_store(InMemoryRunStore())
    before = dict(PERSONAS)
    trace_store = LocalJsonTraceStore(tmp_path / "traces")
    client = TestClient(app)

    with (
        patch("alphaforge.api.server.stream_run", _fast_stream),
        patch("alphaforge.api.server.get_trace_store", return_value=trace_store),
    ):
        for _ in range(100):
            resp = client.post(
                "/runs",
                json={
                    "persona": "custom_user",
                    "request_text": "Je veux construire un portefeuille.",
                    "profile_data": _custom(),
                },
            )
            assert resp.status_code == 200

    assert len(PERSONAS) == 3
    assert set(PERSONAS) == set(before)


def test_custom_persona_is_carried_in_graph_state():
    inputs = initial_state("custom_abc", "construire", persona_data=_custom("high", 15))
    assert inputs["persona_data"] == _custom("high", 15)
    assert "custom_abc" not in PERSONAS


def test_custom_persona_survives_restart_for_profile_rerun(tmp_path):
    from langgraph.checkpoint.memory import MemorySaver

    from alphaforge.graph import _serde

    set_store(InMemoryRunStore())
    saver = MemorySaver(serde=_serde())
    set_graph(build_graph(checkpointer=saver))
    trace_store = LocalJsonTraceStore(tmp_path / "traces")
    client = TestClient(app)
    try:
        with patch("alphaforge.api.server.get_trace_store", return_value=trace_store):
            run_id = client.post(
                "/runs",
                json={
                    "persona": "custom_user",
                    "request_text": "",
                    "profile_data": _custom("low", 3),
                },
            ).json()["run_id"]
            _wait_status(run_id, "interrupted")

            # Simulate a process restart: the in-memory run store is empty.
            set_store(InMemoryRunStore())
            assert server.get_store().get(run_id) is None

            resp = client.post(
                f"/runs/{run_id}/answer",
                json={"text": "Je veux construire un portefeuille diversifié."},
            )
            assert resp.status_code == 200

            state = _wait_final(client, run_id)
            assert state["persona"].startswith("custom_")
            assert state["profile"]["risk_tolerance"] == "low"
            assert state["profile"]["horizon_years"] == 3
    finally:
        set_graph(None)


def test_run_pool_bounds_workers_and_queue():
    pool = RunPool(max_workers=1, max_queue=0)
    started = threading.Event()
    release = threading.Event()

    def blocking_job():
        started.set()
        release.wait(5)

    future = pool.submit(blocking_job)
    assert started.wait(2)
    try:
        try:
            pool.submit(lambda: None)
        except server.RunQueueFull:
            pass
        else:
            raise AssertionError("second submission should be rejected when the queue is full")
    finally:
        release.set()
        future.result(5)
        pool.shutdown(wait=False)


def test_queue_full_returns_503_with_retry_after():
    pool = RunPool(max_workers=1, max_queue=0)
    started = threading.Event()
    release = threading.Event()

    def blocking_job():
        started.set()
        release.wait(5)

    future = pool.submit(blocking_job)
    assert started.wait(2)
    set_store(InMemoryRunStore())
    client = TestClient(app)
    try:
        with patch.object(server, "run_pool", pool):
            resp = client.post(
                "/runs",
                json={"persona": "robert", "request_text": "Je veux investir."},
            )
        assert resp.status_code == 503
        assert resp.headers.get("Retry-After")
    finally:
        release.set()
        future.result(5)
        pool.shutdown(wait=False)


def test_finished_runs_are_evicted_after_retention():
    now = dt.datetime.now(dt.UTC)
    store = InMemoryRunStore(retention=dt.timedelta(minutes=5), clock=lambda: now)
    finished = store.create("robert", "done")
    finished.status = "completed"
    finished.finished_at = now - dt.timedelta(minutes=6)
    running = store.create("amira", "still going")

    assert store.get(finished.run_id) is None
    assert store.get(running.run_id) is running


def test_evicted_run_stays_readable_from_trace_store(tmp_path):
    set_store(InMemoryRunStore(retention=dt.timedelta(0)))
    trace_store = LocalJsonTraceStore(tmp_path / "traces")
    client = TestClient(app)

    with patch("alphaforge.api.server.get_trace_store", return_value=trace_store):
        run_id = client.post(
            "/runs",
            json={"persona": "robert", "request_text": PERSONAS["robert"]["example_request"]},
        ).json()["run_id"]
        state = _wait_final(client, run_id)

        assert state["persona"] == "robert"
        assert server.get_store().get(run_id) is None

        # Rehydration reads the completed run back from the trace store.
        again = client.get(f"/runs/{run_id}")
        assert again.status_code == 200
        assert again.json()["persona"] == "robert"
