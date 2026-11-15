import pytest

from alphaforge import config, trace_store
from alphaforge.trace_store import DynamoStore, LocalStore, ResilientStore, check_run_id

REC = {"run_id": "r1", "status": "done", "events": [{"type": "trace", "entry": {"node": "profile"}}],
       "updated_at": "2026-11-14T10:00:00Z", "state": {"a": "é"}}


class FakeTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item):
        self.items[Item["run_id"]] = dict(Item)

    def get_item(self, Key):
        item = self.items.get(Key["run_id"])
        return {"Item": item} if item else {}

    def scan(self, **kw):
        return {"Items": [{"run_id": k} for k in self.items]}


class BrokenStore:
    def save(self, *a):
        raise RuntimeError("ExpiredToken")

    load = list_ids = save


def test_local_roundtrip_and_listing(tmp_path):
    s = LocalStore(tmp_path)
    assert s.load("r1") is None and s.list_ids() == []
    s.save("r1", REC)
    s.save("r2", {**REC, "run_id": "r2"})
    assert s.load("r1") == REC
    assert s.list_ids() == ["r1", "r2"]
    s.save("r1", {**REC, "status": "running"})  # overwrite
    assert s.load("r1")["status"] == "running"
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("bad", ["../etc/passwd", "a/b", "", "x" * 65, "a b"])
def test_run_id_is_validated(tmp_path, bad):
    with pytest.raises(ValueError):
        check_run_id(bad)
    with pytest.raises(ValueError):
        LocalStore(tmp_path).save(bad, REC)


def test_dynamo_roundtrip_and_gzip_for_large_records():
    table = FakeTable()
    s = DynamoStore(table=table)
    s.save("r1", REC)
    assert table.items["r1"]["encoding"] == "json"
    assert s.load("r1") == REC and s.load("nope") is None
    big = {**REC, "state": {"blob": "x" * 400_000}}
    s.save("big", big)
    assert table.items["big"]["encoding"] == "gzip+b64"
    assert len(table.items["big"]["record"]) < 50_000
    assert s.load("big") == big
    assert s.list_ids() == ["big", "r1"]


def test_resilient_store_survives_aws_failure(tmp_path):
    s = ResilientStore(BrokenStore(), LocalStore(tmp_path))
    s.save("r1", REC)  # must not raise
    assert s.load("r1") == REC
    assert s.list_ids() == ["r1"]


def test_resilient_store_prefers_primary_and_merges_ids(tmp_path):
    table = FakeTable()
    primary = DynamoStore(table=table)
    primary.save("remote", {**REC, "run_id": "remote"})
    s = ResilientStore(primary, LocalStore(tmp_path))
    s.save("local", {**REC, "run_id": "local"})
    assert s.load("remote")["run_id"] == "remote"
    assert s.list_ids() == ["local", "remote"]


def test_get_store_backend_selection(tmp_path, monkeypatch):
    monkeypatch.setenv("AF_RUNS_DIR", str(tmp_path))
    monkeypatch.setattr(config, "TRACE_BACKEND", "local")
    trace_store.reset_store()
    assert isinstance(trace_store.get_store(), LocalStore)
    monkeypatch.setattr(config, "TRACE_BACKEND", "dynamodb")
    monkeypatch.setattr(trace_store, "DynamoStore", lambda: DynamoStore(table=FakeTable()))
    trace_store.reset_store()
    assert isinstance(trace_store.get_store(), ResilientStore)
    trace_store.reset_store()


@pytest.mark.live
def test_live_dynamodb_roundtrip(monkeypatch):
    name = "alphaforge-traces-test"
    trace_store.ensure_table(name)
    s = DynamoStore(name)
    s.save("live-1", REC)
    assert s.load("live-1") == REC
