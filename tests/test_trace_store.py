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


def test_dynamodb_trace_store_with_s3_offloading():
    """Verify DynamoDB 400 KB limit handling: state offloaded to S3."""
    items_db = {}
    s3_objects = {}

    table_stub = MagicMock()
    table_stub.put_item.side_effect = lambda Item: items_db.update({Item["run_id"]: Item})
    table_stub.get_item.side_effect = lambda Key: {"Item": items_db.get(Key["run_id"])}

    s3_stub = MagicMock()

    def mock_put_object(Bucket, Key, Body, ContentType):
        s3_objects[f"{Bucket}/{Key}"] = Body

    def mock_get_object(Bucket, Key):
        body = s3_objects[f"{Bucket}/{Key}"]
        mock_body = MagicMock()
        mock_body.read.return_value = body
        return {"Body": mock_body}

    s3_stub.put_object.side_effect = mock_put_object
    s3_stub.get_object.side_effect = mock_get_object

    store = DynamoDBTraceStore(
        table_name="test-table",
        region_name="us-east-1",
        table_resource=table_stub,
        s3_bucket="test-bucket",
        s3_client=s3_stub,
    )

    state = run("robert", PERSONAS["robert"]["example_request"])
    store.save_run("robert-s3-run", state)

    # Check that DynamoDB item contains s3_state_key and NO final_state_json
    raw_item = items_db["robert-s3-run"]
    assert "s3_state_key" in raw_item
    assert raw_item["s3_state_key"] == "runs/robert-s3-run.json"
    assert "final_state_json" not in raw_item

    # Check that S3 object exists
    assert "test-bucket/runs/robert-s3-run.json" in s3_objects

    # Check get_run retrieves full state from S3 transparently
    retrieved = store.get_run("robert-s3-run")
    assert retrieved is not None
    assert retrieved["run_id"] == "robert-s3-run"
    assert retrieved["persona"] == "robert"
    assert retrieved["final_state"]["persona"] == "robert"



def test_get_trace_store_factory(monkeypatch):
    monkeypatch.setenv("AF_TRACE_BACKEND", "local")
    store = get_trace_store()
    assert isinstance(store, LocalJsonTraceStore)

    monkeypatch.setenv("AF_TRACE_BACKEND", "dynamodb")
    store_ddb = get_trace_store()
    assert isinstance(store_ddb, DynamoDBTraceStore)


def test_golden_runs_fixtures():
    from alphaforge.trace_store import get_golden_run, load_golden_runs

    runs = load_golden_runs()
    assert len(runs) >= 3
    run_ids = {r["run_id"] for r in runs}
    assert "golden_robert_tsla" in run_ids
    assert "golden_amira_build" in run_ids
    assert "golden_mateo_build" in run_ids

    # get_golden_run
    robert = get_golden_run("golden_robert_tsla")
    assert robert is not None
    assert robert["persona"] == "robert"
    assert "final_state" in robert
    assert len(robert["final_state"]["scenarios"]) == 3

    # list_runs with include_golden=True
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = LocalJsonTraceStore(storage_dir=tmp_dir)
        all_runs = store.list_runs(include_golden=True)
        assert len(all_runs) >= 3

        filtered = store.list_runs(persona="amira", include_golden=True)
        assert all(r["persona"] == "amira" for r in filtered)
        assert any(r["run_id"] == "golden_amira_build" for r in filtered)


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


def test_golden_runs_survive_the_limit(tmp_path):
    from alphaforge.trace_store import LocalJsonTraceStore

    store = LocalJsonTraceStore(storage_dir=tmp_path)
    for i in range(60):
        (tmp_path / f"r{i}.json").write_text(
            '{"run_id": "r%d", "persona": "robert", "verification": {"passed": true}}' % i,
            encoding="utf-8",
        )
    runs = store.list_runs(limit=50, include_golden=True)
    assert len(runs) == 50
    assert {"golden_robert_tsla", "golden_amira_build", "golden_mateo_build"} <= {
        r["run_id"] for r in runs
    }
    assert all(r["is_golden"] for r in runs[:3])
