"""Tests for TraceStore (local JSON and DynamoDB) and S3 sync (C-5)."""

import os
import tempfile
from unittest.mock import MagicMock

import pytest

from alphaforge.graph import run
from alphaforge.personas import PERSONAS
from alphaforge.trace_store import (
    DynamoDBTraceStore,
    LocalJsonTraceStore,
    get_trace_store,
)


def test_local_json_trace_store():
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = LocalJsonTraceStore(storage_dir=tmp_dir)
        state = run("robert", PERSONAS["robert"]["example_request"])

        # Save run
        saved = store.save_run("test-run-123", state)
        assert saved["run_id"] == "test-run-123"
        assert saved["persona"] == "robert"

        # Get run
        retrieved = store.get_run("test-run-123")
        assert retrieved is not None
        assert retrieved["run_id"] == "test-run-123"
        assert retrieved["persona"] == "robert"
        assert len(retrieved["trace"]) > 0
        assert retrieved["verification"]["passed"] is True
        assert retrieved["final_state"]["persona"] == "robert"

        # List runs
        runs = store.list_runs()
        assert len(runs) == 1
        assert runs[0]["run_id"] == "test-run-123"

        # Non-existent run
        assert store.get_run("non-existent") is None


def test_dynamodb_trace_store_with_stub():
    # In-memory stub for DynamoDB Table resource
    items_db = {}

    table_stub = MagicMock()

    def mock_put_item(Item):
        items_db[Item["run_id"]] = Item

    def mock_get_item(Key):
        rid = Key["run_id"]
        return {"Item": items_db.get(rid)}

    def mock_scan(Limit=50):
        return {"Items": list(items_db.values())[:Limit]}

    table_stub.put_item.side_effect = mock_put_item
    table_stub.get_item.side_effect = mock_get_item
    table_stub.scan.side_effect = mock_scan

    store = DynamoDBTraceStore(
        table_name="test-table",
        region_name="us-east-1",
        table_resource=table_stub,
    )

    state = run("amira", PERSONAS["amira"]["example_request"])
    store.save_run("amira-stub-run", state)

    retrieved = store.get_run("amira-stub-run")
    assert retrieved is not None
    assert retrieved["run_id"] == "amira-stub-run"
    assert retrieved["persona"] == "amira"
    assert len(retrieved["trace"]) > 0
    assert retrieved["final_state"]["persona"] == "amira"

    runs = store.list_runs()
    assert len(runs) == 1
    assert runs[0]["run_id"] == "amira-stub-run"


def test_get_trace_store_factory(monkeypatch):
    monkeypatch.setenv("AF_TRACE_BACKEND", "local")
    store = get_trace_store()
    assert isinstance(store, LocalJsonTraceStore)

    monkeypatch.setenv("AF_TRACE_BACKEND", "dynamodb")
    store_ddb = get_trace_store()
    assert isinstance(store_ddb, DynamoDBTraceStore)


@pytest.mark.live
def test_live_dynamodb_read_write():
    """Live test against the real workshop DynamoDB table (alphaforge-traces)."""
    table_name = os.getenv("AF_DYNAMODB_TABLE", "alphaforge-traces")
    region = os.getenv("AWS_REGION", "us-east-1")
    store = DynamoDBTraceStore(table_name=table_name, region_name=region)

    state = run("robert", PERSONAS["robert"]["example_request"])
    run_id = f"live-test-{state.persona}-{int(state.as_of_date.strftime('%Y%m%d'))}"

    store.save_run(run_id, state)
    retrieved = store.get_run(run_id)

    assert retrieved is not None
    assert retrieved["run_id"] == run_id
    assert retrieved["persona"] == "robert"
    assert retrieved["verification"]["passed"] is True
    assert len(retrieved["trace"]) >= 9
