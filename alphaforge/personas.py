"""Persona hypotheses (PRD 7). Created by the skeleton; owned by Track B from B-2 on."""

from __future__ import annotations

from typing import Any

PERSONAS: dict[str, dict] = {
    "amira": {
        "label": "Amira, 26 ans",
        "objective": "growth",
        "horizon_years": 15,
        "risk_tolerance": "high",
        "risk_capacity": "high",
        "constraints": [],
        "preferences": ["likes_tech", "likes_crypto", "wants_diversification"],
        "budget_cad": 100_000.0,
        "example_request": (
            "J'ai 100 000 $ CAD, un horizon de 15 ans et plus. J'aime la techno et la crypto "
            "mais je veux rester diversifiée."
        ),
    },
    "mateo": {
        "label": "Mateo, 41 ans",
        "objective": "balanced",
        "horizon_years": 10,
        "risk_tolerance": "moderate",
        "risk_capacity": "moderate",
        "constraints": ["no_crypto", "esg_only", "no_controversies"],
        "preferences": ["wants_balance"],
        "budget_cad": None,
        "example_request": (
            "Je veux un portefeuille équilibré et responsable sur environ 10 ans, "
            "sans entreprises controversées."
        ),
    },
    "robert": {
        "label": "Robert, 59 ans",
        "objective": "capital_preservation",
        "horizon_years": 4,
        "risk_tolerance": "low_moderate",
        "risk_capacity": "low",
        "constraints": ["no_crypto"],
        "preferences": [],
        "budget_cad": None,
        "example_request": "Je veux mettre 25 % de mon portefeuille dans TSLA.",
    },
}


def get_persona(persona_id: str, persona_data: dict[str, Any] | None = None) -> dict:
    """Return the run-scoped custom entry when present, else the global persona table entry."""
    return persona_data if persona_data is not None else PERSONAS[persona_id]
