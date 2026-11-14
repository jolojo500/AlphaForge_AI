"""Trace helper for nodes (PRD 3.2). Orchestrator-owned."""

from __future__ import annotations

import datetime as dt
import functools
from collections.abc import Callable


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds")


def traced(name: str) -> Callable:
    """Wrap a node so it appends one trace entry.

    The node returns its partial state update plus an optional `summary` key: one
    user-facing sentence (French), never model reasoning. The wrapper removes `summary`
    and turns it into `{"node", "started_at", "ended_at", "summary"}` under `trace`.
    """

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(state, *args, **kwargs):
            started = _now()
            update = dict(fn(state, *args, **kwargs) or {})
            summary = update.pop("summary", "")
            update["trace"] = [
                {"node": name, "started_at": started, "ended_at": _now(), "summary": summary}
            ]
            return update

        return wrapper

    return deco
