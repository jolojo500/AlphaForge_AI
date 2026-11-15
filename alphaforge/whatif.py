"""What-if: change ONE hypothesis and rerun (PRD 5.11). Owned by Track C.

The user changes one hypothesis (horizon, budget, tolerance, excluded asset, as-of date).
The graph reruns in full with the modified profile and skips Agent 1. `diff_scenarios`
compares old and new for the side-by-side view.
"""
from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from typing import Any

from alphaforge import config
from alphaforge.evidence import numeric
from alphaforge.graph import initial_state, run
from alphaforge.state import SCENARIO_METRICS, GraphState, Profile

FIELDS = ("horizon_years", "budget_cad", "risk_tolerance", "exclude_ticker", "as_of_date")
TOLERANCES = ("low", "low_moderate", "moderate", "high")
DATA_START = dt.date(2021, 11, 12)  # first day of the starter dataset


class WhatIfError(ValueError):
    """The requested change is not valid. The message is safe to show to the user."""


@dataclass(frozen=True)
class Change:
    field: str
    value: Any


def _tickers() -> set[str]:
    with open(config.STARTER_DIR / "assets_universe.csv", newline="") as f:
        return {r["ticker"] for r in csv.DictReader(f)}


def parse_change(field: str, value: Any) -> Change:
    """Validate and normalise a change. Raises WhatIfError."""
    if field not in FIELDS:
        raise WhatIfError(f"Hypothèse inconnue : {field}. Choix possibles : {', '.join(FIELDS)}.")
    try:
        if field == "horizon_years":
            v = int(value)
            if not 1 <= v <= 50:
                raise WhatIfError("L'horizon doit être compris entre 1 et 50 ans.")
        elif field == "budget_cad":
            v = float(value)
            if not 0 < v <= 1e9:
                raise WhatIfError("Le budget doit être positif.")
        elif field == "risk_tolerance":
            v = str(value)
            if v not in TOLERANCES:
                raise WhatIfError(f"Tolérance inconnue : {v}. Choix : {', '.join(TOLERANCES)}.")
        elif field == "exclude_ticker":
            v = str(value).strip()
            if v not in _tickers():
                raise WhatIfError(f"Actif inconnu : {v}.")
        else:  # as_of_date
            v = value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value))
            if not DATA_START < v <= config.DEFAULT_AS_OF:
                raise WhatIfError(
                    f"La date d'analyse doit être entre {DATA_START} et {config.DEFAULT_AS_OF}."
                )
    except (TypeError, ValueError) as exc:
        if isinstance(exc, WhatIfError):
            raise
        raise WhatIfError(f"Valeur invalide pour {field} : {value!r}.") from exc
    return Change(field, v)


def apply_change(profile: Profile, field: str, value: Any) -> Profile:
    """A copy of `profile` with ONE hypothesis changed. `as_of_date` does not touch the profile."""
    ch = parse_change(field, value)
    if ch.field == "as_of_date":
        return profile.model_copy(deep=True)
    if ch.field == "exclude_ticker":
        excluded = list(dict.fromkeys([*profile.excluded_tickers, ch.value]))
        return profile.model_copy(update={"excluded_tickers": excluded}, deep=True)
    return profile.model_copy(update={ch.field: ch.value}, deep=True)


def rerun_inputs(state: GraphState, field: str, value: Any) -> dict:
    """Graph inputs for the what-if run (a given profile makes the graph skip Agent 1)."""
    if state.profile is None:
        raise WhatIfError("Aucun profil : lancez d'abord une analyse complète.")
    ch = parse_change(field, value)
    profile = apply_change(state.profile, ch.field, ch.value)
    as_of = ch.value if ch.field == "as_of_date" else state.as_of_date
    return initial_state(state.persona, state.request_text, as_of, profile)


def rerun(state: GraphState, field: str, value: Any, *, graph=None) -> GraphState:
    """Blocking rerun: a full graph run with the modified profile."""
    inputs = rerun_inputs(state, field, value)
    return run(
        inputs["persona"], inputs["request_text"], inputs["as_of_date"],
        profile=inputs["profile"], graph=graph,
    )


# ----------------------------------------------------------------------------- diff
def _metric_value(state: GraphState, eid: str | None) -> float | None:
    ev = state.evidence.get(eid or "")
    return numeric(ev) if ev else None


def _delta(old: float | None, new: float | None) -> float | None:
    return None if old is None or new is None else round(new - old, 6)


def diff_scenarios(old: GraphState, new: GraphState) -> dict:
    """Old vs new, JSON-ready: scenario weights and metrics, universe, profile, best scenario."""
    scenarios: dict[str, dict] = {}
    old_by = {s.name: s for s in old.scenarios}
    new_by = {s.name: s for s in new.scenarios}
    for name in sorted(set(old_by) | set(new_by)):
        o, n = old_by.get(name), new_by.get(name)
        ow, nw = (o.weights if o else {}), (n.weights if n else {})
        weights = {
            t: {"old": ow.get(t, 0.0), "new": nw.get(t, 0.0), "delta": round(nw.get(t, 0.0) - ow.get(t, 0.0), 6)}
            for t in sorted(set(ow) | set(nw))
            if abs(nw.get(t, 0.0) - ow.get(t, 0.0)) > 1e-9
        }
        metrics = {}
        for m in SCENARIO_METRICS:
            ov = _metric_value(old, o.metrics.get(m) if o else None)
            nv = _metric_value(new, n.metrics.get(m) if n else None)
            metrics[m] = {
                "old": ov, "new": nv, "delta": _delta(ov, nv),
                "old_evidence": o.metrics.get(m) if o else None,
                "new_evidence": n.metrics.get(m) if n else None,
            }
        scenarios[name] = {"weights": weights, "metrics": metrics}

    profile_changes = {}
    if old.profile and new.profile:
        a, b = old.profile.model_dump(), new.profile.model_dump()
        profile_changes = {k: {"old": a[k], "new": b[k]} for k in a if a[k] != b[k]}
    if old.as_of_date != new.as_of_date:
        profile_changes["as_of_date"] = {"old": old.as_of_date.isoformat(), "new": new.as_of_date.isoformat()}
    ou, nu = set(old.eligible_universe), set(new.eligible_universe)
    old_best = (old.explanation or {}).get("scenario_le_plus_coherent")
    new_best = (new.explanation or {}).get("scenario_le_plus_coherent")
    return {
        "profile": profile_changes,
        "eligible_universe": {"added": sorted(nu - ou), "removed": sorted(ou - nu)},
        "scenarios": scenarios,
        "most_coherent": {"old": old_best, "new": new_best, "changed": old_best != new_best},
        "verification": {
            "old": (old.verification or {}).get("passed"),
            "new": (new.verification or {}).get("passed"),
        },
    }
