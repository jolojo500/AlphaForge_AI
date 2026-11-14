"""Agent 4: explainability (PRD 5.9). STUB: Track B replaces the body in B-4."""

from __future__ import annotations

from alphaforge.state import GraphState
from alphaforge.tracing import traced

DISCLAIMER = "Simulation éducative. Aucun conseil personnalisé."


@traced("explain")
def explain_node(state: GraphState) -> dict:
    by_name = {s.name: s for s in state.scenarios}
    capped, asked = by_name["capped"], by_name["as_requested"]
    quant_ids = sorted(k for k in state.evidence if k.startswith("EQ"))[:2]
    macro_ids = sorted(k for k in state.evidence if k.startswith("EM"))[:1]
    explanation = {
        "resume": "Comparaison de trois scénarios fictifs pour le profil déclaré [stub].",
        "quelles_donnees": [
            {"claim": "Statistiques de risque historiques par actif.", "evidence": quant_ids},
            {"claim": "Contexte de taux et d'inflation à la date d'analyse.", "evidence": macro_ids},
        ],
        "pourquoi_ce_choix": [
            {
                "claim": "Le scénario plafonné présente une perte maximale historique plus faible que le scénario demandé.",
                "evidence": [capped.metrics["max_drawdown"], asked.metrics["max_drawdown"]],
            }
        ],
        "limites": [
            {"claim": "Les valeurs affichées sont des données fictives de démonstration.", "evidence": []}
        ],
        "ce_qui_changerait_la_reponse": [
            {"claim": "Un horizon plus long ou une tolérance au risque différente.", "evidence": []}
        ],
        "incertitude": "Les statistiques historiques ne décrivent pas l'avenir.",
        "scenario_le_plus_coherent": "capped",
        "avertissement": DISCLAIMER,
    }
    return {"explanation": explanation, "summary": "Explication rédigée en quatre questions [stub]."}
