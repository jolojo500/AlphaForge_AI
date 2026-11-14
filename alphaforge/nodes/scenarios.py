"""Scenario builder (PRD 5.7). STUB: Track A replaces the body in A-6."""

from __future__ import annotations

from alphaforge.evidence import EvidenceRegistry
from alphaforge.state import SCENARIO_METRICS, SCENARIO_NAMES, GraphState, Scenario
from alphaforge.tracing import traced

_FAKE = {
    "as_requested": (0.31, -0.38, -0.29, 0.25, 0.30, 0.70),
    "capped": (0.14, -0.19, -0.13, 0.12, 0.16, 0.50),
    "profile_baseline": (0.09, -0.12, -0.09, 0.12, 0.15, 0.45),
}


def _equal(tickers: list[str]) -> dict[str, float]:
    return {t: 1 / len(tickers) for t in tickers}


@traced("scenarios")
def scenarios_node(state: GraphState) -> dict:
    reg = EvidenceRegistry("EP")
    base = sorted(state.eligible_universe)[:8]
    idea = state.profile.requested_idea if state.profile else None
    scenarios = []
    for name in SCENARIO_NAMES:
        weights = _equal(base)
        if idea and name != "profile_baseline":
            w = idea["weight"] if name == "as_requested" else min(idea["weight"], 0.05)
            rest = [t for t in base if t != idea["ticker"]]
            weights = {t: (1 - w) / len(rest) for t in rest} | {idea["ticker"]: w}
        metrics = {}
        for metric, value in zip(SCENARIO_METRICS, _FAKE[name], strict=True):
            metrics[metric] = reg.add(
                value={"metric": metric, "scenario": name, "value": value, "unit": "ratio"},
                source="stub",
                date=state.as_of_date,
                method="fictional placeholder, not computed from data",
                confidence="fictional",
            )
        scenarios.append(
            Scenario(name=name, weights=weights, metrics=metrics, notes=[f"Scénario {name} [stub]."])
        )
    return {
        "scenarios": scenarios,
        "evidence": reg.items(),
        "summary": "Trois scénarios comparables construits [stub].",
    }
