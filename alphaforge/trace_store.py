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


def _golden_first(runs: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Golden demo runs always listed first, so the replay safety net is never cut off by `limit`."""
    golden = [r for r in runs if r.get("is_golden")]
    others = [r for r in runs if not r.get("is_golden")]
    return golden + others[: max(0, limit - len(golden))]

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
    def list_runs(
        self,
        limit: int = 50,
        persona: str | None = None,
        include_golden: bool = False,
    ) -> list[dict[str, Any]]:
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


GOLDEN_RUNS_DIR = config.REPO_ROOT / "tests" / "fixtures" / "golden_runs"


def load_golden_runs() -> list[dict[str, Any]]:
    """Load pre-recorded golden demo runs from tests/fixtures/golden_runs."""
    runs = []
    if GOLDEN_RUNS_DIR.is_dir():
        for path in sorted(GOLDEN_RUNS_DIR.glob("*.json")):
            try:
                runs.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:  # noqa: BLE001
                pass
    return runs


def get_golden_run(run_id: str) -> dict[str, Any] | None:
    """Find a golden run by its run_id."""
    for run in load_golden_runs():
        if run.get("run_id") == run_id:
            return run
    return None


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
        target.write_text(json.dumps(item, indent=2, ensure_ascii=False), encoding="utf-8")
        return item

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        target = self.storage_dir / f"{run_id}.json"
        if target.is_file():
            return json.loads(target.read_text(encoding="utf-8"))
        return get_golden_run(run_id)

    def list_runs(
        self,
        limit: int = 50,
        persona: str | None = None,
        include_golden: bool = False,
    ) -> list[dict[str, Any]]:
        runs = []
        seen = set()
        for file_path in sorted(
            self.storage_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                rid = data.get("run_id")
                p = data.get("persona", "")
                if persona and p != persona:
                    continue
                if rid and rid not in seen:
                    seen.add(rid)
                    v = data.get("verification") or {}
                    runs.append(
                        {
                            "run_id": rid,
                            "persona": p,
                            "as_of_date": data.get("as_of_date", ""),
                            "request_text": data.get("request_text", ""),
                            "created_at": data.get("created_at", ""),
                            "status": data.get("status", "completed"),
                            "verification_passed": v.get("passed", False) if isinstance(v, dict) else bool(v),
                            "is_golden": bool(data.get("is_golden", rid.startswith("golden_"))),
                        }
                    )
            except Exception:  # noqa: BLE001
                pass

        if include_golden:
            for golden in load_golden_runs():
                rid = golden.get("run_id")
                p = golden.get("persona", "")
                if persona and p != persona:
                    continue
                if rid and rid not in seen:
                    seen.add(rid)
                    v = golden.get("verification") or {}
                    runs.append(
                        {
                            "run_id": rid,
                            "persona": p,
                            "as_of_date": golden.get("as_of_date", ""),
                            "request_text": golden.get("request_text", ""),
                            "created_at": golden.get("created_at", ""),
                            "status": golden.get("status", "completed"),
                            "verification_passed": v.get("passed", False) if isinstance(v, dict) else bool(v),
                            "is_golden": True,
                        }
                    )

        return _golden_first(runs, limit)


class DynamoDBTraceStore(TraceStore):
    """AWS DynamoDB backend for run and trace persistence.

    To respect DynamoDB's 400 KB item limit, when `s3_bucket` (or env `AF_S3_BUCKET`)
    is configured, the full graph state is stored in S3 at `s3://<bucket>/runs/<run_id>.json`
    and DynamoDB stores the trace, verification, and S3 pointer.
    """

    def __init__(
        self,
        table_name: str | None = None,
        region_name: str | None = None,
        session: boto3.Session | None = None,
        table_resource: Any = None,
        s3_bucket: str | None = None,
        s3_client: Any = None,
    ) -> None:
        self.table_name = table_name or os.getenv(
            "AF_DYNAMODB_TABLE", "alphaforge-traces"
        )
        self.region_name = region_name or os.getenv("AWS_REGION", "us-east-1")
        self.s3_bucket = s3_bucket or os.getenv("AF_S3_BUCKET")

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

        if s3_client is not None:
            self._s3 = s3_client
        elif self.s3_bucket:
            if session is None:
                profile = os.getenv("AWS_PROFILE")
                if profile:
                    session = boto3.Session(
                        profile_name=profile, region_name=self.region_name
                    )
                else:
                    session = boto3.Session(region_name=self.region_name)
            self._s3 = session.client("s3", region_name=self.region_name)
        else:
            self._s3 = None

    def save_run(
        self,
        run_id: str,
        state: GraphState | dict[str, Any],
        trace: list[dict[str, Any]] | None = None,
        verification: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        item = _prepare_item(run_id, state, trace, verification)

        db_item = {
            "run_id": item["run_id"],
            "persona": item["persona"],
            "as_of_date": item["as_of_date"],
            "request_text": item["request_text"],
            "created_at": item["created_at"],
            "status": item["status"],
            "trace_json": json.dumps(item["trace"], ensure_ascii=False),
            "verification_json": json.dumps(item["verification"], ensure_ascii=False),
            "verification_passed": (item.get("verification") or {}).get("passed", False),
        }

        # To prevent exceeding DynamoDB 400 KB item limit with large states (evidence, quant metrics),
        # offload full state to S3 when bucket is configured.
        if self.s3_bucket and self._s3 is not None:
            s3_key = f"runs/{run_id}.json"
            state_json = json.dumps(item["final_state"], ensure_ascii=False)
            self._s3.put_object(
                Bucket=self.s3_bucket,
                Key=s3_key,
                Body=state_json.encode("utf-8"),
                ContentType="application/json",
            )
            db_item["s3_state_key"] = s3_key
            db_item["s3_bucket"] = self.s3_bucket
        else:
            db_item["final_state_json"] = json.dumps(item["final_state"], ensure_ascii=False)

        self._table.put_item(Item=db_item)
        return item

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        raw = None
        try:
            resp = self._table.get_item(Key={"run_id": run_id})
            raw = resp.get("Item")
        except Exception:
            raw = None

        if not raw:
            return get_golden_run(run_id)

        trace = json.loads(raw.get("trace_json", "[]"))
        verification = json.loads(raw.get("verification_json", "null"))

        final_state: dict[str, Any] = {}
        if "s3_state_key" in raw and self._s3 is not None:
            bucket = raw.get("s3_bucket") or self.s3_bucket
            s3_obj = self._s3.get_object(Bucket=bucket, Key=raw["s3_state_key"])
            body_content = s3_obj["Body"].read()
            if isinstance(body_content, bytes):
                body_content = body_content.decode("utf-8")
            final_state = json.loads(body_content)
        elif "final_state_json" in raw:
            final_state = json.loads(raw["final_state_json"])

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

    def list_runs(
        self,
        limit: int = 50,
        persona: str | None = None,
        include_golden: bool = False,
    ) -> list[dict[str, Any]]:
        items = []
        seen = set()
        try:
            scan_kwargs: dict[str, Any] = {"Limit": limit}
            if persona:
                scan_kwargs["FilterExpression"] = "persona = :p"
                scan_kwargs["ExpressionAttributeValues"] = {":p": persona}
            resp = self._table.scan(**scan_kwargs)
            for raw in resp.get("Items", []):
                try:
                    rid = raw["run_id"]
                    seen.add(rid)
                    items.append(
                        {
                            "run_id": rid,
                            "persona": raw.get("persona", ""),
                            "as_of_date": raw.get("as_of_date", ""),
                            "request_text": raw.get("request_text", ""),
                            "created_at": raw.get("created_at", ""),
                            "status": raw.get("status", "completed"),
                            "verification_passed": raw.get("verification_passed", False),
                            "is_golden": raw.get("run_id", "").startswith("golden_"),
                        }
                    )
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass

        if include_golden:
            for golden in load_golden_runs():
                rid = golden.get("run_id")
                p = golden.get("persona", "")
                if persona and p != persona:
                    continue
                if rid and rid not in seen:
                    seen.add(rid)
                    v = golden.get("verification") or {}
                    items.append(
                        {
                            "run_id": rid,
                            "persona": p,
                            "as_of_date": golden.get("as_of_date", ""),
                            "request_text": golden.get("request_text", ""),
                            "created_at": golden.get("created_at", ""),
                            "status": golden.get("status", "completed"),
                            "verification_passed": v.get("passed", False) if isinstance(v, dict) else bool(v),
                            "is_golden": True,
                        }
                    )
        return _golden_first(items, limit)


def get_trace_store() -> TraceStore:
    """Factory returning the active TraceStore based on AF_TRACE_BACKEND."""
    backend = os.getenv("AF_TRACE_BACKEND", config.TRACE_BACKEND).lower()
    if backend == "dynamodb":
        return DynamoDBTraceStore()
    return LocalJsonTraceStore()
