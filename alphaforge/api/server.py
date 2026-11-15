"""FastAPI backend with SSE (PRD 6). Track C owned."""

from __future__ import annotations

import abc
import asyncio
import datetime as dt
import json
import logging
import os
import threading
import time
import uuid
from collections import defaultdict, deque
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from alphaforge.auth import (
    User,
    authenticate_user,
    get_current_user,
    get_current_user_from_request_or_none,
    register_user,
    require_advisor,
)
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
from alphaforge.suitability import RecordExistsError, get_suitability_store
from alphaforge.trace_store import get_trace_store
from alphaforge.users import get_user_store
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
        self.owner: str | None = None
        self.change: dict[str, Any] | None = None
        self.cost: dict[str, Any] | None = None
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

    def list_owned(self, owner: str) -> list[Run]:
        return []


MAX_RUNS_IN_MEMORY = int(os.getenv("AF_MAX_RUNS_IN_MEMORY", "200"))


class InMemoryRunStore(BaseRunStore):
    """Keeps the most recent runs only (#113); older ones stay readable from the trace store."""

    def __init__(self, max_runs: int = MAX_RUNS_IN_MEMORY) -> None:
        self._runs: dict[str, Run] = {}
        self._lock = threading.Lock()
        self._max = max_runs

    def _evict(self) -> None:
        while len(self._runs) > self._max:
            oldest = next(
                (k for k, r in self._runs.items() if r.status in ("completed", "error")),
                next(iter(self._runs)),
            )
            del self._runs[oldest]

    def list_owned(self, owner: str) -> list[Run]:
        with self._lock:
            runs = [r for r in self._runs.values() if r.owner == owner]
        return sorted(runs, key=lambda r: r.created_at, reverse=True)

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
            self._evict()
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
            )
            run.status = run_data.get("status", "completed")
            run.state = graph_state
            run.cost = run_data.get("cost")
            run.owner = graph_state.owner if graph_state is not None else None
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
            run.owner = checkpoint_values.get("owner")
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
                if run.state and hasattr(run.state, "trace"):
                    from alphaforge.tracing import calculate_run_cost

                    run.cost = calculate_run_cost(run.state.trace)
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

                # Dossier recording for authenticated users (PRD C-16)
                owner = run.owner or (getattr(run.state, "owner", None) if run.state else None)
                if owner and owner.startswith("u:"):
                    username = owner[2:]
                    try:
                        from alphaforge.user_dossier import append_decision

                        append_decision(username, run.state, run_id=run.run_id)
                    except Exception:
                        logging.exception("Failed to append decision to dossier for %s", username)
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


MAX_CONCURRENT_RUNS = int(os.getenv("AF_MAX_CONCURRENT_RUNS", "3"))
MAX_QUEUED_RUNS = int(os.getenv("AF_MAX_QUEUED_RUNS", "12"))
_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_RUNS, thread_name_prefix="run")
_pending = threading.BoundedSemaphore(MAX_CONCURRENT_RUNS + MAX_QUEUED_RUNS)


def start_run_thread(run: Run, gen_fn: Any, *args: Any) -> Future:
    """Queue a run on the bounded worker pool (#113). 429 when the queue is full."""
    if not _pending.acquire(blocking=False):
        raise HTTPException(
            status_code=429,
            detail="Le serveur traite déjà le maximum d'analyses. Réessayez dans une minute.",
        )

    def _job() -> None:
        try:
            _run_worker(run, gen_fn, *args)
        finally:
            _pending.release()

    return _executor.submit(_job)


# --- access control and rate limiting (#111) ---------------------------------------

RATE_LIMIT_RUNS = int(os.getenv("AF_RATE_LIMIT_RUNS", "8"))
RATE_LIMIT_WINDOW_S = int(os.getenv("AF_RATE_LIMIT_WINDOW_S", "600"))
_rate: dict[str, deque] = defaultdict(deque)
_rate_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


def _owner(request: Request) -> str:
    """Owner id: u:<username> if authenticated, c:<client_id> (browser session) or ip otherwise."""
    user = get_current_user_from_request_or_none(request)
    if user:
        return f"u:{user.username}"
    cid = request.headers.get("x-client-id") or request.query_params.get("client") or ""
    cid = cid.strip()[:64]
    return f"c:{cid}" if cid else f"ip:{_client_ip(request)}"


DAILY_RUN_CAP = int(os.getenv("AF_DAILY_RUN_CAP", "300"))
_daily = {"day": None, "count": 0}


def _rate_limit(request: Request) -> None:
    """At most RATE_LIMIT_RUNS model-backed runs per client IP per window, and at most
    DAILY_RUN_CAP runs per UTC day for the whole service (Bedrock budget guard, #111)."""
    key = _client_ip(request)
    now = time.monotonic()
    today = dt.datetime.now(dt.UTC).date()
    with _rate_lock:
        if _daily["day"] != today:
            _daily["day"], _daily["count"] = today, 0
        if _daily["count"] >= DAILY_RUN_CAP:
            raise HTTPException(
                status_code=429,
                detail="Limite quotidienne d'analyses atteinte pour la démonstration. Réessayez demain.",
            )
        q = _rate[key]
        while q and now - q[0] > RATE_LIMIT_WINDOW_S:
            q.popleft()
        if len(q) >= RATE_LIMIT_RUNS:
            raise HTTPException(
                status_code=429,
                detail="Trop d'analyses lancées depuis cette adresse. Réessayez dans quelques minutes.",
            )
        q.append(now)
        _daily["count"] += 1


def _is_golden(run: Run) -> bool:
    return run.run_id.startswith("golden_")


def _authorize(run: Run | None, request: Request, *, write: bool = False) -> Run:
    """404 unless the caller owns the run. Golden demo runs are readable by everyone."""
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if _is_golden(run) and not write:
        return run
    if run.owner is None:
        raise HTTPException(status_code=404, detail="Run not found")
    caller = _owner(request)
    if run.owner == caller:
        return run
    user = get_current_user_from_request_or_none(request)
    if user and run.owner in (f"u:{user.username}", f"u:{user.user_id}"):
        return run
    if user and user.is_advisor and not write:
        return run
    raise HTTPException(status_code=404, detail="Run not found")


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


app = FastAPI(
    title="AlphaForge AI API",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data:; "
        "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    ),
}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Security headers on every response (#112). HTTPS itself is terminated by CloudFront."""
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


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
    current_holdings: dict[str, Any] | str | None = None
    language: Literal["fr", "en"] | None = None


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
    current_holdings = data.get("current_holdings")
    if current_holdings:
        from alphaforge.holdings import parse_holdings

        current_holdings = parse_holdings(current_holdings)
    account_type = str(data.get("account_type") or "non_registered").lower()
    if account_type not in {"tfsa", "rrsp", "fhsa", "non_registered", "mixed"}:
        account_type = "non_registered"
    return {
        "label": str(data.get("label") or "Profil personnalisé"),
        "objective": str(data.get("objective") or "balanced"),
        "horizon_years": horizon,
        "risk_tolerance": tolerance,
        "risk_capacity": capacity,
        "account_type": account_type,
        "constraints": [str(c) for c in data.get("constraints") or []],
        "preferences": [str(c) for c in data.get("preferences") or []],
        "budget_cad": data.get("budget_cad"),
        "max_loss_pct": max_loss,
        "notes": str(data.get("notes") or ""),
        "has_emergency_fund": data.get("has_emergency_fund"),
        "has_high_interest_debt": data.get("has_high_interest_debt"),
        "debt_level": data.get("debt_level"),
        "net_worth_share": data.get("net_worth_share"),
        "net_worth_cad": data.get("net_worth_cad"),
        "liquidity_need_12m": data.get("liquidity_need_12m"),
        "investment_knowledge": data.get("investment_knowledge"),
        "withdrawal_plan": data.get("withdrawal_plan"),
        "income_stability": data.get("income_stability"),
        "example_request": request_text,
        "current_holdings": current_holdings,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/personas")
def get_personas() -> dict[str, dict[str, Any]]:
    return {k: PERSONAS[k] for k in DEMO_PERSONAS}


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)
    email: str | None = Field(default=None, max_length=254)


REGISTER_LIMIT = int(os.getenv("AF_RATE_LIMIT_REGISTER", "5"))


def _register_rate_limit(request: Request) -> None:
    """At most REGISTER_LIMIT sign-ups per client IP per window (separate from the run budget)."""
    key = f"reg:{_client_ip(request)}"
    now = time.monotonic()
    with _rate_lock:
        q = _rate[key]
        while q and now - q[0] > RATE_LIMIT_WINDOW_S:
            q.popleft()
        if len(q) >= REGISTER_LIMIT:
            raise HTTPException(status_code=429, detail="Trop de créations de compte. Réessayez plus tard.")
        q.append(now)


@app.post("/auth/login")
def login_endpoint(req: LoginRequest) -> dict[str, Any]:
    """Authenticate with Cognito or local dev mode (PRD C-14, #128)."""
    return authenticate_user(req.username, req.password)


@app.post("/auth/register")
def register_endpoint(req: RegisterRequest, request: Request) -> dict[str, Any]:
    """Create an account. An existing user's saved profile is never touched."""
    _register_rate_limit(request)
    bundle = register_user(req.username, req.password, req.email)
    try:
        from alphaforge.user_dossier import create_dossier

        create_dossier(username=req.username, email=req.email, profile={})
    except Exception:
        logging.exception("Failed to create dossier for %s", req.username)
    return bundle


@app.get("/auth/me")
def me_endpoint(user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    """Get currently authenticated user identity and profile summary."""
    profile_data = get_user_store().get_user_profile(user.username) or {}
    return {
        "user": user.model_dump(),
        "profile": profile_data.get("profile"),
        "account_type": profile_data.get("account_type"),
        "current_holdings": profile_data.get("current_holdings"),
        "is_advisor": user.is_advisor,
    }


class ProfileUpdateRequest(BaseModel):
    profile: dict[str, Any]
    current_holdings: Any = None
    account_type: str | None = None


@app.get("/user/profile")
def get_user_profile_endpoint(
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Retrieve the authenticated user's profile from the users store."""
    data = get_user_store().get_user_profile(user.username)
    if not data:
        data = {
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "profile": {},
            "account_type": None,
            "current_holdings": None,
            "is_advisor": user.is_advisor,
        }
    return data


@app.put("/user/profile")
def update_user_profile_endpoint(
    req: ProfileUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Update profile, current holdings, and account type in the users store."""
    res = get_user_store().save_user_profile(
        user_id=user.username,
        profile=req.profile,
        current_holdings=req.current_holdings,
        account_type=req.account_type,
        username=user.username,
        email=user.email,
        is_advisor=user.is_advisor,
    )
    try:
        from alphaforge.user_dossier import append_profile_update

        full_profile = dict(req.profile)
        if req.account_type is not None:
            full_profile["account_type"] = req.account_type
        if req.current_holdings is not None:
            full_profile["current_holdings"] = req.current_holdings
        append_profile_update(user.username, full_profile)
    except Exception:
        logging.exception("Failed to append profile update to dossier for %s", user.username)
    return res


@app.get("/users/me/dossier")
def get_user_dossier_endpoint(
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    """Download own user dossier in Markdown format (PRD C-16)."""
    try:
        from alphaforge.user_dossier import read_dossier, sanitize_username

        content = read_dossier(user.username)
    except Exception as exc:
        logging.exception("Failed to read dossier for user %s: %s", user.username, exc)
        raise HTTPException(status_code=500, detail="Erreur lors de la lecture du dossier.") from exc

    if not content:
        raise HTTPException(status_code=404, detail="Dossier introuvable pour cet utilisateur.")

    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="dossier_{sanitize_username(user.username)}.md"',
        },
    )


@app.get("/runs")
def list_runs(request: Request, persona: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Golden demo runs plus the caller's own runs; never other people's requests (#111)."""
    limit = max(1, min(limit, 100))
    if persona in ("custom_user", "me"):
        persona = "custom"  # questionnaire runs are stored under "custom"
    me = _owner(request)
    golden = get_trace_store().list_runs(limit=limit, persona=persona, include_golden=True, owner=me)
    out = [r for r in golden if r.get("is_golden")]
    seen_ids = {r["run_id"] for r in out}

    for r in golden:
        if not r.get("is_golden") and r["run_id"] not in seen_ids:
            seen_ids.add(r["run_id"])
            out.append(r)

    for run in store.list_owned(me):
        if persona and run.persona != persona:
            continue
        if run.run_id in seen_ids:
            continue
        seen_ids.add(run.run_id)
        v = run.state.verification if run.state is not None else None
        out.append(
            {
                "run_id": run.run_id,
                "persona": run.persona,
                "as_of_date": str(run.as_of_date or ""),
                "request_text": run.request_text,
                "created_at": run.created_at.isoformat(),
                "status": run.status,
                "verification_passed": bool(v and v.get("passed")),
                "is_golden": False,
            }
        )
    return out[:limit]


@app.post("/runs")
def create_run(req: RunCreateRequest, request: Request) -> dict[str, str]:
    persona, persona_data = req.persona, None
    user = get_current_user_from_request_or_none(request)
    if req.profile_data:
        # A questionnaire profile travels in the run's own state, never in a global (#113).
        p_data = dict(req.profile_data)
        if req.current_holdings and not p_data.get("current_holdings"):
            p_data["current_holdings"] = req.current_holdings
        persona, persona_data = "custom", _custom_persona(p_data, req.request_text)
    elif req.current_holdings:
        from alphaforge.holdings import parse_holdings

        base = dict(PERSONAS.get(persona, {}))
        base["current_holdings"] = parse_holdings(req.current_holdings)
        persona_data = base
    elif user and persona in ("me", "custom", user.username):
        user_record = get_user_store().get_user_profile(user.username)
        if user_record and user_record.get("profile"):
            p_data = dict(user_record["profile"])
            if user_record.get("current_holdings") and not p_data.get("current_holdings"):
                p_data["current_holdings"] = user_record["current_holdings"]
            persona, persona_data = "custom", _custom_persona(p_data, req.request_text)
        elif persona not in DEMO_PERSONAS:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown persona '{persona}'. Allowed: {list(DEMO_PERSONAS)}",
            )
    elif persona not in DEMO_PERSONAS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown persona '{persona}'. Allowed: {list(DEMO_PERSONAS)}",
        )
    if len(req.request_text) > 4000:
        raise HTTPException(status_code=400, detail="request_text is limited to 4000 characters")
    _rate_limit(request)
    owner = _owner(request)
    run = store.create(
        persona=persona,
        request_text=req.request_text,
        as_of_date=req.as_of_date,
    )
    run.owner = owner
    start_run_thread(
        run,
        stream_run,
        initial_state(
            run.persona,
            run.request_text,
            run.as_of_date,
            persona_data=persona_data,
            owner=owner,
            language=req.language,
        ),
        run.run_id,
    )
    return {"run_id": run.run_id}


@app.get("/runs/{run_id}/events")
async def stream_run_events(run_id: str, request: Request) -> EventSourceResponse:
    run = _authorize(store.get(run_id) or _rehydrate_run_from_trace_store(run_id), request)

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
    parent = _authorize(store.get(run_id) or _rehydrate_run_from_trace_store(run_id), request)

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

    _rate_limit(request)
    child_run = store.create(
        persona=inputs["persona"],
        request_text=inputs["request_text"],
        as_of_date=inputs["as_of_date"],
    )
    child_run.owner = _owner(request)
    inputs["owner"] = child_run.owner
    child_run.parent_run_id = parent.run_id
    child_run.change = {"field": req.field, "value": req.value}

    start_run_thread(
        child_run,
        stream_run,
        inputs,
        child_run.run_id,
    )

    return {"run_id": child_run.run_id, "parent_run_id": parent.run_id}


def _final_state(run: Run) -> GraphState | None:
    """The run's final state, read from the checkpoint if the worker has not stored it yet."""
    if run.state is not None:
        return run.state
    try:
        state = get_state(run.run_id)
    except Exception:  # noqa: BLE001
        return None
    return state if state.verification is not None else None


@app.get("/runs/{run_id}/diff")
def get_run_diff(run_id: str, request: Request) -> dict[str, Any]:
    run = _authorize(store.get(run_id) or _rehydrate_run_from_trace_store(run_id), request)
    if run.parent_run_id is None:
        raise HTTPException(status_code=404, detail="What-if run with parent not found")

    parent = store.get(run.parent_run_id) or _rehydrate_run_from_trace_store(run.parent_run_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="Parent run not found")

    run_state, parent_state = _final_state(run), _final_state(parent)
    if run_state is None or parent_state is None:
        raise HTTPException(status_code=400, detail="Both runs must be completed to diff")

    diff = diff_scenarios(parent_state, run_state)
    diff["change"] = run.change
    diff["parent_run_id"] = parent.run_id
    diff["child_run_id"] = run.run_id
    return diff


@app.post("/runs/{run_id}/answer")
def answer_run(run_id: str, req: AnswerRequest, request: Request) -> dict[str, str]:
    run = _authorize(
        store.get(run_id) or _rehydrate_run_from_trace_store(run_id), request, write=True
    )

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
    run = _authorize(store.get(run_id) or _rehydrate_run_from_trace_store(run_id), request)
    from alphaforge.tracing import calculate_run_cost

    if run.state is not None:
        data = run.state.model_dump(mode="json")
        data["run_id"] = run.run_id
        if run.parent_run_id:
            data["parent_run_id"] = run.parent_run_id
            data["change"] = run.change
        data["cost"] = run.cost or calculate_run_cost(data.get("trace"))
        rec = get_suitability_store().get_record(run.run_id)
        if rec:
            data["reviewed"] = True
            data["reviewer_id"] = rec.get("reviewer_id")
            data["reviewed_at"] = rec.get("reviewed_at")
            data["chosen_scenario"] = rec.get("chosen_scenario")
            data["advisor_rationale"] = rec.get("rationale")
            data["edited_assumptions"] = rec.get("edited_assumptions")
        return data

    try:
        state = get_state(run.run_id)
        data = state.model_dump(mode="json")
        data["run_id"] = run.run_id
        if run.parent_run_id:
            data["parent_run_id"] = run.parent_run_id
            data["change"] = run.change
        data["cost"] = run.cost or calculate_run_cost(data.get("trace"))
        rec = get_suitability_store().get_record(run.run_id)
        if rec:
            data["reviewed"] = True
            data["reviewer_id"] = rec.get("reviewer_id")
            data["reviewed_at"] = rec.get("reviewed_at")
            data["chosen_scenario"] = rec.get("chosen_scenario")
            data["advisor_rationale"] = rec.get("rationale")
            data["edited_assumptions"] = rec.get("edited_assumptions")
        return data
    except Exception:  # noqa: BLE001
        if run.status == "error":
            raise HTTPException(
                status_code=500, detail=run.error or "Run failed with an error"
            ) from None
        return JSONResponse(
            content={"status": "running", "run_id": run.run_id}, status_code=202
        )


class ReviewRunRequest(BaseModel):
    chosen_scenario: str = Field(..., description="Chosen scenario name")
    rationale: str = Field(..., min_length=20, description="Advisor rationale (at least 20 characters)")
    edited_assumptions: dict[str, Any] | None = None


@app.post("/runs/{run_id}/review")
def review_run(
    run_id: str,
    req: ReviewRunRequest,
    user: Annotated[User, Depends(require_advisor)],
) -> dict[str, Any]:
    """Advisor review & sign-off creating an immutable suitability record and S3 PDF (PRD B-14, #121)."""
    run = store.get(run_id) or _rehydrate_run_from_trace_store(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    state = _final_state(run)
    if state is None:
        raise HTTPException(status_code=400, detail="Run must be completed before it can be reviewed")

    scenarios = state.scenarios or []
    scenario_names = [s.name for s in scenarios]
    if req.chosen_scenario not in scenario_names:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid chosen_scenario '{req.chosen_scenario}'. Allowed: {scenario_names}",
        )

    # Build KYC snapshot
    kyc_snapshot = {}
    if state.profile:
        kyc_snapshot = {
            "persona": state.persona,
            "objective": state.profile.objective,
            "horizon_years": state.profile.horizon_years,
            "risk_tolerance": state.profile.risk_tolerance,
            "risk_capacity": state.profile.risk_capacity,
            "budget_cad": state.profile.budget_cad,
            "constraints": state.profile.constraints,
            "preferences": state.profile.preferences,
            "conflicts": state.profile.conflicts,
        }
    if state.persona_data:
        kyc_snapshot["account_type"] = state.persona_data.get("account_type")

    now_iso = dt.datetime.now(dt.UTC).isoformat()
    record = {
        "run_id": run_id,
        "reviewer_id": user.username,
        "reviewed_at": now_iso,
        "chosen_scenario": req.chosen_scenario,
        "rationale": req.rationale.strip(),
        "edited_assumptions": req.edited_assumptions,
        "kyc_snapshot": kyc_snapshot,
        "scenarios": [s.model_dump() if hasattr(s, "model_dump") else s for s in scenarios],
        "model_ids": {
            "main": os.getenv("AF_MODEL_MAIN", "global.anthropic.claude-sonnet-5-5"),
            "fast": os.getenv("AF_MODEL_FAST", "global.anthropic.claude-haiku-5-5"),
        },
        "data_dates": {
            "as_of_date": str(state.as_of_date or dt.date.today()),
        },
        "verifier_result": state.verification or {},
    }

    try:
        saved_record = get_suitability_store().save_record(run_id, record)
    except RecordExistsError:
        raise HTTPException(status_code=409, detail="Cette analyse a déjà été révisée ; le dossier est immuable.") from None

    state.reviewed = True
    state.reviewer_id = user.username
    state.reviewed_at = now_iso
    state.chosen_scenario = req.chosen_scenario
    state.advisor_rationale = req.rationale.strip()
    if req.edited_assumptions:
        state.edited_assumptions = req.edited_assumptions

    if run.owner and getattr(state, "owner", None) is None:
        state.owner = run.owner

    run.state = state

    try:
        get_trace_store().save_run(
            run_id=run.run_id,
            state=state,
            trace=run.events,
            verification=state.verification,
        )
    except Exception:
        pass

    # Append advisor review / decision to dossier (PRD C-16)
    owner = run.owner or getattr(state, "owner", None)
    if owner and owner.startswith("u:"):
        username = owner[2:]
        try:
            from alphaforge.user_dossier import append_decision

            append_decision(username, state, run_id=run.run_id)
        except Exception:
            logging.exception("Failed to append advisor review to dossier for %s", username)

    return {
        "status": "reviewed",
        "run_id": run_id,
        "reviewer_id": user.username,
        "reviewed_at": now_iso,
        "chosen_scenario": req.chosen_scenario,
        "suitability_record": saved_record,
    }


@app.get("/runs/{run_id}/suitability")
def get_suitability_record(run_id: str, request: Request) -> dict[str, Any]:
    """Retrieve immutable suitability determination record."""
    _authorize(store.get(run_id) or _rehydrate_run_from_trace_store(run_id), request)
    rec = get_suitability_store().get_record(run_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Dossier de convenance introuvable pour cette analyse.")
    return rec


@app.get("/runs/{run_id}/suitability/pdf")
def get_suitability_pdf(run_id: str, request: Request) -> Response:
    """Retrieve suitability record signed PDF."""
    _authorize(store.get(run_id) or _rehydrate_run_from_trace_store(run_id), request)
    pdf_bytes = get_suitability_store().get_pdf(run_id)
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="Document PDF de convenance introuvable.")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="dossier_convenance_{run_id}.pdf"'},
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
