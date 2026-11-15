"""What-if engine (PRD 5.11). Track C owned."""

from __future__ import annotations

import datetime as dt
from typing import Any

from alphaforge.graph import initial_state, run
from alphaforge.state import (
    SCENARIO_NAMES,
    Evidence,
    GraphState,
    Profile,
    Scenario,
)


def apply_change(
    profile: Profile,
    field: str,
    value: Any,
) -> Profile:
    """Apply a single hypothesis change to a profile, returning a new Profile."""
    if field == "horizon_years":
        return profile.model_copy(update={"horizon_years": int(value)})

    if field == "budget_cad":
        val = float(value) if value is not None and value != "" else None
        return profile.model_copy(update={"budget_cad": val})

    if field == "risk_tolerance":
        return profile.model_copy(update={"risk_tolerance": str(value)})

    if field == "risk_capacity":
        if str(value) not in ("low", "moderate", "high"):
            raise ValueError("risk_capacity must be low, moderate or high")
        return profile.model_copy(update={"risk_capacity": str(value)})

    if field in ("exclude_ticker", "exclude_asset"):
        ticker = str(value).upper()
        current = list(profile.excluded_tickers)
        if ticker not in current:
            current.append(ticker)
        return profile.model_copy(update={"excluded_tickers": current})

    if field == "excluded_tickers":
        tickers = [str(t).upper() for t in (value if isinstance(value, list) else [value])]
        current = list(set(profile.excluded_tickers + tickers))
        return profile.model_copy(update={"excluded_tickers": current})

    if field == "as_of_date":
        # as_of_date is on GraphState, profile remains unchanged
        return profile

    if field == "current_holdings":
        from alphaforge.holdings import parse_holdings

        return profile.model_copy(update={"current_holdings": parse_holdings(value)})

    raise ValueError(f"Unsupported what-if field: {field}")


def prepare_whatif_inputs(
    state: GraphState,
    change: dict[str, Any] | tuple[str, Any],
) -> dict[str, Any]:
    """Prepare initial_state dictionary for a what-if rerun."""
    if isinstance(change, tuple):
        field, value = change
    else:
        field, value = change["field"], change["value"]

    if state.profile is None:
        raise ValueError("Cannot perform what-if rerun on a state without an established profile")

    if field == "as_of_date":
        as_of = (
            dt.date.fromisoformat(value)
            if isinstance(value, str)
            else value
        )
        new_profile = state.profile
    else:
        as_of = state.as_of_date
        new_profile = apply_change(state.profile, field, value)

    return initial_state(
        persona=state.persona,
        request_text=state.request_text,
        as_of_date=as_of,
        profile=new_profile,
    )


def rerun(
    state: GraphState,
    change: dict[str, Any] | tuple[str, Any],
    thread_id: str | None = None,
) -> GraphState:
    """Rerun the graph with the modified profile, entering at screening (skipping Agent 1)."""
    inputs = prepare_whatif_inputs(state, change)
    return run(
        persona=inputs["persona"],
        request_text=inputs["request_text"],
        as_of_date=inputs["as_of_date"],
        profile=inputs["profile"],
        thread_id=thread_id,
    )


def _get_metric_num(ev: Evidence | None) -> float | None:
    if not ev:
        return None
    val = ev.value
    if isinstance(val, dict) and "value" in val:
        val = val["value"]
    if isinstance(val, (int, float)):
        return float(val)
    return None


def diff_scenarios(
    old: GraphState | list[Scenario],
    new: GraphState | list[Scenario],
    old_evidence: dict[str, Evidence] | None = None,
    new_evidence: dict[str, Evidence] | None = None,
) -> dict[str, Any]:
    """Compare old vs new scenarios, returning weight and metric deltas per scenario."""
    if isinstance(old, GraphState):
        old_scenarios = old.scenarios
        old_ev = old.evidence
    else:
        old_scenarios = old
        old_ev = old_evidence or {}

    if isinstance(new, GraphState):
        new_scenarios = new.scenarios
        new_ev = new.evidence
    else:
        new_scenarios = new
        new_ev = new_evidence or {}

    old_map = {s.name: s for s in old_scenarios}
    new_map = {s.name: s for s in new_scenarios}

    scenarios_diff: dict[str, Any] = {}
    summary_lines: list[str] = []

    for name in SCENARIO_NAMES:
        old_sc = old_map.get(name)
        new_sc = new_map.get(name)
        if not old_sc or not new_sc:
            continue

        # Weight deltas
        all_tickers = sorted(set(old_sc.weights.keys()) | set(new_sc.weights.keys()))
        weights_diff: dict[str, dict[str, float]] = {}
        for t in all_tickers:
            w_old = old_sc.weights.get(t, 0.0)
            w_new = new_sc.weights.get(t, 0.0)
            delta = round(w_new - w_old, 6)
            weights_diff[t] = {
                "old": w_old,
                "new": w_new,
                "delta": delta,
            }
            if abs(delta) > 1e-4 and name == "capped":
                pct_old = f"{w_old * 100:.1f}%"
                pct_new = f"{w_new * 100:.1f}%"
                summary_lines.append(
                    f"Scénario {name} : poids de {t} passe de {pct_old} à {pct_new} ({'+' if delta > 0 else ''}{delta * 100:.1f}%)"
                )

        # Metric deltas
        all_metrics = sorted(set(old_sc.metrics.keys()) | set(new_sc.metrics.keys()))
        metrics_diff: dict[str, Any] = {}
        for m in all_metrics:
            eid_old = old_sc.metrics.get(m)
            eid_new = new_sc.metrics.get(m)
            val_old = _get_metric_num(old_ev.get(eid_old)) if eid_old else None
            val_new = _get_metric_num(new_ev.get(eid_new)) if eid_new else None
            delta_val = (
                round(val_new - val_old, 6)
                if val_old is not None and val_new is not None
                else None
            )
            metrics_diff[m] = {
                "old": val_old,
                "new": val_new,
                "delta": delta_val,
                "old_eid": eid_old,
                "new_eid": eid_new,
            }

        scenarios_diff[name] = {
            "weights": weights_diff,
            "metrics": metrics_diff,
            "notes": {
                "old": old_sc.notes,
                "new": new_sc.notes,
            },
        }

    return {
        "scenarios": scenarios_diff,
        "summary": summary_lines,
    }
