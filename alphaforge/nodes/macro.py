"""Macro (PRD 5.4). STUB: Track A replaces the body in A-3."""

from __future__ import annotations

from alphaforge.evidence import EvidenceRegistry
from alphaforge.state import GraphState
from alphaforge.tracing import traced


@traced("macro")
def macro_node(state: GraphState) -> dict:
    reg = EvidenceRegistry("EM")
    for metric, value in (("policy_rate_ca", 2.25), ("cpi_yoy_ca", 2.1)):
        reg.add(
            value={"metric": metric, "value": value, "unit": "%"},
            source="stub",
            date=state.as_of_date,
            method="fictional placeholder",
            confidence="fictional",
        )
    return {"evidence": reg.items(), "summary": "Contexte macro connu à la date d'analyse [stub]."}
