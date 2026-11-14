"""Verifier (PRD 5.10). STUB (checks cited ids only): Track B replaces the body in B-3."""

from __future__ import annotations

from alphaforge.state import GraphState
from alphaforge.tracing import traced

SECTIONS = ("quelles_donnees", "pourquoi_ce_choix", "limites", "ce_qui_changerait_la_reponse")


@traced("verifier")
def verifier_node(state: GraphState) -> dict:
    errors = []
    explanation = state.explanation or {}
    for section in SECTIONS:
        for item in explanation.get(section, []):
            for eid in item.get("evidence", []):
                if eid not in state.evidence:
                    errors.append(f"{section}: preuve inconnue {eid}")
    passed = not errors
    update = {
        "verification": {"passed": passed, "errors": errors},
        "summary": "Vérification réussie [stub]." if passed else f"{len(errors)} erreur(s) détectée(s).",
    }
    if not passed:
        update["retries"] = {"explain": state.retries.get("explain", 0) + 1}
    return update
