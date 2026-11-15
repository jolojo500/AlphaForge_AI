"""Run persistence for traces and final states (PRD 2, 3.1). Owned by Track C.

One record per run, keyed by run_id. Backends:
- local (default): JSON files under data/runs/ (override with AF_RUNS_DIR)
- dynamodb: one item per run in the table AF_TRACE_TABLE (default "alphaforge-traces")

`AF_TRACE_BACKEND` selects the backend (config.TRACE_BACKEND). The DynamoDB backend is wrapped
so that any AWS failure (for example an expired token) falls back to the local files instead
of failing the run.
"""
from __future__ import annotations

import base64
import gzip
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Protocol

from alphaforge import config

log = logging.getLogger("alphaforge.trace_store")

DEFAULT_TABLE = "alphaforge-traces"
# DynamoDB items are limited to 400 KB: larger records are gzipped.
GZIP_THRESHOLD = 300_000
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class TraceStore(Protocol):
    def save(self, run_id: str, record: dict[str, Any]) -> None: ...
    def load(self, run_id: str) -> dict[str, Any] | None: ...
    def list_ids(self) -> list[str]: ...


def check_run_id(run_id: str) -> str:
    """Run ids become file names, so only a safe alphabet is accepted."""
    if not _ID_RE.match(run_id):
        raise ValueError(f"invalid run id {run_id!r}")
    return run_id


class LocalStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or os.getenv("AF_RUNS_DIR") or config.REPO_ROOT / "data" / "runs")

    def _path(self, run_id: str) -> Path:
        return self.root / f"{check_run_id(run_id)}.json"

    def save(self, run_id: str, record: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self._path(run_id).with_suffix(".tmp")
        tmp.write_text(json.dumps(record, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(self._path(run_id))  # atomic: readers never see a half-written file

    def load(self, run_id: str) -> dict[str, Any] | None:
        try:
            return json.loads(self._path(run_id).read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return None

    def list_ids(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.stem for p in self.root.glob("*.json"))


def _encode(record: dict[str, Any]) -> dict[str, Any]:
    raw = json.dumps(record, ensure_ascii=False, default=str).encode("utf-8")
    if len(raw) > GZIP_THRESHOLD:
        return {"encoding": "gzip+b64", "record": base64.b64encode(gzip.compress(raw)).decode("ascii")}
    return {"encoding": "json", "record": raw.decode("utf-8")}


def _decode(item: dict[str, Any]) -> dict[str, Any]:
    payload = item["record"]
    if item.get("encoding") == "gzip+b64":
        payload = gzip.decompress(base64.b64decode(payload)).decode("utf-8")
    return json.loads(payload)


class DynamoStore:
    """`table` is injectable for tests; otherwise it is created from boto3."""

    def __init__(self, table_name: str | None = None, table=None):
        self.table_name = table_name or os.getenv("AF_TRACE_TABLE", DEFAULT_TABLE)
        if table is None:
            import boto3

            table = boto3.resource("dynamodb", region_name=config.AWS_REGION).Table(self.table_name)
        self.table = table

    def save(self, run_id: str, record: dict[str, Any]) -> None:
        item = {"run_id": check_run_id(run_id), **_encode(record)}
        item["updated_at"] = str(record.get("updated_at", ""))
        self.table.put_item(Item=item)

    def load(self, run_id: str) -> dict[str, Any] | None:
        item = self.table.get_item(Key={"run_id": check_run_id(run_id)}).get("Item")
        return _decode(item) if item else None

    def list_ids(self) -> list[str]:
        ids: list[str] = []
        kwargs: dict[str, Any] = {"ProjectionExpression": "run_id"}
        while True:
            page = self.table.scan(**kwargs)
            ids += [i["run_id"] for i in page.get("Items", [])]
            if "LastEvaluatedKey" not in page:
                return sorted(ids)
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


class ResilientStore:
    """Primary store with a local fallback: a failing AWS call never fails a run."""

    def __init__(self, primary: TraceStore, fallback: TraceStore):
        self.primary, self.fallback = primary, fallback

    def save(self, run_id: str, record: dict[str, Any]) -> None:
        self.fallback.save(run_id, record)  # always keep a local copy
        try:
            self.primary.save(run_id, record)
        except Exception as exc:
            log.warning("trace store primary save failed (%s): kept local copy", type(exc).__name__)

    def load(self, run_id: str) -> dict[str, Any] | None:
        try:
            found = self.primary.load(run_id)
            if found is not None:
                return found
        except Exception as exc:
            log.warning("trace store primary load failed (%s): using local copy", type(exc).__name__)
        return self.fallback.load(run_id)

    def list_ids(self) -> list[str]:
        try:
            return sorted(set(self.primary.list_ids()) | set(self.fallback.list_ids()))
        except Exception:
            return self.fallback.list_ids()


def ensure_table(table_name: str | None = None, client=None) -> str:
    """Create the DynamoDB table if missing (on-demand billing). Returns the table name."""
    import boto3

    name = table_name or os.getenv("AF_TRACE_TABLE", DEFAULT_TABLE)
    client = client or boto3.client("dynamodb", region_name=config.AWS_REGION)
    try:
        client.describe_table(TableName=name)
        return name
    except client.exceptions.ResourceNotFoundException:
        pass
    client.create_table(
        TableName=name,
        AttributeDefinitions=[{"AttributeName": "run_id", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "run_id", "KeyType": "HASH"}],
        BillingMode="PAY_PER_REQUEST",
    )
    client.get_waiter("table_exists").wait(TableName=name)
    return name


_STORE: TraceStore | None = None


def get_store() -> TraceStore:
    global _STORE
    if _STORE is None:
        local = LocalStore()
        if config.TRACE_BACKEND == "dynamodb":
            try:
                _STORE = ResilientStore(DynamoStore(), local)
            except Exception as exc:  # no boto3 config at all
                log.warning("DynamoDB unavailable (%s): using local files", type(exc).__name__)
                _STORE = local
        else:
            _STORE = local
    return _STORE


def reset_store() -> None:
    """Forget the cached store (tests, or after changing env vars)."""
    global _STORE
    _STORE = None
