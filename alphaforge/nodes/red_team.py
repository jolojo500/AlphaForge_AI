"""Agent 3: red team (PRD 5.8). Pass-through STUB: Track B replaces the body in B-7."""

from __future__ import annotations

from alphaforge.state import GraphState
from alphaforge.tracing import traced


@traced("red_team")
def red_team_node(state: GraphState) -> dict:
    return {
        "objections": [],
        "retries": {"red_team": state.retries.get("red_team", 0) + 1},
        "summary": "Aucune objection bloquante [stub].",
    }
