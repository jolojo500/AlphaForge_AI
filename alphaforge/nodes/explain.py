"""Agent 4: explainability (PRD 5.9). Owned by Track B.

Explains the comparison of the three scenarios, with every claim linked to evidence ids.
Numbers reach the model only as evidence entries with ids. The verifier audits the result;
on a retry this node receives the verifier's error list.

If the model is unavailable, a deterministic template built from the same evidence is used,
so the run still ends with a verifiable explanation.
"""
from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field

from alphaforge import llm
from alphaforge.evidence import numeric
from alphaforge.nodes.profile import TOLERANCE_EN, TOLERANCE_FR
from alphaforge.state import Evidence, GraphState, Scenario
from alphaforge.tracing import traced

DISCLAIMER = "Simulation éducative. Aucun conseil personnalisé."
DISCLAIMER_EN = "Educational simulation. No personalized advice."
MAX_EVIDENCE_LINES = 100

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
- Concision stricte : 1 à 2 affirmations (claims) par section, environ 25 à 30 mots par affirmation.
  Va droit au but, sans répétition. Le résumé doit comporter 1 à 2 phrases directes (environ 30 mots).
- Le résumé et l'incertitude sont vérifiés comme les affirmations : n'y écris un nombre que s'il est
  suivi de son identifiant entre crochets dans le texte (par exemple « 23,2 % [EP3] »). Sinon,
  formule-les sans chiffres.
- Ne remplace pas les trois scénarios par un seul : compare-les, puis indique le plus cohérent.
- Distingue les faits (preuves « fact »), les hypothèses (« assumption ») et les données fictives
  (« fictional »). Si une preuve est fictive ou une hypothèse, dis-le dans les limites.
- quelles_donnees : quelles données ont été utilisées. pourquoi_ce_choix : pourquoi ce scénario est
  le plus cohérent. limites : ce qui limite l'analyse. ce_qui_changerait_la_reponse : ce qui
  changerait la comparaison (horizon, tolérance, budget, exclusion, date).
- Si le profil contient des tensions (conflicts) ou si des objections existent, explique-les.
- Pas de raisonnement interne : seulement des constats observables.
- avertissement : « Simulation éducative. Aucun conseil personnalisé. »"""

SYSTEM_EN = """You are the explainability agent for an educational financial simulation tool.
You explain the COMPARISON of three simulated scenarios for an investor profile, in English.
You answer the four BNCD workshop questions: which data, why this choice, which limits,
what would change the answer. You distinguish risk tolerance (what the person says they accept)
and risk capacity (what their situation can absorb). Named risk types are: market, credit,
liquidity, interest rate and inflation, currency, concentration.

Strict rules:
- Respond using the exact schema keys (quelles_donnees, pourquoi_ce_choix, limites,
  ce_qui_changerait_la_reponse, resume, incertitude, scenario_le_plus_coherent, avertissement).
- Every claim must cite evidence ids (evidence field) taken ONLY from the provided list. Do not invent any id.
- Every number you write must come from an evidence item cited in the same claim, copied exactly as printed after '='
  (e.g. '38.0%'). Do not write any other number (except those from the user request), no invented years.
- Consistency language, never advice: state which scenario is 'most consistent with the stated profile',
  without telling to buy, sell, or invest. No return forecast, no promise. Statistics are historical.
  NEVER use the roots 'recommend*' or 'advise*'.
- Strict conciseness: 1 to 2 claims per section, ~25 to 30 words per claim. The summary must be 1 to 2 direct sentences (~30 words).
- The summary and uncertainty are checked like claims: do not write a number unless followed by its id in brackets
  (e.g. '23.2% [EP3]'). Otherwise write without figures.
- Do not replace the three scenarios with a single one: compare them, then indicate the most consistent.
- Distinguish facts ('fact' evidence), assumptions ('assumption'), and fictional data ('fictional').
  If an evidence item is fictional or an assumption, state it in the limits.
- quelles_donnees: what data was used. pourquoi_ce_choix: why this scenario is most consistent.
  limites: what limits the analysis. ce_qui_changerait_la_reponse: what would change the comparison (horizon, tolerance, budget, exclusion, date).
- If the profile has conflicts or if objections exist, explain them.
- No internal reasoning: only observable observations.
- avertissement: 'Educational simulation. No personalized advice.'"""


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
    """Select only evidence the explanation needs (keeps prompt well under 6k tokens)."""
    # Top 8 tickers by highest weight across scenarios + requested ticker
    max_weights: dict[str, float] = {}
    for sc in state.scenarios:
        for t, w in sc.weights.items():
            if w > max_weights.get(t, 0.0):
                max_weights[t] = w
    top_tickers = set(sorted(max_weights, key=lambda t: max_weights[t], reverse=True)[:8])
    if state.profile and state.profile.requested_idea:
        top_tickers.add(state.profile.requested_idea["ticker"])

    metric_ids = {e for sc in state.scenarios for e in sc.metrics.values()}
    cited_ids = metric_ids | {x.get("evidence_id") for x in state.exclusions if x.get("evidence_id")}
    cited_ids |= {e.get("evidence_id") for e in state.events if e.get("evidence_id")}

    ordered: list[Evidence] = []
    for eid, ev in sorted(state.evidence.items(), key=lambda kv: (kv[0][:2], int(kv[0][2:]))):
        prefix = eid[:2]
        # Include scenario metrics, macro, exclusions, events, and explicitly cited items
        if prefix in ("EP", "EM", "ES", "EN") or eid in cited_ids:
            ordered.append(ev)
            continue
        if prefix == "EQ":
            v = ev.value
            # Survivorship assumption entry has no ticker or string value
            if not isinstance(v, dict):
                ordered.append(ev)
                continue
            if "tickers" in v:
                if set(v["tickers"]) <= top_tickers:
                    ordered.append(ev)
                continue
            ticker = v.get("ticker")
            if ticker is None or ticker in top_tickers:
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
    lang = getattr(state.profile, "language", None) or getattr(state, "language", "fr")
    p = state.profile
    if lang == "en":
        lines = [
            f"Analysis date: {state.as_of_date}",
            f"Request: {state.request_text!r}",
            (
                f"Profile: persona={p.persona}, objective={p.objective}, horizon={p.horizon_years} years, "
                f"tolerance={p.risk_tolerance}, capacity={p.risk_capacity}, constraints={p.constraints}, "
                f"preferences={p.preferences}, type={p.request_type}, idea={p.requested_idea}"
            ),
            f"Detected conflicts: {p.conflicts or 'none'}",
            "",
            "Simulated scenarios:",
            *(_scenario_block(s, state.evidence) for s in state.scenarios),
            "",
            "Scenario notes: "
            + " | ".join(f"{s.name}: {' '.join(s.notes)}" for s in state.scenarios if s.notes),
            f"Excluded assets: {[(x['ticker'], x['reason'], x['evidence_id']) for x in state.exclusions]}",
            f"Red team objections: {state.objections or 'none'}",
            f"News & Events: {[(e['ticker'], e['headline'], e['risk_type'], e['evidence_id']) for e in state.events]}",
            "",
            "Available evidence (id = value to copy as is | indicator | method | source | date | nature):",
            *(describe_evidence(ev) for ev in _select_evidence(state)),
        ]
        errors = (state.verification or {}).get("errors") if state.retries.get("explain") else None
        if errors:
            lines += [
                "",
                "Your previous response was rejected by the verifier. Correct exactly these points:",
                *[f"- {e}" for e in errors],
            ]
        return "\n".join(lines)

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
    lang = getattr(state.profile, "language", None) or getattr(state, "language", "fr")

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
            if lang == "en":
                donnees.append(
                    {
                        "claim": (
                            f"Scenario {sc.name}: historical annualized volatility of {_fr(abs(vol) * 100, 1)} %, "
                            f"historical maximum loss of {_fr(abs(mdd) * 100, 1)} %."
                        ),
                        "evidence": ids,
                    }
                )
            else:
                donnees.append(
                    {
                        "claim": (
                            f"Scénario {sc.name} : volatilité annualisée historique de {_fr(abs(vol) * 100, 1)} %, "
                            f"perte maximale historique de {_fr(abs(mdd) * 100, 1)} %."
                        ),
                        "evidence": ids,
                    }
                )
    bm = _metric_value(state, best, "max_drawdown")
    if bm is not None:
        if lang == "en":
            tol_str = (
                TOLERANCE_EN.get(state.profile.risk_tolerance, state.profile.risk_tolerance)
                if state.profile
                else ""
            )
            pourquoi.append(
                {
                    "claim": (
                        f"The {best.name} scenario shows the lowest historical maximum loss "
                        f"({_fr(abs(bm) * 100, 1)} %) among the three, which is most consistent with a "
                        f"'{tol_str}' risk tolerance."
                    ),
                    "evidence": [best.metrics["max_drawdown"]],
                }
            )
        else:
            tol_str = (
                TOLERANCE_FR.get(state.profile.risk_tolerance, state.profile.risk_tolerance)
                if state.profile
                else ""
            )
            pourquoi.append(
                {
                    "claim": (
                        f"Le scénario {best.name} présente la plus faible perte maximale historique "
                        f"({_fr(abs(bm) * 100, 1)} %) parmi les trois, ce qui est le plus cohérent avec une "
                        f"tolérance au risque « {tol_str} »."
                    ),
                    "evidence": [best.metrics["max_drawdown"]],
                }
            )
    req_idea = getattr(state.profile, "requested_idea", None) if state.profile else None
    if isinstance(req_idea, dict):
        ticker = req_idea.get("ticker")
        w_val = req_idea.get("weight")
    elif req_idea is not None:
        ticker = getattr(req_idea, "ticker", None)
        w_val = getattr(req_idea, "weight", None)
    else:
        ticker = None
        w_val = None
    weight_pct = int(round(w_val * 100)) if w_val is not None else None
    horizon = getattr(state.profile, "horizon_years", 5) if state.profile else 5
    scenario_label = "le scénario ajusté" if best.name == "capped" else ("le scénario de votre demande" if best.name == "as_requested" else "le profil de base")

    if lang == "en":
        tol_str = (
            TOLERANCE_EN.get(state.profile.risk_tolerance, state.profile.risk_tolerance)
            if state.profile
            else "moderate"
        )
        if ticker and weight_pct:
            resume = (
                f"Your request to allocate {weight_pct} % to {ticker} has been analyzed across three scenarios against your {tol_str} risk profile (horizon {horizon} years). "
                f"The {best.name.replace('_', ' ')} scenario is the most consistent with your financial capacity and objectives."
            )
        elif ticker:
            resume = (
                f"An allocation to {ticker} has been analyzed across three scenarios against your {tol_str} risk profile (horizon {horizon} years). "
                f"The {best.name.replace('_', ' ')} scenario is the most consistent with your risk profile."
            )
        else:
            resume = (
                f"Three simulated allocation scenarios were evaluated against your {tol_str} risk profile (horizon {horizon} years). "
                f"The {best.name.replace('_', ' ')} scenario is the most consistent with your declared objectives."
            )

        if not donnees:
            donnees = [{"claim": "No numerical metrics available.", "evidence": []}]
        if not pourquoi:
            pourquoi = [{"claim": "The choice is based on the declared profile.", "evidence": []}]
        limites = [
            {"claim": "This explanation was generated from a template, without a language model.", "evidence": []},
            {"claim": "Historical statistics do not describe the future.", "evidence": []},
        ]
        if state.profile and state.profile.conflicts:
            limites.append(
                {"claim": "The profile has contradictions with the formulated request.", "evidence": []}
            )
        return {
            "resume": resume,
            "quelles_donnees": donnees,
            "pourquoi_ce_choix": pourquoi,
            "limites": limites,
            "ce_qui_changerait_la_reponse": [
                {"claim": "A different horizon, different risk tolerance, or asset exclusion.", "evidence": []}
            ],
            "incertitude": "Historical statistics do not describe the future.",
            "scenario_le_plus_coherent": best.name,
            "avertissement": DISCLAIMER_EN,
        }

    tol_str = (
        TOLERANCE_FR.get(state.profile.risk_tolerance, state.profile.risk_tolerance)
        if state.profile
        else "modéré"
    )
    if ticker and weight_pct:
        resume = (
            f"Votre souhait d'investir {weight_pct} % sur {ticker} a été analysé à travers trois scénarios face à votre tolérance au risque {tol_str} (horizon de {horizon} ans). "
            f"{scenario_label.capitalize()} ressort comme le plus cohérent avec votre capacité financière et vos objectifs."
        )
    elif ticker:
        resume = (
            f"L'exposition à {ticker} a été analysée à travers trois scénarios face à votre tolérance au risque {tol_str} (horizon de {horizon} ans). "
            f"{scenario_label.capitalize()} ressort comme le plus cohérent avec votre profil de risque."
        )
    else:
        resume = (
            f"Trois scénarios d'allocation ont été simulés pour votre tolérance au risque {tol_str} (horizon de {horizon} ans). "
            f"{scenario_label.capitalize()} ressort comme le plus cohérent avec le profil déclaré."
        )

    if not donnees:
        donnees = [{"claim": "Aucun indicateur chiffré n'est disponible.", "evidence": []}]
    if not pourquoi:
        pourquoi = [{"claim": "Le choix repose sur le profil déclaré.", "evidence": []}]
    limites = [
        {"claim": "Cette explication a été produite par un gabarit, sans modèle de langage.", "evidence": []},
        {"claim": "Les statistiques sont historiques et ne décrivent pas l'avenir.", "evidence": []},
    ]
    if state.profile and state.profile.conflicts:
        limites.append(
            {"claim": "Le profil comporte des tensions avec la demande formulée.", "evidence": []}
        )
    return {
        "resume": resume,
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
def _explain_llm():
    if llm._override is not None or os.getenv("AF_LLM_OFFLINE") == "1":
        return None
    from langchain_aws import ChatBedrockConverse

    from alphaforge import config
    return ChatBedrockConverse(
        model=llm.model_id("main"),
        region_name=config.AWS_REGION,
        max_tokens=6000,
    )


def generate_explanation(state: GraphState, llm_client=None) -> tuple[dict, bool]:
    """Returns (explanation dict, used_template)."""
    client = llm_client if llm_client is not None else _explain_llm()
    lang = getattr(state.profile, "language", None) or getattr(state, "language", "fr")
    sys = SYSTEM_EN if lang == "en" else SYSTEM
    disclaimer = DISCLAIMER_EN if lang == "en" else DISCLAIMER
    try:
        out = llm.call_json(
            build_prompt(state), Explanation, kind="main", system=sys, llm=client
        )
    except llm.LLMError:
        return template_explanation(state), True
    data = out.model_dump()
    data["avertissement"] = disclaimer
    return data, False


@traced("explain")
def explain_node(state: GraphState) -> dict:
    lang = getattr(state.profile, "language", None) or getattr(state, "language", "fr")
    explanation, template = generate_explanation(state)
    retry = bool(state.retries.get("explain"))
    if lang == "en":
        summary = "Explanation drafted across four questions"
        summary += " (template without model)." if template else "."
        if retry:
            summary = "Explanation corrected after verification" + (
                " (template without model)." if template else "."
            )
    else:
        summary = "Explication rédigée en quatre questions"
        summary += " (gabarit sans modèle)." if template else "."
        if retry:
            summary = "Explication corrigée après la vérification" + (
                " (gabarit sans modèle)." if template else "."
            )
    return {"explanation": explanation, "summary": summary}
