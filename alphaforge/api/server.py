"""FastAPI backend with SSE (PRD 6). Track C owned."""

from __future__ import annotations

import abc
import asyncio
import datetime as dt
import json
import logging
import os
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from alphaforge.graph import (
    get_state,
    initial_state,
    resume_run,
    stream_run,
)
from alphaforge.personas import PERSONAS
from alphaforge.state import GraphState
from alphaforge.trace_store import get_trace_store
from alphaforge.whatif import diff_scenarios, prepare_whatif_inputs

DIST_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


class Run:
    """Represents an execution run and its state/subscribers."""

    def __init__(
        self,
        run_id: str,
        persona: str,
        request_text: str,
        as_of_date: dt.date | None = None,
        created_at: dt.datetime | None = None,
    ):
        self.run_id = run_id
        self.persona = persona
        self.request_text = request_text
        self.as_of_date = as_of_date
        self.created_at = created_at or dt.datetime.now(dt.UTC)
        self.status: Literal["running", "interrupted", "completed", "error"] = "running"
        self.events: list[dict[str, Any]] = []
        self.state: GraphState | None = None
        self.question: str | None = None
        self.error: str | None = None
        self.parent_run_id: str | None = None
        self.change: dict[str, Any] | None = None
        self.subscribers: set[tuple[asyncio.Queue, asyncio.AbstractEventLoop]] = set()
        self._lock = threading.Lock()

    def record_event(self, event: dict[str, Any]) -> None:
        with self._lock:
            self.events.append(event)
            for q, loop in list(self.subscribers):
                try:
                    loop.call_soon_threadsafe(q.put_nowait, event)
                except Exception:  # noqa: BLE001
                    pass
            if event.get("type") in ("final", "error"):
                for q, loop in list(self.subscribers):
                    try:
                        loop.call_soon_threadsafe(q.put_nowait, None)
                    except Exception:  # noqa: BLE001
                        pass
                self.subscribers.clear()

    def add_subscriber(self, q: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> None:
        with self._lock:
            for ev in self.events:
                q.put_nowait(ev)
            if self.status in ("completed", "error"):
                q.put_nowait(None)
            else:
                self.subscribers.add((q, loop))

    def remove_subscriber(
        self, q: asyncio.Queue, loop: asyncio.AbstractEventLoop
    ) -> None:
        with self._lock:
            self.subscribers.discard((q, loop))


class BaseRunStore(abc.ABC):
    @abc.abstractmethod
    def create(
        self, persona: str, request_text: str, as_of_date: dt.date | None = None
    ) -> Run:
        pass

    @abc.abstractmethod
    def get(self, run_id: str) -> Run | None:
        pass

    @abc.abstractmethod
    def save(self, run: Run) -> None:
        pass


class InMemoryRunStore(BaseRunStore):
    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}
        self._lock = threading.Lock()

    def create(
        self, persona: str, request_text: str, as_of_date: dt.date | None = None
    ) -> Run:
        run_id = uuid.uuid4().hex
        run = Run(
            run_id=run_id,
            persona=persona,
            request_text=request_text,
            as_of_date=as_of_date,
        )
        with self._lock:
            self._runs[run_id] = run
        return run

    def get(self, run_id: str) -> Run | None:
        with self._lock:
            return self._runs.get(run_id)

    def save(self, run: Run) -> None:
        with self._lock:
            self._runs[run.run_id] = run


store: BaseRunStore = InMemoryRunStore()


def get_store() -> BaseRunStore:
    return store


def set_store(new_store: BaseRunStore) -> None:
    global store
    store = new_store


def _run_worker(run: Run, gen_fn: Any, *args: Any) -> None:
    try:
        for item in gen_fn(*args):
            t = item.get("type")
            if t == "final":
                run.state = item.get("state")
                run.status = "completed"
                run.record_event({"type": "final", "run_id": run.run_id})
                try:
                    ts = get_trace_store()
                    ts.save_run(
                        run_id=run.run_id,
                        state=run.state,
                        trace=run.state.trace if hasattr(run.state, "trace") else None,
                        verification=run.state.verification
                        if hasattr(run.state, "verification")
                        else None,
                    )
                except Exception:
                    logging.exception("Failed to persist trace for run %s", run.run_id)
            elif t == "interrupt":
                run.status = "interrupted"
                run.question = item.get("question")
                run.record_event(item)
            else:
                run.record_event(item)
    except Exception as exc:  # noqa: BLE001
        run.status = "error"
        run.error = str(exc)
        run.record_event({"type": "error", "error": str(exc), "message": str(exc)})


def start_run_thread(run: Run, gen_fn: Any, *args: Any) -> threading.Thread:
    thread = threading.Thread(
        target=_run_worker,
        args=(run, gen_fn, *args),
        daemon=True,
    )
    thread.start()
    return thread


@asynccontextmanager
async def lifespan(_: FastAPI):
    bucket = os.getenv("AF_S3_BUCKET")
    if bucket:
        try:
            from infra.sync_s3 import pull_caches

            pull_caches(bucket_name=bucket)
        except Exception:
            logging.exception("Failed to pull caches from S3 bucket %s", bucket)
    yield


app = FastAPI(title="AlphaForge AI API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunCreateRequest(BaseModel):
    persona: str
    request_text: str = ""
    as_of_date: dt.date | None = None


class AnswerRequest(BaseModel):
    text: str = Field(..., description="Answer to the clarifying question")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/personas")
def get_personas() -> dict[str, dict[str, Any]]:
    return PERSONAS


@app.post("/runs")
def create_run(req: RunCreateRequest) -> dict[str, str]:
    if req.persona not in PERSONAS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown persona '{req.persona}'. Allowed: {list(PERSONAS.keys())}",
        )
    run = store.create(
        persona=req.persona,
        request_text=req.request_text,
        as_of_date=req.as_of_date,
    )
    start_run_thread(
        run,
        stream_run,
        initial_state(run.persona, run.request_text, run.as_of_date),
        run.run_id,
    )
    return {"run_id": run.run_id}


@app.get("/runs/{run_id}/events")
async def stream_run_events(run_id: str) -> EventSourceResponse:
    run = store.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    loop = asyncio.get_running_loop()

    async def event_generator():
        q: asyncio.Queue = asyncio.Queue()
        run.add_subscriber(q, loop)
        try:
            while True:
                ev = await q.get()
                if ev is None:
                    break
                yield {"data": json.dumps(ev)}
        finally:
            run.remove_subscriber(q, loop)

    return EventSourceResponse(event_generator())


class WhatIfRequest(BaseModel):
    field: str = Field(..., description="Hypothesis field to change")
    value: Any = Field(..., description="New value for the hypothesis")


@app.post("/runs/{run_id}/whatif")
def whatif_run(run_id: str, req: WhatIfRequest) -> dict[str, str]:
    parent = store.get(run_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="Parent run not found")

    parent_state = parent.state
    if parent_state is None:
        try:
            parent_state = get_state(parent.run_id)
        except Exception:  # noqa: BLE001
            raise HTTPException(
                status_code=400, detail="Parent run state is not available for what-if"
            ) from None

    if parent_state.profile is None:
        raise HTTPException(status_code=400, detail="Parent profile is not established")

    try:
        inputs = prepare_whatif_inputs(
            parent_state, {"field": req.field, "value": req.value}
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from None

    child_run = store.create(
        persona=inputs["persona"],
        request_text=inputs["request_text"],
        as_of_date=inputs["as_of_date"],
    )
    child_run.parent_run_id = parent.run_id
    child_run.change = {"field": req.field, "value": req.value}

    start_run_thread(
        child_run,
        stream_run,
        inputs,
        child_run.run_id,
    )

    return {"run_id": child_run.run_id, "parent_run_id": parent.run_id}


@app.get("/runs/{run_id}/diff")
def get_run_diff(run_id: str) -> dict[str, Any]:
    run = store.get(run_id)
    if run is None or run.parent_run_id is None:
        raise HTTPException(status_code=404, detail="What-if run with parent not found")

    parent = store.get(run.parent_run_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="Parent run not found")

    if run.state is None or parent.state is None:
        raise HTTPException(status_code=400, detail="Both runs must be completed to diff")

    diff = diff_scenarios(parent.state, run.state)
    diff["change"] = run.change
    diff["parent_run_id"] = parent.run_id
    diff["child_run_id"] = run.run_id
    return diff


@app.post("/runs/{run_id}/answer")
def answer_run(run_id: str, req: AnswerRequest) -> dict[str, str]:
    run = store.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    with run._lock:
        if run.status != "interrupted":
            raise HTTPException(
                status_code=400,
                detail=f"Run is not awaiting an answer (current status: {run.status})",
            )
        run.status = "running"

    start_run_thread(
        run,
        resume_run,
        req.text,
        run.run_id,
    )
    return {"run_id": run.run_id, "status": "resumed"}


@app.get("/runs/{run_id}")
def get_run_state(run_id: str):
    run = store.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.state is not None:
        data = run.state.model_dump(mode="json")
        data["run_id"] = run.run_id
        if run.parent_run_id:
            data["parent_run_id"] = run.parent_run_id
            data["change"] = run.change
        return data

    try:
        state = get_state(run.run_id)
        data = state.model_dump(mode="json")
        data["run_id"] = run.run_id
        if run.parent_run_id:
            data["parent_run_id"] = run.parent_run_id
            data["change"] = run.change
        return data
    except Exception:  # noqa: BLE001
        if run.status == "error":
            raise HTTPException(
                status_code=500, detail=run.error or "Run failed with an error"
            ) from None
        return JSONResponse(
            content={"status": "running", "run_id": run.run_id}, status_code=202
        )


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    dist_dir = DIST_DIR.resolve()
    if not dist_dir.is_dir():
        raise HTTPException(status_code=404, detail="Not found")

    target = (dist_dir / full_path).resolve()
    try:
        target.relative_to(dist_dir)
    except ValueError:
        raise HTTPException(status_code=403, detail="Forbidden") from None

    if full_path and target.is_file():
        return FileResponse(target)

    index_file = dist_dir / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)

    raise HTTPException(status_code=404, detail="Not found")
