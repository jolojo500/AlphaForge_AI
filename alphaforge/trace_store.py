"""Trace and run storage interface with Local JSON and DynamoDB backends (PRD 2, C-5)."""

from __future__ import annotations

import abc
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

import boto3

from alphaforge import config
from alphaforge.state import GraphState


class TraceStore(abc.ABC):
    @abc.abstractmethod
    def save_run(
        self,
        run_id: str,
        state: GraphState | dict[str, Any],
        trace: list[dict[str, Any]] | None = None,
        verification: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Save a finished run with trace, verification, and final state."""
        pass

    @abc.abstractmethod
    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Retrieve a saved run item by run_id."""
        pass

    @abc.abstractmethod
    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        """List recently saved runs."""
        pass


def _prepare_item(
    run_id: str,
    state: GraphState | dict[str, Any],
    trace: list[dict[str, Any]] | None = None,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(state, GraphState):
        state_dict = state.model_dump(mode="json")
    else:
        state_dict = json.loads(json.dumps(state))

    run_trace = trace if trace is not None else state_dict.get("trace", [])
    run_verification = (
        verification if verification is not None else state_dict.get("verification")
    )

    created_at = dt.datetime.now(dt.UTC).isoformat()
    return {
        "run_id": run_id,
        "persona": state_dict.get("persona", "unknown"),
        "as_of_date": str(state_dict.get("as_of_date", "")),
        "request_text": state_dict.get("request_text", ""),
        "created_at": created_at,
        "status": "completed",
        "verification": run_verification,
        "trace": run_trace,
        "final_state": state_dict,
    }


class LocalJsonTraceStore(TraceStore):
    """Local JSON file backend for trace persistence."""

    def __init__(self, storage_dir: Path | str | None = None) -> None:
        if storage_dir is None:
            self.storage_dir = config.REPO_ROOT / "data" / "traces"
        else:
            self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def save_run(
        self,
        run_id: str,
        state: GraphState | dict[str, Any],
        trace: list[dict[str, Any]] | None = None,
        verification: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        item = _prepare_item(run_id, state, trace, verification)
        target = self.storage_dir / f"{run_id}.json"
        target.write_text(json.dumps(item, indent=2, ensure_ascii=False))
        return item

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        target = self.storage_dir / f"{run_id}.json"
        if not target.is_file():
            return None
        return json.loads(target.read_text())

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        runs = []
        for file_path in sorted(
            self.storage_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]:
            try:
                runs.append(json.loads(file_path.read_text()))
            except Exception:  # noqa: BLE001
                pass
        return runs


class DynamoDBTraceStore(TraceStore):
    """AWS DynamoDB backend for run and trace persistence."""

    def __init__(
        self,
        table_name: str | None = None,
        region_name: str | None = None,
        session: boto3.Session | None = None,
        table_resource: Any = None,
    ) -> None:
        self.table_name = table_name or os.getenv(
            "AF_DYNAMODB_TABLE", "alphaforge-traces"
        )
        self.region_name = region_name or os.getenv("AWS_REGION", "us-east-1")

        if table_resource is not None:
            self._table = table_resource
        else:
            if session is None:
                profile = os.getenv("AWS_PROFILE")
                if profile:
                    session = boto3.Session(
                        profile_name=profile, region_name=self.region_name
                    )
                else:
                    session = boto3.Session(region_name=self.region_name)
            dynamodb = session.resource("dynamodb", region_name=self.region_name)
            self._table = dynamodb.Table(self.table_name)

    def save_run(
        self,
        run_id: str,
        state: GraphState | dict[str, Any],
        trace: list[dict[str, Any]] | None = None,
        verification: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        item = _prepare_item(run_id, state, trace, verification)

        # For DynamoDB put_item, store final_state as JSON string to preserve exact floats/dicts
        db_item = {
            "run_id": item["run_id"],
            "persona": item["persona"],
            "as_of_date": item["as_of_date"],
            "request_text": item["request_text"],
            "created_at": item["created_at"],
            "status": item["status"],
            "trace_json": json.dumps(item["trace"], ensure_ascii=False),
            "verification_json": json.dumps(item["verification"], ensure_ascii=False),
            "final_state_json": json.dumps(item["final_state"], ensure_ascii=False),
            "verification_passed": (item.get("verification") or {}).get("passed", False),
        }

        self._table.put_item(Item=db_item)
        return item

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        resp = self._table.get_item(Key={"run_id": run_id})
        raw = resp.get("Item")
        if not raw:
            return None

        # Reconstruct standard item structure
        trace = json.loads(raw.get("trace_json", "[]"))
        verification = json.loads(raw.get("verification_json", "null"))
        final_state = json.loads(raw.get("final_state_json", "{}"))

        return {
            "run_id": raw["run_id"],
            "persona": raw.get("persona", ""),
            "as_of_date": raw.get("as_of_date", ""),
            "request_text": raw.get("request_text", ""),
            "created_at": raw.get("created_at", ""),
            "status": raw.get("status", "completed"),
            "verification": verification,
            "trace": trace,
            "final_state": final_state,
        }

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        # Scan with limit for inspection/audit
        resp = self._table.scan(Limit=limit)
        items = []
        for raw in resp.get("Items", []):
            try:
                items.append(
                    {
                        "run_id": raw["run_id"],
                        "persona": raw.get("persona", ""),
                        "as_of_date": raw.get("as_of_date", ""),
                        "request_text": raw.get("request_text", ""),
                        "created_at": raw.get("created_at", ""),
                        "status": raw.get("status", "completed"),
                        "verification_passed": raw.get("verification_passed", False),
                    }
                )
            except Exception:  # noqa: BLE001
                pass
        return items


def get_trace_store() -> TraceStore:
    """Factory returning the active TraceStore based on AF_TRACE_BACKEND."""
    backend = os.getenv("AF_TRACE_BACKEND", config.TRACE_BACKEND).lower()
    if backend == "dynamodb":
        return DynamoDBTraceStore()
    return LocalJsonTraceStore()
