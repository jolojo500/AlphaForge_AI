"""Agent 1: profile (PRD 5.1). STUB: Track B replaces the body in B-2."""

from __future__ import annotations

import re

from langgraph.types import interrupt

from alphaforge.personas import PERSONAS
from alphaforge.state import GraphState, Profile
from alphaforge.tracing import traced

_KNOWN = {"tsla": "TSLA", "tesla": "TSLA", "nvda": "NVDA", "nvidia": "NVDA"}


@traced("profile")
def profile_node(state: GraphState) -> dict:
    text = state.request_text.strip()
    if not text and not state.retries.get("clarify"):
        # LangGraph re-runs the node from the top on resume; interrupt() then returns the answer.
        answer = interrupt({"question": "Que souhaitez-vous faire : construire une allocation ou évaluer une idée ?"})
        return {
            "request_text": str(answer),
            "retries": {"clarify": 1},
            "summary": "Question de clarification posée.",
        }

    p = PERSONAS[state.persona]
    idea = None
    lowered = text.lower()
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", lowered)
    ticker = next((t for k, t in _KNOWN.items() if k in lowered), None)
    if m and ticker:
        idea = {"ticker": ticker, "weight": float(m.group(1).replace(",", ".")) / 100}

    conflicts = []
    if idea and p["risk_tolerance"] in ("low", "low_moderate"):
        conflicts.append(
            f"{idea['weight']:.0%} dans {idea['ticker']} face à une tolérance au risque "
            f"{p['risk_tolerance']} et un horizon de {p['horizon_years']} ans."
        )

    profile = Profile(
        persona=state.persona,
        objective=p["objective"],
        horizon_years=p["horizon_years"],
        risk_tolerance=p["risk_tolerance"],
        risk_capacity=p["risk_capacity"],
        constraints=list(p["constraints"]),
        preferences=list(p["preferences"]),
        budget_cad=p["budget_cad"],
        request_type="judge" if idea else "build",
        requested_idea=idea,
        conflicts=conflicts,
    )
    return {"profile": profile, "summary": f"Profil compris ({profile.request_type}) [stub]."}
