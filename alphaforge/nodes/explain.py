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
from alphaforge.data.provider import get_provider
from alphaforge.evidence import numeric
from alphaforge.nodes.profile import TOLERANCE_EN, TOLERANCE_FR
from alphaforge.nodes.scenarios import CAPS
from alphaforge.state import Evidence, GraphState, Scenario, effective_risk
from alphaforge.tracing import traced

DISCLAIMER = "Simulation éducative. Aucun conseil personnalisé."
DISCLAIMER_EN = "Educational simulation. No personalized advice."
MAX_EVIDENCE_LINES = 100
SCENARIO_NAMES = ("as_requested", "capped", "profile_baseline")

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


SYSTEM = """Tu es l'agent d'explicabilité d'un outil éducatif de simulation financière d'aide à la décision.
Tu évalues directement l'idée d'investissement demandée, quelle que soit sa classe (action, FNB/indice, cryptoactif, or ou autre actif de l'univers), selon le profil déclaré et les preuves disponibles. Parle clairement et simplement.
Tu réponds aux quatre questions de gouvernance de l'atelier BNCD : quelles données, pourquoi ce choix, quelles limites, qu'est-ce qui changerait la réponse.
Tu distingues tolérance au risque (ce que la personne accepte) et capacité (ce que sa situation peut absorber).
Les risques se nomment parmi : marché, crédit, liquidité, taux et inflation, devise, concentration.

Règles strictes :
- Réponds avec les clés exactes du schéma : resume, quelles_donnees, pourquoi_ce_choix, limites, ce_qui_changerait_la_reponse, incertitude, scenario_le_plus_coherent, avertissement.
- Le champ resume est la réponse principale, directe et brève (2 paragraphes) : dis clairement si l'idée est cohérente, partiellement cohérente ou peu cohérente avec la tolérance ET la capacité, l'objectif et l'horizon. Si elle est peu cohérente, dis-le sans ambiguïté et explique le risque déterminant, sans dramatiser. Ne dis jamais que tu connais le portefeuille si ses positions n'ont pas été fournies. Dans ce cas, précise que le poids demandé est évalué sur un portefeuille hypothétique et que son impact réel dépend des avoirs actuels, inconnus.
- Sois concis : le résumé tient en 1 à 2 phrases directes réparties sur deux courts paragraphes; limite chaque autre section à 1 ou 2 affirmations brèves.
- Adapte l'analyse à l'actif demandé : action (risque d'entreprise et concentration), FNB/indice (expositions sous-jacentes et chevauchements disponibles), cryptoactif (volatilité et risque de marché), or (matière première, devise et taux), autres actifs selon les données disponibles. Ne transpose pas un raisonnement propre à une classe d'actifs à une autre.
- Justifie le constat par les preuves spécifiques à l'actif (historique, risque, liquidité si disponible), les actualités et les indicateurs macro effectivement fournis. N'invente ni cycle de marché, ni valorisation, ni capitalisation boursière, ni volume. Indique clairement dans les limites les facteurs importants absents des données; ne présente pas le contexte macro comme une conclusion sur l'actif si le lien n'est pas étayé.
- Chiffres dans le résumé : Tu peux reprendre uniquement les chiffres présents dans la demande de l'utilisateur. Tout autre nombre doit être immédiatement suivi de son identifiant de preuve entre crochets (ex. « 23,2 % [EP3] »).
- Règle des nombres (vérifiée automatiquement) : recopie chaque nombre exactement comme il est imprimé après « = » dans la preuve citée (par exemple « 38,0 % »). N'écris AUCUN autre nombre : ni plafond, ni plancher, ni seuil, ni pourcentage d'actions, ni année, sauf s'il figure dans une preuve citée dans la même affirmation ou dans la demande de l'utilisateur. Sans preuve, formule l'idée sans chiffre (« au-dessus du plafond de référence »).
- Ne remplace pas les trois scénarios par un seul : compare-les, puis indique le plus cohérent. Si le profil contient des tensions (conflicts) ou si des objections existent, explique-les.
- Chaque affirmation (claim) dans les 4 sections cite des identifiants de preuve (champ evidence) pris UNIQUEMENT dans la liste fournie. Tout nombre dans une affirmation doit venir d'une preuve citée dans la même affirmation.
- Langage de cohérence, jamais de conseil réglementé : dis quel scénario est « le plus cohérent avec le profil déclaré », sans dire d'acheter, de vendre ou d'investir. Aucune prévision de rendement futur, aucune promesse. Les statistiques sont historiques.
  N'utilise JAMAIS les racines « recommand* » ou « conseill* » (même « recommandé par le profil » : utilise « plafond de référence » ou « le plus cohérent avec le profil déclaré »).
- Distingue les faits (preuves « fact »), les hypothèses (« assumption ») et les données fictives (« fictional »). Si une preuve est fictive ou une hypothèse, mentionne-le dans les limites.
- Contexte crypto DefiLlama : s'il est fourni dans les preuves (ex. TVL Ethereum, offre de stablecoins), tu peux le citer de manière purement descriptive dans « quelles_donnees » ou « limites » avec son identifiant de preuve (par exemple « la valeur totale bloquée sur Ethereum était de ... au ... »), sans prévision, sans signal et sans conseil.
- Si la préférence esg_tilt est active, mentionne la « part du portefeuille dans des titres présents dans le fonds ESGV (indicateur indirect) » avec son identifiant de preuve pour le scénario retenu, et rappelle en une phrase dans les limites que l'indicateur repose sur les actions américaines et ne constitue pas un score ESG. Ne prétends jamais que le portefeuille « est ESG » ou « est durable ».
- Pas de raisonnement interne : seulement des constats observables.
- avertissement : « Simulation éducative. Aucun conseil personnalisé. »"""

SYSTEM_EN = """You are the explainability agent for an educational financial simulation decision-aid tool.
You directly evaluate the requested investment idea, whatever its asset class (stock, ETF/index, crypto, gold, or another asset in the universe), against the stated profile and available evidence. Be clear and plain-spoken.
You answer the four BNCD governance questions: which data, why this choice, which limits, what would change the answer.
You distinguish risk tolerance (what the person says they accept) and risk capacity (what their situation can absorb).
Named risk types are: market, credit, liquidity, interest rate and inflation, currency, concentration.

Strict rules:
- Respond using the exact schema keys: resume, quelles_donnees, pourquoi_ce_choix, limites, ce_qui_changerait_la_reponse, incertitude, scenario_le_plus_coherent, avertissement.
- The resume is the direct, concise primary answer (2 paragraphs): clearly state whether the idea is consistent, partly consistent, or poorly consistent with risk tolerance AND capacity, objective, and horizon. If poorly consistent, say so plainly and explain the key risk without alarmism. Never imply knowledge of a portfolio whose holdings were not provided. In that case, state that the requested weight is evaluated against a hypothetical portfolio and its real impact depends on unknown current holdings.
- Be concise: keep the resume to 1 or 2 direct sentences across two short paragraphs, and limit every other section to 1 or 2 brief claims.
- Adapt the analysis to the requested asset (stock: company and concentration risk; ETF/index: underlying exposures and available overlaps; crypto: volatility and market risk; gold: commodity, currency and rates; others based on available data). Do not apply one asset class's reasoning to another.
- Ground the assessment in asset-specific evidence (history, risk, available liquidity), actual news, and macro indicators actually provided. Never invent market cycles, valuation, market capitalization, or volume. State important missing data in the limitations; do not imply macro conditions have a proven asset-specific effect unless evidence supports it.
- Numbers in the summary: You may reuse only numbers present in the user's request. Any other number must immediately include its evidence id in brackets (e.g. '23.2% [EP3]').
- Number rule (checked automatically): copy each number exactly as printed after '=' in the cited evidence (e.g. '38.0%'). Write NO other number: no cap, floor, threshold, equity percentage or year, unless it appears in an evidence item cited in the same claim or in the user's request. Without evidence, say it without a figure ('above the reference cap').
- Do not replace the three scenarios with a single one: compare them, then indicate the most consistent. If the profile has conflicts or objections exist, explain them.
- Every claim in the 4 sections must cite evidence ids (evidence field) taken ONLY from the provided list. Every number in a claim must come from an evidence item cited in the same claim.
- Consistency language, never advice: state which scenario is 'most consistent with the stated profile', without telling to buy, sell, or invest. No return forecast, no promise.
  NEVER use the roots 'recommend*' or 'advise*'.
- Distinguish facts ('fact' evidence), assumptions ('assumption'), and fictional data ('fictional').
- DefiLlama crypto context: if provided in the evidence (e.g. Ethereum TVL, stablecoin supply), you may cite it purely descriptively in 'quelles_donnees' or 'limites' with its evidence id (e.g. 'the total value locked on Ethereum was ... as of ...'), with no forecast, no signal, and no advice.
- If the esg_tilt preference is active, mention the 'share of the portfolio in assets held by the ESGV fund (indirect indicator)' with its evidence id for the most consistent scenario, and state the limit in one sentence under limits (U.S. stocks only, fund membership is not an ESG score). Never claim that the portfolio 'is ESG' or 'is sustainable'.
- avertissement: 'Educational simulation. No personalized advice.'"""


# ----------------------------------------------------------------------- context building
_PERCENT_UNITS = {"ratio", "%", "pct", "percent"}


def _fr(x: float, digits: int) -> str:
    return f"{x:.{digits}f}".replace(".", ",")


def _weight_text(weight_pct: float, language: str) -> str:
    precision = 2 if abs(weight_pct) < 1 else 1
    text = f"{weight_pct:.{precision}f}".rstrip("0").rstrip(".")
    return text.replace(".", ",") if language == "fr" else text


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

    requested_ticker = (
        state.profile.requested_idea.get("ticker")
        if state.profile and state.profile.requested_idea
        else None
    )
    ordered: list[Evidence] = []
    evidence_items = sorted(
        state.evidence.items(),
        key=lambda kv: (
            kv[0][:2] != "EQ"
            and kv[0][:2] not in ("EP", "EM", "ES", "EN"),
            not (
                kv[0][:2] == "EQ"
                and isinstance(kv[1].value, dict)
                and kv[1].value.get("ticker") == requested_ticker
            ),
            kv[0][:2],
            int(kv[0][2:]),
        ),
    )
    for eid, ev in evidence_items:
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
    portfolio_label = (
        "portefeuille actuel fourni"
        if sc.name == "current"
        else "portefeuille simulé"
    )
    lines = [f"- {sc.name} : indicateurs historiques du {portfolio_label}"]
    for m, eid in sc.metrics.items():
        ev = evidence.get(eid)
        if ev is not None:
            lines.append(f"    {m} : {eid} = {printable(ev)} ({ev.method}, {ev.confidence})")
    return "\n".join(lines)


def _decision_context(state: GraphState) -> list[str]:
    profile = state.profile
    idea = profile.requested_idea if profile else None
    if not idea:
        return []

    ticker = idea.get("ticker")
    info = get_provider().asset_info()
    if ticker not in info.index:
        return [f"Actif demandé : {ticker}; métadonnées et historique indisponibles."]

    asset = info.loc[ticker]
    lines = [
        f"Actif demandé : {ticker}, classe={asset['asset_class']}, secteur={asset['sector']}."
    ]
    metric_names = {
        "volatility_ann",
        "max_drawdown",
        "stress_2022",
        "correlation",
        "etf_overlap",
        "avg_daily_traded_value_20d_cad",
    }
    for ev in _select_evidence(state):
        value = ev.value
        if not isinstance(value, dict) or value.get("ticker") != ticker:
            continue
        metric = value.get("metric")
        if metric in metric_names:
            lines.append(describe_evidence(ev))

    related_events = [event for event in state.events if event.get("ticker") == ticker]
    if related_events:
        lines.append(
            "Actualités datées retenues pour l'actif : "
            + "; ".join(
                f"{event['headline']} [{event['evidence_id']}]"
                for event in related_events
            )
        )
    elif any(
        isinstance(ev.value, dict)
        and ev.value.get("metric") == "news_items_retained"
        for ev in state.evidence.values()
    ):
        lines.append("Aucune actualité datée n'a été retenue pour cet actif.")

    macro = [
        ev for ev in _select_evidence(state)
        if isinstance(ev.value, dict)
        and str(ev.value.get("metric", "")).startswith(
            ("policy_rate_", "yield_", "cpi_", "unemployment_")
        )
    ]
    if macro:
        lines.append("Indicateurs macro disponibles : " + "; ".join(map(describe_evidence, macro)))
    lines.append(
        "Capitalisation boursière, valorisation fondamentale et phase de cycle : "
        "non disponibles dans les données de cette analyse; ne pas les inférer."
    )
    if profile and not profile.current_holdings:
        lines.append(
            "Portefeuille actuel non fourni : les poids du scénario demandé hors actif ciblé "
            "sont une hypothèse de simulation, pas les avoirs du client."
        )
    return lines


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
            *_decision_context(state),
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
        *_decision_context(state),
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


def _best_scenario(state: GraphState) -> Scenario:
    candidates = [sc for sc in state.scenarios if sc.name in SCENARIO_NAMES]
    if not candidates:
        raise ValueError("No comparable scenario is available for the explanation.")
    profile = state.profile
    level = (
        effective_risk(profile.risk_tolerance, profile.risk_capacity)
        if profile
        else "moderate"
    )
    name = (
        "profile_baseline"
        if level in ("low", "low_moderate")
        or (profile and profile.objective == "capital_preservation")
        else "capped"
    )
    selected = next((sc for sc in candidates if sc.name == name), None)
    if selected:
        return selected
    return min(
        candidates,
        key=lambda sc: abs(_metric_value(state, sc, "max_drawdown") or 0),
    )


def _requested_assessment(state: GraphState) -> tuple[str | None, float | None, bool]:
    profile = state.profile
    idea = profile.requested_idea if profile else None
    if not idea:
        return None, None, False

    ticker = idea.get("ticker")
    weight = idea.get("weight")
    weight_pct = round(float(weight) * 100, 2) if weight is not None else None
    info = get_provider().asset_info()
    if ticker not in info.index or weight is None:
        return ticker, weight_pct, bool(profile.conflicts)

    risk_level = effective_risk(profile.risk_tolerance, profile.risk_capacity)
    caps = CAPS.get(risk_level, CAPS["moderate"])
    asset_class = info.at[ticker, "asset_class"]
    cap_key = (
        "single_stock"
        if asset_class == "equity"
        else "crypto_total"
        if asset_class == "crypto"
        else "etf"
    )
    incompatible = bool(profile.conflicts) or float(weight) > caps[cap_key]
    return ticker, weight_pct, incompatible


def _market_summary(state: GraphState, ticker: str | None, language: str) -> str:
    if not ticker:
        return (
            "The available evidence compares simulated portfolio risk; no specific asset was "
            "requested."
            if language == "en"
            else "Les preuves disponibles comparent le risque des portefeuilles simulés; aucun actif précis n'a été demandé."
        )

    metrics = {}
    for ev in state.evidence.values():
        value = ev.value
        if isinstance(value, dict) and value.get("ticker") == ticker:
            metrics[value.get("metric")] = ev
    details = []
    for metric, label in (
        ("volatility_ann", "volatilité annualisée historique" if language == "fr" else "historical annualized volatility"),
        ("max_drawdown", "perte maximale historique" if language == "fr" else "historical maximum loss"),
        ("stress_2022", "rendement pendant le choc de marché de 2022" if language == "fr" else "return during the 2022 market stress"),
        ("avg_daily_traded_value_20d_cad", "valeur quotidienne moyenne échangée en CAD" if language == "fr" else "average daily traded value in CAD"),
    ):
        ev = metrics.get(metric)
        if ev:
            details.append(f"{label} : {printable(ev)} [{ev.id}]")

    events = [event for event in state.events if event.get("ticker") == ticker]
    if events:
        details.append(
            ("Actualités : " if language == "fr" else "News: ")
            + (
                "des éléments datés relatifs à cet actif ont été retenus "
                if language == "fr"
                else "dated items related to this asset were retained "
            )
            + " ".join(f"[{event['evidence_id']}]" for event in events)
        )
    macro = [
        ev for ev in state.evidence.values()
        if isinstance(ev.value, dict)
        and ev.value.get("metric") in {
            "policy_rate_ca", "policy_rate_us", "cpi_yoy_ca", "cpi_yoy_us"
        }
    ]
    if macro:
        details.append(
            (
                "Contexte macro (taux directeurs et inflation) : "
                if language == "fr"
                else "Macro context (policy rates and inflation): "
            )
            + "; ".join(
                f"{ev.value['metric']} : {printable(ev)} [{ev.id}]"
                for ev in macro
            )
            + (
                "; contexte général, sans prédire la trajectoire de l'actif"
                if language == "fr"
                else "; general context, not a prediction of the asset's path"
            )
            if language == "fr"
            else "Observed macro context includes rates and inflation, but cannot by itself predict this asset's path."
        )
    else:
        details.append(
            "Aucun indicateur macro exploitable n'est disponible."
            if language == "fr"
            else "No usable macro indicator is available."
        )
    if not metrics:
        details.insert(
            0,
            "No asset-specific historical metrics are available."
            if language == "en"
            else "Aucun indicateur historique propre à cet actif n'est disponible."
        )
    details.append(
        "Market capitalization, fundamental valuation, and an economic-cycle assessment are not available."
        if language == "en"
        else "Capitalisation boursière, valorisation fondamentale et phase du cycle économique ne sont pas disponibles"
    )
    return "; ".join(details) + "."


def template_explanation(state: GraphState) -> dict:
    """Explanation built from the evidence without a model (used when the LLM fails)."""
    lang = getattr(state.profile, "language", None) or getattr(state, "language", "fr")

    best = _best_scenario(state)
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
    # DefiLlama crypto context when present in evidence
    ev_tvl = next(
        (
            e
            for e in state.evidence.values()
            if isinstance(e.value, dict) and e.value.get("metric") == "eth_tvl"
        ),
        None,
    )
    if ev_tvl is not None:
        if lang == "en":
            donnees.append(
                {
                    "claim": (
                        f"According to DefiLlama, the total value locked on Ethereum was "
                        f"{printable(ev_tvl)} USD as of {ev_tvl.date}."
                    ),
                    "evidence": [ev_tvl.id],
                }
            )
        else:
            donnees.append(
                {
                    "claim": (
                        f"Selon DefiLlama, la valeur totale bloquée sur Ethereum était de "
                        f"{printable(ev_tvl)} USD au {ev_tvl.date}."
                    ),
                    "evidence": [ev_tvl.id],
                }
            )
    bm = _metric_value(state, best, "max_drawdown")
    if bm is not None:
        caps_evidence = [
            eid for eid, ev in state.evidence.items()
            if isinstance(ev.value, dict) and ev.value.get("metric") == "caps"
        ]
        if lang == "en":
            tol_str = (
                TOLERANCE_EN.get(state.profile.risk_tolerance, state.profile.risk_tolerance)
                if state.profile
                else ""
            )
            pourquoi.append(
                {
                    "claim": (
                        f"The {best.name} scenario respects the profile's risk limits and has a "
                        f"historical maximum loss of {_fr(abs(bm) * 100, 1)} %, making it the "
                        f"most consistent with a '{tol_str}' risk tolerance."
                    ),
                    "evidence": [best.metrics["max_drawdown"], *caps_evidence],
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
                        f"Le scénario {best.name} respecte les limites de risque du profil et affiche "
                        f"une perte maximale historique de {_fr(abs(bm) * 100, 1)} %, ce qui le rend "
                        f"le plus cohérent avec une tolérance au risque « {tol_str} »."
                    ),
                    "evidence": [best.metrics["max_drawdown"], *caps_evidence],
                }
            )

    if state.profile and "esg_tilt" in state.profile.preferences:
        esg_val = _metric_value(state, best, "esg_proxy_share")
        if esg_val is not None and "esg_proxy_share" in best.metrics:
            if lang == "en":
                donnees.append(
                    {
                        "claim": (
                            f"Scenario {best.name}: share of the portfolio in assets held by the ESGV fund "
                            f"(indirect proxy) of {_fr(abs(esg_val) * 100, 1)} %."
                        ),
                        "evidence": [best.metrics["esg_proxy_share"]],
                    }
                )
            else:
                donnees.append(
                    {
                        "claim": (
                            f"Scénario {best.name} : part du portefeuille dans des titres présents dans le fonds ESGV "
                            f"(indicateur indirect) de {_fr(abs(esg_val) * 100, 1)} %."
                        ),
                        "evidence": [best.metrics["esg_proxy_share"]],
                    }
                )
    ticker, weight_pct, incompatible = _requested_assessment(state)
    horizon = getattr(state.profile, "horizon_years", 5) if state.profile else 5
    scenario_label = "le scénario ajusté" if best.name == "capped" else "le profil de référence"

    capacity = state.profile.risk_capacity if state.profile else "moderate"
    capacity_label = (
        {"low": "faible", "moderate": "modérée", "high": "élevée"}.get(capacity, capacity)
        if lang != "en"
        else {"low": "low", "moderate": "moderate", "high": "high"}.get(capacity, capacity)
    )

    proxy_eids = [
        eid for eid, ev in state.evidence.items()
        if (isinstance(ev.value, dict) and ev.value.get("metric") == "esg_proxy")
        or (isinstance(ev.value, str) and "Proxy ESG" in ev.value)
    ]

    if lang == "en":
        tol_str = (
            TOLERANCE_EN.get(state.profile.risk_tolerance, state.profile.risk_tolerance)
            if state.profile
            else "moderate"
        )
        if ticker and weight_pct is not None:
            verdict = "poorly consistent" if incompatible else "within the profile's exposure limit"
            p1 = (
                f"Your request to allocate {_weight_text(weight_pct, 'en')} % to {ticker} is {verdict} with your "
                f"{tol_str} risk tolerance, {capacity_label} capacity, and {horizon}-year horizon"
            )
            if incompatible:
                p1 += "; it conflicts with your profile's risk limits"
            p1 += f"; the {best.name.replace('_', ' ')} scenario is the most consistent."
        elif ticker:
            p1 = (
                f"Your proposed exposure to {ticker} is "
                f"{'poorly consistent' if incompatible else 'within the profile limits'} with "
                f"your {tol_str} risk tolerance, {capacity_label} capacity, and {horizon}-year horizon."
            )
        else:
            p1 = (
                f"Your asset allocation request was evaluated for a {horizon}-year horizon with a {tol_str} risk profile. "
                f"The {best.name.replace('_', ' ')} scenario emerges as the most consistent structure with your wealth objectives."
            )

        p2 = _market_summary(state, ticker, "en")
        if state.profile and not state.profile.current_holdings:
            p2 += (
                " Current holdings were not provided, so the simulated remainder is hypothetical "
                "and does not describe your portfolio."
            )
        resume = f"{p1}\n\n{p2}"

        if not donnees:
            donnees = [{"claim": "No numerical metrics available.", "evidence": []}]
        if not pourquoi:
            pourquoi = [{"claim": "The choice is based on the declared profile.", "evidence": []}]
        limites = [
            {"claim": "This explanation was generated from a template, without a language model.", "evidence": []},
            {"claim": "Historical statistics do not describe the future.", "evidence": []},
            {"claim": "Market capitalization, fundamental valuation, and a reliable market-cycle assessment are not available in this dataset.", "evidence": []},
        ]
        ev_cross = next(
            (
                e
                for e in state.evidence.values()
                if isinstance(e.value, dict) and e.value.get("metric") == "btc_price_cross_check"
            ),
            None,
        )
        if ev_cross is not None:
            limites.append(
                {
                    "claim": (
                        f"DefiLlama's Bitcoin price shows a relative gap of {printable(ev_cross)} "
                        f"compared to the data provider close as of {ev_cross.date}."
                    ),
                    "evidence": [ev_cross.id],
                }
            )
        if state.profile and "esg_tilt" in state.profile.preferences:
            limites.append(
                {
                    "claim": (
                        "The share of the portfolio in assets held by the ESGV fund (indirect proxy) "
                        "is limited to U.S. equities and fund membership does not constitute an ESG score."
                    ),
                    "evidence": proxy_eids[:1],
                }
            )
        if state.profile and state.profile.conflicts:
            limites.append(
                {"claim": "The profile has contradictions with the formulated request.", "evidence": []}
            )
        if state.profile and not state.profile.current_holdings:
            limites.append(
                {"claim": "Current holdings were not provided; the remaining simulated allocation is hypothetical.", "evidence": []}
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
    if ticker and weight_pct is not None:
        verdict = "peu cohérente" if incompatible else "compatible avec la limite d'exposition du profil"
        p1 = (
            f"Consacrer {_weight_text(weight_pct, 'fr')} % à {ticker} est {verdict}, au regard de votre tolérance "
            f"au risque {tol_str}, de votre capacité {capacity_label} et de votre horizon de {horizon} ans"
        )
        if incompatible:
            p1 += "; cette part dépasse le cadre de risque du profil"
        p1 += f"; le scénario {best.name.replace('_', ' ')} est le plus cohérent."
    elif ticker:
        p1 = (
            f"L'exposition proposée à {ticker} est "
            f"{'peu cohérente' if incompatible else 'compatible avec les limites du profil'}, "
            f"au regard de votre tolérance au risque {tol_str}, de votre capacité {capacity_label} "
            f"et de votre horizon de {horizon} ans."
        )
    else:
        p1 = (
            f"Votre demande d'allocation a été évaluée pour un horizon de {horizon} ans avec une tolérance au risque {tol_str}. "
            f"{scenario_label.capitalize()} ressort comme la structure la plus cohérente avec vos objectifs patrimoniaux."
        )

    p2 = _market_summary(state, ticker, "fr")
    if state.profile and not state.profile.current_holdings:
        p2 += (
            " Vos avoirs ne sont pas fournis; le reste simulé est hypothétique et ne décrit "
            "pas votre portefeuille."
        )
    resume = f"{p1}\n\n{p2}"

    if not donnees:
        donnees = [{"claim": "Aucun indicateur chiffré n'est disponible.", "evidence": []}]
    if not pourquoi:
        pourquoi = [{"claim": "Le choix repose sur le profil déclaré.", "evidence": []}]
    limites = [
        {"claim": "Cette explication a été produite par un gabarit, sans modèle de langage.", "evidence": []},
        {"claim": "Les statistiques sont historiques et ne décrivent pas l'avenir.", "evidence": []},
        {"claim": "La capitalisation boursière, la valorisation fondamentale et une analyse fiable du cycle de marché ne sont pas disponibles dans ces données.", "evidence": []},
    ]
    ev_cross = next(
        (
            e
            for e in state.evidence.values()
            if isinstance(e.value, dict) and e.value.get("metric") == "btc_price_cross_check"
        ),
        None,
    )
    if ev_cross is not None:
        limites.append(
            {
                "claim": (
                    f"Le cours Bitcoin de DefiLlama présente un écart relatif de {printable(ev_cross)} "
                    f"par rapport au cours de clôture du fournisseur au {ev_cross.date}."
                ),
                "evidence": [ev_cross.id],
            }
        )
    if state.profile and "esg_tilt" in state.profile.preferences:
        limites.append(
            {
                "claim": (
                    "La part du portefeuille dans des titres présents dans le fonds ESGV (indicateur indirect) "
                    "est limitée aux actions américaines et l'appartenance au fonds ne constitue pas un score ESG."
                ),
                "evidence": proxy_eids[:1],
            }
        )
    if state.profile and state.profile.conflicts:
        limites.append(
            {"claim": "Le profil comporte des tensions avec la demande formulée.", "evidence": []}
        )
    if state.profile and not state.profile.current_holdings:
        limites.append(
            {"claim": "Les avoirs actuels ne sont pas fournis; la répartition simulée restante est hypothétique.", "evidence": []}
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
