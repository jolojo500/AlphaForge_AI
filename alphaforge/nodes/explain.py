"""Agent 4: explainability (PRD 5.9). Owned by Track B.

Explains the comparison of the three scenarios, with every claim linked to evidence ids.
Numbers reach the model only as evidence entries with ids. The verifier audits the result;
on a retry this node receives the verifier's error list.

If the model is unavailable, a deterministic template built from the same evidence is used,
so the run still ends with a verifiable explanation.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from alphaforge import llm
from alphaforge.evidence import numeric
from alphaforge.nodes.profile import TOLERANCE_FR
from alphaforge.state import Evidence, GraphState, Scenario
from alphaforge.tracing import traced

DISCLAIMER = "Simulation éducative. Aucun conseil personnalisé."
MAX_EVIDENCE_LINES = 220

class Claim(BaseModel):
    claim: str
    evidence: list[str] = Field(default_factory=list)


class Explanation(BaseModel):
    resume: str
    quelles_donnees: list[Claim]
    pourquoi_ce_choix: list[Claim]
    limites: list[Claim]
    ce_qui_changerait_la_reponse: list[Claim]
    incertitude: str
    scenario_le_plus_coherent: Literal["as_requested", "capped", "profile_baseline"]
    avertissement: str = DISCLAIMER


SYSTEM = """Tu es l'agent d'explicabilité d'un outil éducatif de simulation financière.
Tu expliques la COMPARAISON de trois scénarios fictifs pour un profil d'investisseur, en français.
Tu réponds aux quatre questions de l'atelier BNCD : quelles données, pourquoi ce choix, quelles limites,
qu'est-ce qui changerait la réponse. Tu distingues tolérance au risque (ce que la personne accepte)
et capacité (ce que sa situation peut absorber). Les risques se nomment parmi : marché, crédit,
liquidité, taux et inflation, devise, concentration.

Règles strictes :
- Réponds avec les clés exactes du schéma. Chaque affirmation (claim) cite des identifiants de preuve
  (champ evidence) pris UNIQUEMENT dans la liste fournie. N'invente aucun identifiant.
- Tout nombre que tu écris doit venir d'une preuve citée dans la même affirmation, recopié exactement
  comme il est imprimé après « = » (par exemple « 38,0 % »). N'écris aucun autre nombre chiffré
  (sauf ceux de la demande de l'utilisateur), pas d'années de calcul inventées.
- Langage de cohérence, jamais de conseil : dis quel scénario est « le plus cohérent avec le profil
  déclaré », sans dire d'acheter, de vendre ou d'investir. Aucune prévision de rendement futur,
  aucune promesse. Les statistiques sont historiques.
  N'utilise JAMAIS les racines « recommand* » ou « conseill* » (même « recommandé par le profil » :
  utilise « plafond de référence » ou « le plus cohérent avec le profil déclaré »).
- Ne remplace pas les trois scénarios par un seul : compare-les, puis indique le plus cohérent.
- Distingue les faits (preuves « fact »), les hypothèses (« assumption ») et les données fictives
  (« fictional »). Si une preuve est fictive ou une hypothèse, dis-le dans les limites.
- quelles_donnees : quelles données ont été utilisées. pourquoi_ce_choix : pourquoi ce scénario est
  le plus cohérent. limites : ce qui limite l'analyse. ce_qui_changerait_la_reponse : ce qui
  changerait la comparaison (horizon, tolérance, budget, exclusion, date).
- Si le profil contient des tensions (conflicts) ou si des objections existent, explique-les.
- Pas de raisonnement interne : seulement des constats observables.
- avertissement : « Simulation éducative. Aucun conseil personnalisé. »"""


# ----------------------------------------------------------------------- context building
_PERCENT_UNITS = {"ratio", "%", "pct", "percent"}


def _fr(x: float, digits: int) -> str:
    return f"{x:.{digits}f}".replace(".", ",")


def printable(ev: Evidence) -> str:
    """The value as it should be printed in a claim, so the verifier matches it."""
    v = ev.value
    num = numeric(ev)
    if num is None:
        return str(v.get("value", v)) if isinstance(v, dict) else str(v)
    unit = v.get("unit") if isinstance(v, dict) else None
    metric = v.get("metric") if isinstance(v, dict) else None
    if metric == "sector_concentration_hhi":
        return _fr(num, 2)
    if unit == "%":
        return f"{_fr(num, 2)} %"
    if unit in _PERCENT_UNITS or (unit is None and isinstance(v, dict) and abs(num) <= 1.5):
        return f"{_fr(num * 100, 1)} %"
    return _fr(num, 2) if abs(num) < 1000 else f"{num:,.0f}".replace(",", " ")


def describe_evidence(ev: Evidence) -> str:
    v = ev.value
    if isinstance(v, dict):
        label = " ".join(str(v[k]) for k in ("metric", "scenario", "ticker") if k in v) or "value"
        if "tickers" in v:
            label += " " + "/".join(v["tickers"])
    else:
        label = "valeur"
    return (
        f"{ev.id} = {printable(ev)} | {label} | {ev.method} | {ev.source} | {ev.date} | {ev.confidence}"
    )


def _select_evidence(state: GraphState) -> list[Evidence]:
    """Scenario metrics, exclusions, macro and news first, then quant for held tickers."""
    held = {t for sc in state.scenarios for t in sc.weights}
    metric_ids = {e for sc in state.scenarios for e in sc.metrics.values()}
    cited = set(metric_ids) | {x.get("evidence_id") for x in state.exclusions}
    cited |= {e.get("evidence_id") for e in state.events}
    ordered = []
    for eid, ev in sorted(state.evidence.items(), key=lambda kv: (kv[0][:2], int(kv[0][2:]))):
        v = ev.value if isinstance(ev.value, dict) else {}
        tickers = set(v.get("tickers", [])) | ({v["ticker"]} if "ticker" in v else set())
        if eid in cited or eid[:2] in ("EM", "EP") or (eid[:2] == "EQ" and tickers <= held) or (
            not tickers and eid[:2] != "EN"
        ):
            ordered.append(ev)
    return ordered[:MAX_EVIDENCE_LINES]


def _scenario_block(sc: Scenario, evidence: dict[str, Evidence]) -> str:
    top = sorted(sc.weights.items(), key=lambda kv: -kv[1])[:8]
    weights = ", ".join(f"{t} {_fr(w * 100, 1)} %" for t, w in top)
    lines = [f"- {sc.name} : positions principales [{weights}]"]
    for m, eid in sc.metrics.items():
        ev = evidence.get(eid)
        if ev is not None:
            lines.append(f"    {m} : {eid} = {printable(ev)} ({ev.method}, {ev.confidence})")
    return "\n".join(lines)


def build_prompt(state: GraphState) -> str:
    p = state.profile
    lines = [
        f"Date d'analyse : {state.as_of_date}",
        f"Demande : {state.request_text!r}",
        (
            f"Profil : persona={p.persona}, objectif={p.objective}, horizon={p.horizon_years} ans, "
            f"tolérance={p.risk_tolerance}, capacité={p.risk_capacity}, contraintes={p.constraints}, "
            f"préférences={p.preferences}, type={p.request_type}, idée={p.requested_idea}"
        ),
        f"Tensions détectées : {p.conflicts or 'aucune'}",
        "",
        "Scénarios fictifs :",
        *(_scenario_block(s, state.evidence) for s in state.scenarios),
        "",
        "Notes des scénarios : "
        + " | ".join(f"{s.name}: {' '.join(s.notes)}" for s in state.scenarios if s.notes),
        f"Actifs exclus : {[(x['ticker'], x['reason'], x['evidence_id']) for x in state.exclusions]}",
        f"Objections du red team : {state.objections or 'aucune'}",
        f"Actualités : {[(e['ticker'], e['headline'], e['risk_type'], e['evidence_id']) for e in state.events]}",
        "",
        "Preuves disponibles (id = valeur à recopier telle quelle | indicateur | méthode | source | date | nature) :",
        *(describe_evidence(ev) for ev in _select_evidence(state)),
    ]
    errors = (state.verification or {}).get("errors") if state.retries.get("explain") else None
    if errors:
        lines += [
            "",
            "Ta réponse précédente a été rejetée par le vérificateur. Corrige exactement ces points :",
            *[f"- {e}" for e in errors],
        ]
    return "\n".join(lines)


# ----------------------------------------------------------------------- deterministic fallback
def _metric_value(state: GraphState, sc: Scenario, metric: str) -> float | None:
    ev = state.evidence.get(sc.metrics.get(metric, ""))
    return numeric(ev) if ev else None


def template_explanation(state: GraphState) -> dict:
    """Explanation built from the evidence without a model (used when the LLM fails)."""
    def risk(sc: Scenario) -> float:
        v = _metric_value(state, sc, "max_drawdown")
        return abs(v) if v is not None else 9.0

    best = min(state.scenarios, key=risk)
    donnees, pourquoi = [], []
    for sc in state.scenarios:
        ids = [sc.metrics[m] for m in ("volatility_ann", "max_drawdown") if m in sc.metrics]
        vol = _metric_value(state, sc, "volatility_ann")
        mdd = _metric_value(state, sc, "max_drawdown")
        if vol is not None and mdd is not None:
            donnees.append(
                {
                    "claim": (
                        f"Scénario {sc.name} : volatilité annualisée historique de {abs(vol):.1%}, "
                        f"perte maximale historique de {abs(mdd):.1%}."
                    ),
                    "evidence": ids,
                }
            )
    bm = _metric_value(state, best, "max_drawdown")
    if bm is not None:
        tol_str = (
            TOLERANCE_FR.get(state.profile.risk_tolerance, state.profile.risk_tolerance)
            if state.profile
            else ""
        )
        pourquoi.append(
            {
                "claim": (
                    f"Le scénario {best.name} présente la plus faible perte maximale historique "
                    f"({abs(bm):.1%}) parmi les trois, ce qui est le plus cohérent avec une "
                    f"tolérance au risque « {tol_str} »."
                ),
                "evidence": [best.metrics["max_drawdown"]],
            }
        )
    if not donnees:
        donnees = [{"claim": "Aucun indicateur chiffré n'est disponible.", "evidence": []}]
    if not pourquoi:
        pourquoi = [{"claim": "Le choix repose sur le profil déclaré.", "evidence": []}]
    fictional = any(e.confidence == "fictional" for e in state.evidence.values())
    limites = [
        {"claim": "Cette explication a été produite par un gabarit, sans modèle de langage.", "evidence": []},
        {"claim": "Les statistiques sont historiques et ne décrivent pas l'avenir.", "evidence": []},
    ]
    if fictional:
        limites.append({"claim": "Certaines valeurs sont des données fictives de démonstration.", "evidence": []})
    if state.profile and state.profile.conflicts:
        limites.append(
            {"claim": "Le profil comporte des tensions avec la demande formulée.", "evidence": []}
        )
    return {
        "resume": "Comparaison de trois scénarios fictifs avec leurs indicateurs de risque historiques.",
        "quelles_donnees": donnees,
        "pourquoi_ce_choix": pourquoi,
        "limites": limites,
        "ce_qui_changerait_la_reponse": [
            {"claim": "Un autre horizon, une autre tolérance au risque ou une exclusion d'actif.", "evidence": []}
        ],
        "incertitude": "Les statistiques historiques ne décrivent pas l'avenir.",
        "scenario_le_plus_coherent": best.name,
        "avertissement": DISCLAIMER,
    }


# ----------------------------------------------------------------------- node
def generate_explanation(state: GraphState, llm_client=None) -> tuple[dict, bool]:
    """Returns (explanation dict, used_template)."""
    try:
        out = llm.call_json(
            build_prompt(state), Explanation, kind="main", system=SYSTEM, llm=llm_client
        )
    except llm.LLMError:
        return template_explanation(state), True
    data = out.model_dump()
    data["avertissement"] = DISCLAIMER
    return data, False


@traced("explain")
def explain_node(state: GraphState) -> dict:
    explanation, template = generate_explanation(state)
    retry = bool(state.retries.get("explain"))
    summary = "Explication rédigée en quatre questions"
    summary += " (gabarit sans modèle)." if template else "."
    if retry:
        summary = "Explication corrigée après la vérification" + (
            " (gabarit sans modèle)." if template else "."
        )
    return {"explanation": explanation, "summary": summary}
