"""FastAPI backend with SSE (PRD 6). Track C owned."""

from __future__ import annotations

import abc
import asyncio
import datetime as dt
import hmac
import json
import logging
import os
import re
import secrets
import threading
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import cookie_parser

from alphaforge.graph import (
    _cfg,
    get_graph,
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

SESSION_MAX_AGE = 7 * 24 * 3600
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9._~-]{1,128}$")

# In-memory, per-process abuse protection. The run store is per-process too, so this
# matches the existing deployment model without adding a new AWS dependency.
_limit_lock = threading.Lock()
_rate_windows: dict[str, deque[float]] = {}
_daily_date: dt.date | None = None
_daily_count = 0


def _session_cookie_name() -> str:
    return os.getenv("AF_SESSION_COOKIE", "af_session")


def _valid_session_id(value: str | None) -> str | None:
    if value and _SESSION_ID_RE.fullmatch(value):
        return value
    return None


def _session_from_request(headers: Headers) -> str | None:
    """Read a caller-supplied session id from the cookie or an API header."""
    cookies = cookie_parser(headers.get("cookie", ""))
    session_id = _valid_session_id(
        cookies.get(_session_cookie_name()) or cookies.get("session_id")
    )
    if session_id:
        return session_id
    return _valid_session_id(headers.get("x-session-id"))


class SessionMiddleware:
    """Issue a demo session cookie and expose it as request.state.session_id."""

    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        session_id = _session_from_request(headers)
        needs_cookie = session_id is None
        if session_id is None:
            session_id = secrets.token_urlsafe(32)

        scope.setdefault("state", {})["session_id"] = session_id

        if not needs_cookie and headers.get("x-session-id") is None:
            await self.app(scope, receive, send)
            return

        cookie = (
            f"{_session_cookie_name()}={quote(session_id, safe='')}; "
            f"Path=/; Max-Age={SESSION_MAX_AGE}; HttpOnly; SameSite=Lax"
        )
        if os.getenv("AF_SESSION_SECURE", "").lower() in ("1", "true", "yes"):
            cookie += "; Secure"

        async def send_with_cookie(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append("set-cookie", cookie)
            await send(message)

        await self.app(scope, receive, send_with_cookie)


def _request_session_id(request: Request) -> str:
    return request.state.session_id


def _configured_demo_token() -> str | None:
    for name in ("AF_DEMO_TOKEN", "AF_API_TOKEN"):
        value = os.getenv(name)
        if value:
            return value
    return None


def _supplied_demo_token(request: Request) -> str | None:
    token = request.headers.get("x-demo-token") or request.headers.get("x-api-token")
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        token = cookie_parser(request.headers.get("cookie", "")).get("af_demo_token")
    return token or None


def _require_write_access(request: Request) -> None:
    """Optional shared demo token, enabled by AF_DEMO_TOKEN in deployments."""
    expected = _configured_demo_token()
    if not expected:
        return
    supplied = _supplied_demo_token(request)
    if supplied is None or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid demo token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _env_int(names: tuple[str, ...], default: int) -> int:
    for name in names:
        value = os.getenv(name)
        if value is None or not value.strip():
            continue
        try:
            return int(value)
        except ValueError:
            logging.warning("Ignoring invalid %s=%r", name, value)
    return default


def _rate_limit_per_minute() -> int:
    return _env_int(
        ("AF_RATE_LIMIT_PER_MINUTE", "AF_RATE_LIMIT", "AF_RUNS_PER_MINUTE"), 5
    )


def _daily_run_cap() -> int:
    return _env_int(
        ("AF_DAILY_RUN_CAP", "AF_DAILY_RUN_LIMIT", "AF_MAX_RUNS_PER_DAY"), 50
    )


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_rate_limit(request: Request) -> None:
    limit = _rate_limit_per_minute()
    if limit <= 0:
        return

    ip = _client_ip(request)
    now = time.monotonic()
    with _limit_lock:
        window = _rate_windows.setdefault(ip, deque())
        while window and now - window[0] >= 60:
            window.popleft()
        if len(window) >= limit:
            retry_after = max(1, int(60 - (now - window[0])))
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: max {limit} run requests per minute per IP",
                headers={"Retry-After": str(retry_after)},
            )
        window.append(now)


def _consume_daily_run_cap() -> None:
    global _daily_count, _daily_date

    cap = _daily_run_cap()
    if cap <= 0:
        return

    today = dt.datetime.now(dt.UTC).date()
    with _limit_lock:
        if _daily_date != today:
            _daily_date = today
            _daily_count = 0
        if _daily_count >= cap:
            raise HTTPException(
                status_code=429,
                detail=f"Daily run cap reached: max {cap} runs per day",
            )
        _daily_count += 1


def reset_limits() -> None:
    """Reset per-process rate/daily counters (used by tests and manual demos)."""
    global _daily_count, _daily_date

    with _limit_lock:
        _rate_windows.clear()
        _daily_date = dt.datetime.now(dt.UTC).date()
        _daily_count = 0


class Run:
    """Represents an execution run and its state/subscribers."""

    def __init__(
        self,
        run_id: str,
        persona: str,
        request_text: str,
        as_of_date: dt.date | None = None,
        created_at: dt.datetime | None = None,
        session_id: str | None = None,
    ):
        self.run_id = run_id
        self.persona = persona
        self.request_text = request_text
        self.as_of_date = as_of_date
        self.session_id = session_id
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
        self,
        persona: str,
        request_text: str,
        as_of_date: dt.date | None = None,
        session_id: str | None = None,
    ) -> Run:
        pass

    @abc.abstractmethod
    def get(self, run_id: str) -> Run | None:
        pass

    @abc.abstractmethod
    def save(self, run: Run) -> None:
        pass

    def list(self) -> list[Run]:
        """Return runs currently held in memory (optional for persistent stores)."""
        return []


class InMemoryRunStore(BaseRunStore):
    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}
        self._lock = threading.Lock()

    def create(
        self,
        persona: str,
        request_text: str,
        as_of_date: dt.date | None = None,
        session_id: str | None = None,
    ) -> Run:
        run_id = uuid.uuid4().hex
        run = Run(
            run_id=run_id,
            persona=persona,
            request_text=request_text,
            as_of_date=as_of_date,
            session_id=session_id,
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

    def list(self) -> list[Run]:
        with self._lock:
            return list(self._runs.values())


store: BaseRunStore = InMemoryRunStore()


def get_store() -> BaseRunStore:
    return store


def set_store(new_store: BaseRunStore) -> None:
    global store
    store = new_store


def _visible_run(run_id: str, session_id: str) -> Run:
    """Return a run owned by this session (or a public/golden run), else 404."""
    run = store.get(run_id) or _rehydrate_run_from_trace_store(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.session_id is not None and run.session_id != session_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


def _rehydrate_run_from_trace_store(run_id: str) -> Run | None:
    """Attempt to restore a Run and its state from the trace store or checkpointer."""
    run = store.get(run_id)
    if run is not None:
        return run

    # 1. Try trace store first (completed runs & golden runs)
    try:
        ts = get_trace_store()
        run_data = ts.get_run(run_id)
        if run_data:
            final_state_data = run_data.get("final_state")
            graph_state = None
            if final_state_data:
                graph_state = GraphState.model_validate(final_state_data)

            as_of_date_val = run_data.get("as_of_date")
            as_of_date = None
            if as_of_date_val:
                try:
                    as_of_date = dt.date.fromisoformat(str(as_of_date_val)[:10])
                except Exception:
                    pass

            run = Run(
                run_id=run_id,
                persona=run_data.get("persona", ""),
                request_text=run_data.get("request_text", ""),
                as_of_date=as_of_date,
                session_id=run_data.get("session_id"),
            )
            run.status = run_data.get("status", "completed")
            run.state = graph_state
            if run.status == "completed":
                run.record_event({"type": "final", "run_id": run.run_id})

            store.save(run)
            return run
    except Exception:
        logging.exception("Failed to rehydrate run %s from trace store", run_id)

    # 2. Try checkpointer (e.g. for paused / interrupted runs after process restart)
    try:
        graph = get_graph()
        thread_state = graph.get_state(_cfg(run_id))
        if thread_state and thread_state.values:
            checkpoint_values = thread_state.values
            as_of_date_val = checkpoint_values.get("as_of_date")
            as_of_date = None
            if isinstance(as_of_date_val, dt.date):
                as_of_date = as_of_date_val
            elif as_of_date_val:
                try:
                    as_of_date = dt.date.fromisoformat(str(as_of_date_val)[:10])
                except Exception:
                    pass

            run = Run(
                run_id=run_id,
                persona=checkpoint_values.get("persona", ""),
                request_text=checkpoint_values.get("request_text", ""),
                as_of_date=as_of_date,
            )
            if thread_state.tasks and any(t.interrupts for t in thread_state.tasks):
                run.status = "interrupted"
                for t in thread_state.tasks:
                    if t.interrupts:
                        val = t.interrupts[0].value
                        run.question = (
                            val.get("question") if isinstance(val, dict) else str(val)
                        )
                        run.record_event(
                            {"type": "interrupt", "question": run.question}
                        )
                        break
            else:
                run.status = "completed"
                run.state = GraphState.model_validate(checkpoint_values)
                run.record_event({"type": "final", "run_id": run.run_id})

            store.save(run)
            return run
    except Exception:
        logging.exception("Failed to rehydrate run %s from checkpointer", run_id)

    return None


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
                        session_id=run.session_id,
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


_PROD = os.getenv("AF_ENV", "dev").strip().lower() in ("prod", "production")
app = FastAPI(
    title="AlphaForge AI API",
    lifespan=lifespan,
    docs_url=None if _PROD else "/docs",
    redoc_url=None if _PROD else "/redoc",
    openapi_url=None if _PROD else "/openapi.json",
)

app.add_middleware(SessionMiddleware)
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
    profile_data: dict[str, Any] | None = None
    user_profile: dict[str, Any] | None = None


class AnswerRequest(BaseModel):
    text: str = Field(..., description="Answer to the clarifying question")


DEMO_PERSONAS = ("amira", "mateo", "robert")
TOLERANCES = {"low", "low_moderate", "moderate", "high"}
CAPACITIES = {"low", "moderate", "high"}


def _custom_persona(data: dict[str, Any], request_text: str) -> dict[str, Any]:
    """Validated persona-table entry for a questionnaire profile (400 on bad values)."""
    tolerance = data.get("risk_tolerance", "moderate")
    capacity = data.get("risk_capacity", "moderate")
    if tolerance not in TOLERANCES:
        raise HTTPException(400, f"risk_tolerance must be one of {sorted(TOLERANCES)}")
    if capacity not in CAPACITIES:
        raise HTTPException(400, f"risk_capacity must be one of {sorted(CAPACITIES)}")
    try:
        horizon = int(data.get("horizon_years", 5))
    except (TypeError, ValueError):
        raise HTTPException(400, "horizon_years must be an integer") from None
    if not 1 <= horizon <= 50:
        raise HTTPException(400, "horizon_years must be between 1 and 50")
    max_loss = data.get("max_loss_pct")
    if max_loss is not None:
        try:
            max_loss = float(max_loss)
        except (TypeError, ValueError):
            max_loss = None
    return {
        "label": str(data.get("label") or "Profil personnalisé"),
        "objective": str(data.get("objective") or "balanced"),
        "horizon_years": horizon,
        "risk_tolerance": tolerance,
        "risk_capacity": capacity,
        "constraints": [str(c) for c in data.get("constraints") or []],
        "preferences": [str(c) for c in data.get("preferences") or []],
        "budget_cad": data.get("budget_cad"),
        "max_loss_pct": max_loss,
        "notes": str(data.get("notes") or ""),
        "example_request": request_text,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/personas")
def get_personas() -> dict[str, dict[str, Any]]:
    return {k: PERSONAS[k] for k in DEMO_PERSONAS}


def _in_memory_run_summary(run: Run) -> dict[str, Any]:
    verification = run.state.verification if run.state is not None else None
    return {
        "run_id": run.run_id,
        "persona": run.persona,
        "as_of_date": str(run.as_of_date or ""),
        "request_text": run.request_text,
        "created_at": run.created_at.isoformat(),
        "status": run.status,
        "verification_passed": bool(verification and verification.get("passed", False)),
        "is_golden": False,
    }


@app.get("/runs")
def list_runs(
    request: Request, persona: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    session_id = _request_session_id(request)
    ts = get_trace_store()
    persisted = ts.list_runs(
        limit=limit,
        persona=persona,
        include_golden=True,
        session_id=session_id,
    )

    owned = [
        _in_memory_run_summary(run)
        for run in store.list()
        if run.session_id == session_id and (not persona or run.persona == persona)
    ]
    seen = {run["run_id"] for run in owned}
    runs = owned + [run for run in persisted if run["run_id"] not in seen]

    golden = [run for run in runs if run.get("is_golden")]
    others = [run for run in runs if not run.get("is_golden")]
    runs = golden + others[: max(0, limit - len(golden))]
    return [{k: v for k, v in run.items() if k != "session_id"} for run in runs]


@app.post("/runs")
def create_run(req: RunCreateRequest, request: Request) -> dict[str, str]:
    _require_write_access(request)
    _check_rate_limit(request)
    session_id = _request_session_id(request)
    persona = req.persona
    if req.profile_data:
        # A questionnaire profile is registered under its own key for this run only,
        # so concurrent users never overwrite each other and the demo personas stay intact.
        persona = f"custom_{uuid.uuid4().hex[:12]}"
        PERSONAS[persona] = _custom_persona(req.profile_data, req.request_text)
    elif persona not in DEMO_PERSONAS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown persona '{persona}'. Allowed: {list(DEMO_PERSONAS)}",
        )
    _consume_daily_run_cap()
    run = store.create(
        persona=persona,
        request_text=req.request_text,
        as_of_date=req.as_of_date,
        session_id=session_id,
    )
    start_run_thread(
        run,
        stream_run,
        initial_state(run.persona, run.request_text, run.as_of_date),
        run.run_id,
    )
    return {"run_id": run.run_id}


@app.get("/runs/{run_id}/events")
async def stream_run_events(run_id: str, request: Request) -> EventSourceResponse:
    run = _visible_run(run_id, _request_session_id(request))

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
def whatif_run(run_id: str, req: WhatIfRequest, request: Request) -> dict[str, str]:
    _require_write_access(request)
    _check_rate_limit(request)
    session_id = _request_session_id(request)
    parent = _visible_run(run_id, session_id)

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

    _consume_daily_run_cap()
    child_run = store.create(
        persona=inputs["persona"],
        request_text=inputs["request_text"],
        as_of_date=inputs["as_of_date"],
        session_id=session_id,
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
def get_run_diff(run_id: str, request: Request) -> dict[str, Any]:
    session_id = _request_session_id(request)
    run = _visible_run(run_id, session_id)
    if run.parent_run_id is None:
        raise HTTPException(status_code=404, detail="What-if run with parent not found")

    parent = _visible_run(run.parent_run_id, session_id)

    if run.state is None or parent.state is None:
        raise HTTPException(status_code=400, detail="Both runs must be completed to diff")

    diff = diff_scenarios(parent.state, run.state)
    diff["change"] = run.change
    diff["parent_run_id"] = parent.run_id
    diff["child_run_id"] = run.run_id
    return diff


@app.get("/runs/compare")
def compare_runs(run_a: str, run_b: str, request: Request) -> dict[str, Any]:
    """Compare two completed runs using diff_scenarios (PRD 7, C-9)."""
    session_id = _request_session_id(request)
    r_a = _visible_run(run_a, session_id)
    r_b = _visible_run(run_b, session_id)
    if r_a.state is None or r_b.state is None:
        raise HTTPException(status_code=400, detail="Both runs must be completed to compare")
    diff = diff_scenarios(r_a.state, r_b.state)
    diff["run_a_id"] = r_a.run_id
    diff["run_b_id"] = r_b.run_id
    return diff


@app.post("/runs/{run_id}/answer")
def answer_run(run_id: str, req: AnswerRequest, request: Request) -> dict[str, str]:
    _require_write_access(request)
    run = _visible_run(run_id, _request_session_id(request))

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
def get_run_state(run_id: str, request: Request):
    run = _visible_run(run_id, _request_session_id(request))

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
