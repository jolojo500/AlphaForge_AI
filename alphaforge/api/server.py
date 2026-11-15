"""FastAPI + SSE backend (PRD 6). Owned by Track C.

Run it:  uv run uvicorn alphaforge.api.server:app --reload

Each run executes in a background thread and appends numbered events to a list. The SSE
endpoint tails that list, so a client can reconnect and replay from `Last-Event-ID` (or
`?after=N`). A stream ends when the run pauses on a question, finishes, or fails; the client
closes the EventSource at that point and reconnects after answering.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import threading
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from alphaforge import config, whatif
from alphaforge.graph import initial_state, resume_run, stream_run
from alphaforge.personas import PERSONAS
from alphaforge.state import GraphState
from alphaforge.trace_store import TraceStore, get_store

log = logging.getLogger("alphaforge.api")

TERMINAL = {"waiting", "done", "error"}
POLL_SECONDS = 0.05
DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
MAX_REQUEST_CHARS = 2000


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


# ----------------------------------------------------------------------------- models
class RunRequest(BaseModel):
    persona: Literal["amira", "mateo", "robert"]
    request_text: str = Field(default="", max_length=MAX_REQUEST_CHARS)
    as_of_date: dt.date | None = None


class AnswerRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_REQUEST_CHARS)


class WhatIfRequest(BaseModel):
    field: str
    value: Any


# ----------------------------------------------------------------------------- run registry
class Run:
    def __init__(self, run_id: str, persona: str, request_text: str, as_of: dt.date,
                 parent_id: str | None = None, change: dict | None = None):
        self.id = run_id
        self.parent_id = parent_id
        self.persona = persona
        self.request_text = request_text
        self.as_of = as_of
        self.change = change
        self.status = "running"
        self.question: str | None = None
        self.error: str | None = None
        self.events: list[dict] = []
        self.state: GraphState | None = None
        self.state_json: dict | None = None  # set when loaded from the store
        self.live = False  # True only for runs started by this process (they can be resumed)
        self.created_at = self.updated_at = _now()
        self._lock = threading.Lock()

    def emit(self, event: dict) -> None:
        with self._lock:
            self.events.append({"seq": len(self.events) + 1, **event})
            self.updated_at = _now()

    def snapshot_events(self, after: int) -> list[dict]:
        with self._lock:
            return self.events[after:]

    def state_dict(self) -> dict | None:
        if self.state is not None:
            return self.state.model_dump(mode="json")
        return self.state_json

    def record(self) -> dict:
        return {
            "run_id": self.id, "parent_run_id": self.parent_id, "persona": self.persona,
            "request_text": self.request_text, "as_of_date": self.as_of.isoformat(),
            "change": self.change, "status": self.status, "question": self.question,
            "error": self.error, "events": list(self.events), "state": self.state_dict(),
            "created_at": self.created_at, "updated_at": self.updated_at,
        }

    @classmethod
    def from_record(cls, rec: dict) -> Run:
        run = cls(rec["run_id"], rec["persona"], rec["request_text"],
                  dt.date.fromisoformat(rec["as_of_date"]), rec.get("parent_run_id"), rec.get("change"))
        run.status, run.question, run.error = rec["status"], rec.get("question"), rec.get("error")
        run.events, run.state_json = rec.get("events", []), rec.get("state")
        run.created_at, run.updated_at = rec.get("created_at", run.created_at), rec.get("updated_at", run.updated_at)
        return run


class RunManager:
    def __init__(self, store: TraceStore, graph=None):
        self.store = store
        self.graph = graph
        self.runs: dict[str, Run] = {}

    def get(self, run_id: str) -> Run | None:
        run = self.runs.get(run_id)
        if run is None:
            try:
                rec = self.store.load(run_id)
            except ValueError:  # malformed id
                return None
            if rec:
                run = self.runs[run_id] = Run.from_record(rec)
        return run

    def _save(self, run: Run) -> None:
        try:
            self.store.save(run.id, run.record())
        except Exception:
            log.exception("could not persist run %s", run.id)

    def _drive(self, run: Run, events: Iterator[dict]) -> None:
        """Worker body: turn graph events into numbered run events."""
        try:
            for ev in events:
                if ev["type"] == "trace":
                    run.emit(ev)
                elif ev["type"] == "interrupt":
                    run.question = ev["question"]
                    run.status = "waiting"
                    run.emit({"type": "interrupt", "question": ev["question"]})
                    break
                elif ev["type"] == "final":
                    run.state, run.question = ev["state"], None
                    run.status = "done"
                    run.emit({"type": "final", "run_id": run.id})
        except Exception as exc:
            log.exception("run %s failed", run.id)
            run.status, run.error = "error", f"{type(exc).__name__}"
            run.emit({"type": "error", "message": "Erreur interne pendant l'analyse."})
        self._save(run)

    def _spawn(self, run: Run, events: Iterator[dict]) -> None:
        threading.Thread(target=self._drive, args=(run, events), daemon=True, name=f"run-{run.id}").start()

    def start(self, req: RunRequest) -> Run:
        as_of = req.as_of_date or config.DEFAULT_AS_OF
        run = Run(uuid.uuid4().hex, req.persona, req.request_text, as_of)
        run.live = True
        self.runs[run.id] = run
        self._save(run)
        inputs = initial_state(req.persona, req.request_text, as_of)
        self._spawn(run, stream_run(inputs, run.id, self.graph))
        return run

    def answer(self, run: Run, text: str) -> None:
        run.status, run.question = "running", None
        self._spawn(run, resume_run(text, run.id, self.graph))

    def whatif(self, parent: Run, field: str, value: Any) -> Run:
        raw = parent.state or parent.state_json
        if raw is None:
            raise whatif.WhatIfError("Aucun état disponible pour l'analyse d'origine.")
        parent_state = parent.state or GraphState.model_validate(raw)
        inputs = whatif.rerun_inputs(parent_state, field, value)  # raises WhatIfError
        change = whatif.parse_change(field, value)
        run = Run(uuid.uuid4().hex, parent.persona, parent.request_text, inputs["as_of_date"],
                  parent.id, {"field": change.field, "value": _jsonable(change.value)})
        run.live = True
        self.runs[run.id] = run
        self._save(run)
        self._spawn(run, stream_run(inputs, run.id, self.graph))
        return run

    def diff(self, run: Run) -> dict | None:
        parent = self.get(run.parent_id) if run.parent_id else None
        if parent is None or run.state_dict() is None or parent.state_dict() is None:
            return None
        old = parent.state or GraphState.model_validate(parent.state_json)
        new = run.state or GraphState.model_validate(run.state_json)
        return whatif.diff_scenarios(old, new)


def _jsonable(v: Any) -> Any:
    return v.isoformat() if isinstance(v, dt.date) else v


# ----------------------------------------------------------------------------- static files
class SPAStaticFiles(StaticFiles):
    """Static files with a fallback to index.html so client-side routes survive a reload."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except Exception:
            if path.startswith(("runs", "personas", "health")):
                raise
            return FileResponse(Path(self.directory) / "index.html")  # type: ignore[arg-type]


def default_dist() -> Path:
    return Path(os.getenv("AF_FRONTEND_DIST") or config.REPO_ROOT / "frontend" / "dist")


# ----------------------------------------------------------------------------- app factory
def create_app(store: TraceStore | None = None, graph=None, dist: Path | None = None) -> FastAPI:
    app = FastAPI(title="AlphaForge AI", version="0.1.0")
    origins = DEV_ORIGINS + [o for o in os.getenv("AF_CORS_ORIGINS", "").split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"],
                       allow_headers=["*"])
    mgr = RunManager(store or get_store(), graph)
    app.state.manager = mgr

    def need(run_id: str) -> Run:
        run = mgr.get(run_id)
        if run is None:
            raise HTTPException(404, "Analyse introuvable.")
        return run

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/personas")
    def personas() -> list[dict]:
        return [{"id": pid, **p} for pid, p in PERSONAS.items()]

    @app.post("/runs", status_code=201)
    def create_run(req: RunRequest) -> dict:
        if req.as_of_date is not None:
            try:
                whatif.parse_change("as_of_date", req.as_of_date)
            except whatif.WhatIfError as exc:
                raise HTTPException(422, str(exc)) from exc
        return {"run_id": mgr.start(req).id}

    @app.get("/runs/{run_id}/events")
    async def run_events(run_id: str, request: Request, after: int = 0):
        run = need(run_id)
        last = request.headers.get("last-event-id")
        if last and last.isdigit():
            after = max(after, int(last))

        async def stream():
            sent = after
            while True:
                batch = run.snapshot_events(sent)
                for ev in batch:
                    sent = ev["seq"]
                    yield {"id": str(ev["seq"]), "data": json.dumps(ev, ensure_ascii=False)}
                if not batch and run.status in TERMINAL:
                    return
                if await request.is_disconnected():
                    return
                await asyncio.sleep(POLL_SECONDS)

        return EventSourceResponse(stream())

    @app.post("/runs/{run_id}/answer", status_code=202)
    def answer(run_id: str, req: AnswerRequest) -> dict:
        run = need(run_id)
        if run.status != "waiting" or not run.live:
            raise HTTPException(409, "Cette analyse n'attend pas de réponse.")
        mgr.answer(run, req.text)
        return {"run_id": run.id}

    @app.post("/runs/{run_id}/whatif", status_code=201)
    def run_whatif(run_id: str, req: WhatIfRequest) -> dict:
        parent = need(run_id)
        if parent.status != "done" or parent.state_dict() is None:
            raise HTTPException(409, "L'analyse d'origine n'est pas terminée.")
        try:
            child = mgr.whatif(parent, req.field, req.value)
        except whatif.WhatIfError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"run_id": child.id, "parent_run_id": parent.id}

    @app.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        run = need(run_id)
        return {
            "run_id": run.id, "parent_run_id": run.parent_id, "status": run.status,
            "question": run.question, "error": run.error, "persona": run.persona,
            "request_text": run.request_text, "as_of_date": run.as_of.isoformat(),
            "change": run.change, "state": run.state_dict(),
            "diff": mgr.diff(run) if run.status == "done" else None,
        }

    dist = default_dist() if dist is None else dist
    if (dist / "index.html").exists():
        app.mount("/", SPAStaticFiles(directory=str(dist), html=True), name="frontend")
    return app


app = create_app()
