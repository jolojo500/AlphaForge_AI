"""Tests for persistent LangGraph checkpointer and run store rehydration (C-7)."""

import os
import uuid

import pytest
from starlette.testclient import TestClient

from alphaforge.api.server import InMemoryRunStore, app, set_store
from alphaforge.graph import (
    _serde,
    build_graph,
    get_checkpointer,
    get_state,
    initial_state,
    resume_run,
    set_graph,
    stream_run,
)


def setup_function():
    set_store(InMemoryRunStore())
    set_graph(None)


def test_checkpointer_selection(monkeypatch):
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph_checkpoint_aws import DynamoDBSaver

    # Local default returns MemorySaver
    monkeypatch.setenv("AF_CHECKPOINTER", "memory")
    cp_local = get_checkpointer()
    assert isinstance(cp_local, MemorySaver)

    # DynamoDB backend returns DynamoDBSaver
    monkeypatch.setenv("AF_CHECKPOINTER", "dynamodb")
    cp_ddb = get_checkpointer()
    assert isinstance(cp_ddb, DynamoDBSaver)


def test_pause_and_resume_across_checkpointer_instances():
    """Verify that a paused run on checkpointer instance 1 can be resumed

    by a fresh checkpointer instance 2 (simulating process restart).
    """
    from langgraph.checkpoint.memory import MemorySaver

    # Create shared storage backend for fake persistence across saver instances
    shared_saver_1 = MemorySaver(serde=_serde())

    # Build Graph 1 and start an ambiguous run for Robert that pauses on clarifying question
    graph_1 = build_graph(checkpointer=shared_saver_1)
    run_id = f"test-pause-resume-{uuid.uuid4().hex[:8]}"
    inputs = initial_state("robert", "Je veux investir mais je ne sais pas comment.")

    events_1 = list(stream_run(inputs, run_id, graph_1))
    assert len(events_1) == 1
    assert events_1[0]["type"] == "interrupt"
    assert "Que souhaitez-vous faire" in events_1[0]["question"]

    # Verify checkpoint exists in saver 1 storage
    assert run_id in shared_saver_1.storage

    # Process restart: instantiate Saver 2 pointing to the same underlying storage dicts
    shared_saver_2 = MemorySaver(serde=_serde())
    shared_saver_2.storage = shared_saver_1.storage
    shared_saver_2.writes = shared_saver_1.writes
    shared_saver_2.blobs = shared_saver_1.blobs

    # Build Graph 2 (simulating new server process)
    graph_2 = build_graph(checkpointer=shared_saver_2)

    # Resume the interrupted run from Graph 2
    events_2 = list(resume_run("Je veux évaluer l'idée d'ajouter 25% de TSLA", run_id, graph_2))
    assert len(events_2) > 0
    final_event = [e for e in events_2 if e.get("type") == "final"]
    assert len(final_event) == 1

    final_state = get_state(run_id, graph_2)
    assert final_state.persona == "robert"
    assert len(final_state.scenarios) == 3
    assert (final_state.verification or {}).get("passed") is True


def test_api_rehydration_of_interrupted_run_after_restart():
    """Verify server can rehydrate an interrupted run and answer it after in-memory store empties."""
    from langgraph.checkpoint.memory import MemorySaver

    shared_saver = MemorySaver(serde=_serde())
    shared_graph = build_graph(checkpointer=shared_saver)
    set_graph(shared_graph)

    client = TestClient(app)

    # 1. Create a run that pauses on interrupt
    run_id = client.post(
        "/runs",
        json={"persona": "robert", "request_text": "Je veux investir"},
    ).json()["run_id"]

    # Wait briefly for worker to hit the interrupt
    import time

    for _ in range(20):
        time.sleep(0.1)
        r = client.get(f"/runs/{run_id}")
        if r.status_code == 200 or r.status_code == 202:
            break

    # 2. Simulate server restart: wipe the in-memory run store
    set_store(InMemoryRunStore())
    # Verify in-memory store is completely empty
    from alphaforge.api.server import get_store

    assert get_store().get(run_id) is None

    # 3. Answer the question on the rehydrated run
    ans_resp = client.post(
        f"/runs/{run_id}/answer",
        json={"text": "Je veux évaluer l'idée d'ajouter 25% de TSLA"},
    )
    assert ans_resp.status_code == 200
    assert ans_resp.json()["status"] == "resumed"

    # 4. Wait for run to finish
    state = None
    for _ in range(300):
        time.sleep(0.2)
        r = client.get(f"/runs/{run_id}")
        if r.status_code == 200 and r.json().get("scenarios"):
            state = r.json()
            break

    assert state is not None
    assert state["persona"] == "robert"
    assert len(state["scenarios"]) == 3
    assert state["verification"]["passed"] is True


@pytest.mark.live
def test_live_dynamodb_checkpointer():
    """Live test against AWS DynamoDB checkpoints table (alphaforge-checkpoints)."""
    import boto3
    from langgraph_checkpoint_aws import DynamoDBSaver
    from langgraph_checkpoint_aws.checkpoint.dynamodb.serialization import (
        CheckpointSerializer,
    )

    table_name = os.getenv("AF_CHECKPOINTS_TABLE", "alphaforge-checkpoints")
    region_name = os.getenv("AWS_REGION", "us-east-1")
    session = boto3.Session(region_name=region_name)

    saver1 = DynamoDBSaver(table_name=table_name, session=session)
    serde = _serde()
    saver1.serde = serde
    saver1.serializer = CheckpointSerializer(serde, False)
    saver1.repo.serializer = saver1.serializer

    graph1 = build_graph(checkpointer=saver1)
    run_id = f"live-checkpointer-{uuid.uuid4().hex[:8]}"

    # Run initial ambiguous request that interrupts
    inputs = initial_state("robert", "Je veux investir")
    events = list(stream_run(inputs, run_id, graph1))
    assert len(events) == 1
    assert events[0]["type"] == "interrupt"

    # Simulating new process connecting to the same table
    saver2 = DynamoDBSaver(table_name=table_name, session=session)
    saver2.serde = serde
    saver2.serializer = CheckpointSerializer(serde, False)
    saver2.repo.serializer = saver2.serializer

    graph2 = build_graph(checkpointer=saver2)

    # Resume the interrupted run via graph2
    resume_events = list(
        resume_run(
            "Je veux évaluer l'idée d'ajouter 25% de TSLA",
            run_id,
            graph2,
        )
    )
    assert len(resume_events) > 0
    final_event = [e for e in resume_events if e.get("type") == "final"]
    assert len(final_event) == 1

    final_state = get_state(run_id, graph2)
    assert final_state.persona == "robert"
    assert len(final_state.scenarios) == 3
    assert final_state.verification["passed"] is True
