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
- Le champ resume est la réponse principale, directe et brève (2 paragraphes) : ouvre directement par « Oui », « En partie » ou « Non » en une phrase selon que l'idée est cohérente, partiellement cohérente ou peu cohérente avec la tolérance ET la capacité, l'objectif et l'horizon. Si elle est peu cohérente, dis-le sans ambiguïté et explique le risque déterminant, sans dramatiser. Ne dis jamais que tu connais le portefeuille si ses positions n'ont pas été fournies. Dans ce cas, précise que le poids demandé est évalué sur un portefeuille hypothétique et que son impact réel dépend des avoirs actuels, inconnus.
- Style du résumé (lu par un non-spécialiste) : le premier paragraphe donne le constat en une phrase simple, avec un seul chiffre au plus. Le second paragraphe explique en langage courant, avec deux chiffres au plus, chacun introduit en toutes lettres par ce qu'il mesure (« la baisse maximale historique », « la volatilité annuelle »). Pas d'énumération de chiffres ni de parenthèses de chiffres : le détail chiffré va dans les sections.
- Nomme toujours les scénarios « votre demande telle quelle », « la version ajustée à vos limites » et « le profil de référence ». N'écris JAMAIS d'identifiant interne ni de nom de champ (as_requested, capped, profile_baseline, persona, policy_rate_ca, esg_tilt, etc.) : décris la chose en français courant.
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
- The resume is the direct, concise primary answer (2 paragraphs): open directly with 'Yes', 'Partly', or 'No' in one sentence according to whether the idea is consistent, partly consistent, or poorly consistent with risk tolerance AND capacity, objective, and horizon. If poorly consistent, say so plainly and explain the key risk without alarmism. Never imply knowledge of a portfolio whose holdings were not provided. In that case, state that the requested weight is evaluated against a hypothetical portfolio and its real impact depends on unknown current holdings.
- Summary style (read by a non-specialist): the first paragraph states the finding in one plain sentence, with at most one figure. The second paragraph explains in everyday language, with at most two figures, each introduced in words by what it measures ('the historical maximum drawdown', 'the annual volatility'). No lists of figures and no figures in parentheses: numeric detail belongs in the sections.
- Always name the scenarios 'your request as is', 'the version adjusted to your limits' and 'the reference profile'. NEVER write an internal identifier or field name (as_requested, capped, profile_baseline, persona, policy_rate_ca, esg_tilt, etc.): describe the thing in plain English.
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
    # Reading assumptions ("Hypothèse ...") are not conflicts: only real ones make the idea incompatible.
    incompatible = bool(_real_conflicts(profile)) or float(weight) > caps[cap_key]
    return ticker, weight_pct, incompatible


# ----------------------------------------------------------------------- plain-language resume
# Names shown to the user. The verifier maps these words back to the scenario.
_SCENARIO_FR = {
    "as_requested": "votre demande telle quelle",
    "capped": "la version ajustée à vos limites",
    "profile_baseline": "le profil de référence",
    "current": "votre portefeuille actuel",
}
_SCENARIO_EN = {
    "as_requested": "your request as is",
    "capped": "the version adjusted to your limits",
    "profile_baseline": "the reference profile",
    "current": "your current portfolio",
}
POINTER_FR = "La répartition détaillée et la vérification de vos limites sont dans Voir les détails."
POINTER_EN = "The detailed allocation and the check of your limits are under Show details."
MAX_BREACH_SENTENCES = 5

_COUNT_FR = ("zéro", "une", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf",
             "dix", "onze", "douze")
_COUNT_EN = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
             "ten", "eleven", "twelve")

# Share of the portfolio in words (lower bound, French, English). No digit: these words are
# not figures, so they need no evidence id.
_FRACTIONS = (
    (0.90, "la quasi-totalité", "almost all"),
    (0.80, "la grande majorité", "the large majority"),
    (0.70, "environ les trois quarts", "about three quarters"),
    (0.58, "environ les deux tiers", "about two thirds"),
    (0.45, "environ la moitié", "about half"),
    (0.37, "un peu plus du tiers", "a little over a third"),
    (0.29, "environ un tiers", "about a third"),
    (0.22, "environ un quart", "about a quarter"),
    (0.17, "environ un cinquième", "about a fifth"),
    (0.13, "environ un sixième", "about a sixth"),
    (0.08, "environ un dixième", "about a tenth"),
    (0.0, "une petite part", "a small share"),
)

# Group -> (French singular with article, French plural, English singular, English plural).
_GROUPS = {
    "tech": ("une grande entreprise technologique", "grandes entreprises technologiques",
             "one large technology company", "large technology companies"),
    "equity_other": ("une action d'un autre secteur", "actions d'autres secteurs",
                     "one stock from another sector", "stocks from other sectors"),
    "etf_us": ("un FNB d'actions américaines", "FNB d'actions américaines",
               "one U.S. equity ETF", "U.S. equity ETFs"),
    "etf_ca": ("un FNB d'actions canadiennes", "FNB d'actions canadiennes",
               "one Canadian equity ETF", "Canadian equity ETFs"),
    "bond": ("un FNB d'obligations", "FNB d'obligations", "one bond ETF", "bond ETFs"),
    "gold": ("un FNB adossé à l'or", "FNB adossés à l'or", "one gold ETF", "gold ETFs"),
    "crypto": ("un cryptoactif", "cryptoactifs", "one crypto asset", "crypto assets"),
    "other": ("un autre actif", "autres actifs", "one other asset", "other assets"),
}
_TECH_SECTORS = {"Information Technology", "Communication Services"}
_MIN_GROUP_SHARE = 0.08
_MAX_GROUPS = 3


def scenario_label(name: str, language: str = "fr") -> str:
    """Plain-language name of a scenario, as written in the answer."""
    table = _SCENARIO_EN if language == "en" else _SCENARIO_FR
    return table.get(name, name)


def _scenario_fr(name: str) -> str:
    return scenario_label(name, "fr")


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _count_word(n: int, language: str) -> str:
    words = _COUNT_EN if language == "en" else _COUNT_FR
    if 0 <= n < len(words):
        return words[n]
    return "several" if language == "en" else "plusieurs"


def _fraction_word(share: float, language: str) -> str:
    for floor, fr, en in _FRACTIONS:
        if share >= floor:
            return en if language == "en" else fr
    return _FRACTIONS[-1][2 if language == "en" else 1]


def _asset_group(ticker: str, info) -> str:
    if ticker not in info.index:
        return "other"
    asset_class = str(info.at[ticker, "asset_class"])
    if asset_class == "equity":
        return "tech" if str(info.at[ticker, "sector"]) in _TECH_SECTORS else "equity_other"
    if asset_class == "etf_equity":
        return "etf_ca" if str(info.at[ticker, "currency"]) == "CAD" else "etf_us"
    if asset_class == "etf_bond":
        return "bond"
    if asset_class == "etf_commodity":
        return "gold"
    if asset_class == "crypto":
        return "crypto"
    return "other"


def describe_allocation(sc: Scenario, language: str = "fr") -> str:
    """The scenario's weights in words, without a table and without a digit.

    Example: "Environ la moitié dans six grandes entreprises technologiques, environ un tiers
    dans deux FNB d'actions américaines, et le reste en petites positions."
    """
    en = language == "en"
    info = get_provider().asset_info()
    shares: dict[str, float] = {}
    counts: dict[str, int] = {}
    for ticker, weight in sc.weights.items():
        if weight <= 0:
            continue
        group = _asset_group(ticker, info)
        shares[group] = shares.get(group, 0.0) + float(weight)
        counts[group] = counts.get(group, 0) + 1
    if not shares:
        return ""
    ordered = sorted(shares, key=lambda g: (-shares[g], g))
    shown = [g for g in ordered if shares[g] >= _MIN_GROUP_SHARE][:_MAX_GROUPS] or ordered[:1]
    parts = []
    for group in shown:
        fr_one, fr_many, en_one, en_many = _GROUPS[group]
        n = counts[group]
        if n == 1:
            what = en_one if en else fr_one
        else:
            what = f"{_count_word(n, language)} {en_many if en else fr_many}"
        parts.append(f"{_fraction_word(shares[group], language)} {'in' if en else 'dans'} {what}")
    rest = 1.0 - sum(shares[g] for g in shown)
    if rest > 0.03:
        if rest <= 0.20:
            tail = "the rest in small positions" if en else "le reste en petites positions"
        else:
            tail = (
                "the rest spread across other kinds of assets"
                if en
                else "le reste réparti entre d'autres catégories d'actifs"
            )
        text = ", ".join(parts) + (", and " if en else ", et ") + tail
    elif len(parts) > 1:
        text = ", ".join(parts[:-1]) + (" and " if en else " et ") + parts[-1]
    else:
        text = parts[0]
    return _cap(text) + "."


def scenario_breaches(state: GraphState, name: str) -> list[dict]:
    """Guardrail entries with status "breach" for the scenario `name`."""
    return [
        g for g in state.guardrails or []
        if isinstance(g, dict) and g.get("status") == "breach" and g.get("scenario") == name
    ]


def _breach_context(state: GraphState) -> list[float]:
    """The user's own numbers (declared limits), which a breach sentence may restate."""
    out: list[float] = []
    p = state.profile
    if p:
        for limit in (p.max_loss_12m, p.crypto_target_min, p.sector_cap):
            if isinstance(limit, (int, float)):
                out.append(float(limit))
    for g in state.guardrails or []:
        declared = g.get("declared") if isinstance(g, dict) else None
        if isinstance(declared, (int, float)) and not isinstance(declared, bool):
            out.append(float(declared))
    return out


def breach_sentence(state: GraphState, entry: dict, language: str = "fr") -> str:
    """One sentence for a crossed limit: its figure, then its evidence ids in brackets.

    The guardrail's own message is used when every figure in it is backed by the cited
    evidence or by a declared limit; otherwise the sentence names the limit without a figure,
    so the number rules always hold.
    """
    from alphaforge.evidence import EID_RE
    from alphaforge.nodes.verifier import check_numbers

    en = language == "en"
    ids = [e for e in entry.get("evidence") or [] if e in state.evidence]
    message = str(entry.get("message_en" if en else "message_fr") or "").strip()
    label = str(entry.get("label_en" if en else "label_fr") or "").strip().rstrip(".")
    candidates = []
    if message:
        candidates.append(message)
    if label:
        candidates.append(
            f"A limit you declared is crossed: {label}."
            if en
            else f"Une limite que vous avez déclarée est dépassée : {label}."
        )
    candidates.append(
        "A limit you declared is crossed."
        if en
        else "Une limite que vous avez déclarée est dépassée."
    )
    context = _breach_context(state)
    for text in candidates:
        missing = [e for e in ids if e not in EID_RE.findall(text)]
        if missing:
            body = text.rstrip()
            end = body[-1] if body[-1:] in ".!?" else ""
            body = body[: len(body) - len(end)].rstrip()
            text = f"{body} [{', '.join(missing)}]{end or '.'}"
        elif text[-1:] not in ".!?":
            text += "."
        if not check_numbers({"resume": text}, state.evidence, context):
            return text
    return candidates[-1]


def _real_conflicts(profile) -> list[str]:
    """Profile conflicts, without the entries that only record a reading assumption."""
    return [
        c for c in (profile.conflicts if profile else [])
        if not str(c).lstrip().lower().startswith(("hypothèse", "assumption"))
    ]


def _profile_words(state: GraphState, language: str) -> str:
    p = state.profile
    if p is None:
        return "declared profile" if language == "en" else "profil déclaré"
    capacity = p.risk_capacity
    if language == "en":
        tol = TOLERANCE_EN.get(p.risk_tolerance, p.risk_tolerance)
        cap = {"low": "low", "moderate": "moderate", "high": "high"}.get(capacity, capacity)
        return f"{tol} risk tolerance, {cap} capacity, {p.horizon_years}-year horizon"
    tol = TOLERANCE_FR.get(p.risk_tolerance, p.risk_tolerance)
    cap = {"low": "faible", "moderate": "modérée", "high": "élevée"}.get(capacity, capacity)
    return f"tolérance au risque {tol}, capacité {cap}, horizon de {p.horizon_years} ans"


def _comparison_paragraph(state: GraphState, best: Scenario, language: str) -> str:
    """Compares the request as is with the selected version; every direction word comes from
    the sign of the metric delta."""
    en = language == "en"
    request = next((sc for sc in state.scenarios if sc.name == "as_requested"), None)
    sentences = []
    if request is not None and request.name != best.name:
        r_mdd = _metric_value(state, request, "max_drawdown")
        b_mdd = _metric_value(state, best, "max_drawdown")
        if r_mdd is not None and b_mdd is not None:
            r_txt, b_txt = _fr(abs(r_mdd) * 100, 1), _fr(abs(b_mdd) * 100, 1)
            r_id, b_id = request.metrics["max_drawdown"], best.metrics["max_drawdown"]
            if r_txt == b_txt:
                direction = "a comparable loss" if en else "une baisse comparable"
            elif abs(b_mdd) < abs(r_mdd):
                direction = "a smaller loss" if en else "une baisse plus faible"
            else:
                direction = "a larger loss" if en else "une baisse plus forte"
            if en:
                sentences.append(
                    f"Over the available history, the historical maximum loss is {r_txt} % "
                    f"[{r_id}] with {scenario_label(request.name, 'en')} and {b_txt} % [{b_id}] "
                    f"with {scenario_label(best.name, 'en')}, that is {direction}."
                )
            else:
                sentences.append(
                    f"Sur l'historique disponible, la baisse maximale historique est de {r_txt} % "
                    f"[{r_id}] avec {scenario_label(request.name, 'fr')} et de {b_txt} % [{b_id}] "
                    f"avec {scenario_label(best.name, 'fr')}, soit {direction}."
                )
        r_top = _metric_value(state, request, "top_weight")
        b_top = _metric_value(state, best, "top_weight")
        if r_top is not None and b_top is not None and abs(r_top - b_top) >= 0.005:
            if b_top < r_top:
                sentences.append(
                    "Its largest position is also smaller."
                    if en
                    else "Sa plus grosse position y est aussi plus petite."
                )
            else:
                sentences.append(
                    "Its largest position, however, is larger."
                    if en
                    else "Sa plus grosse position y est en revanche plus grande."
                )
    if not sentences:
        sentences.append(
            "The figures that compare the versions are in the details."
            if en
            else "Les chiffres qui comparent les versions sont dans les détails."
        )
    if state.profile and not state.profile.current_holdings:
        sentences.append(
            "Your holdings were not provided: the rest of the simulated portfolio is "
            "hypothetical and does not describe your portfolio."
            if en
            else "Vos avoirs ne sont pas fournis : le reste du portefeuille simulé est "
            "hypothétique et ne décrit pas votre portefeuille."
        )
    return " ".join(sentences)


def template_resume(state: GraphState, best: Scenario, language: str = "fr") -> str:
    """The plain-language answer: verdict, comparison, crossed limits, pointer to the details."""
    en = language == "en"
    profile = state.profile
    ticker, weight_pct, incompatible = _requested_assessment(state)
    words = _profile_words(state, language)
    best_label = scenario_label(best.name, language)
    n_scenarios = _count_word(len(state.scenarios), language)
    request_breaches = scenario_breaches(state, "as_requested")
    is_judge = bool(ticker) or (profile is not None and profile.request_type == "judge")

    if is_judge:
        if ticker and weight_pct is not None:
            subject = (
                f"putting {_weight_text(weight_pct, 'en')} % in {ticker}"
                if en
                else f"consacrer {_weight_text(weight_pct, 'fr')} % à {ticker}"
            )
        elif ticker:
            subject = f"the proposed exposure to {ticker}" if en else f"l'exposition proposée à {ticker}"
        else:
            subject = "your request as is" if en else "votre demande telle quelle"
            incompatible = bool(_real_conflicts(profile))
        if incompatible:
            p1 = (
                f"No: this idea is poorly consistent with your profile because {subject} goes beyond its risk framework ({words})."
                if en
                else f"Non : cette idée est peu cohérente avec votre profil parce que {subject} dépasse son cadre de risque ({words})."
            )
        elif request_breaches:
            p1 = (
                f"Partly: this idea is partly consistent with your profile ({words}), but {subject} crosses at least one limit you declared."
                if en
                else f"En partie : cette idée est partiellement cohérente avec votre profil "
                f"({words}), mais {subject} dépasse au moins une limite que vous avez déclarée."
            )
        else:
            p1 = (
                f"Yes: this idea is consistent with your profile; {subject} stays inside its risk framework ({words})."
                if en
                else f"Oui : cette idée est cohérente avec votre profil ; {subject} reste dans le cadre de risque de votre profil ({words})."
            )
        p1 += (
            f" Of the {n_scenarios} versions compared, {best_label} is the closest to your "
            "declared profile."
            if en
            else f" Parmi les {n_scenarios} versions comparées, c'est {best_label} qui "
            "correspond le mieux à votre profil déclaré."
        )
    else:
        p1 = (
            f"Here is the simulated portfolio built for your request: of the {n_scenarios} "
            f"versions compared, {best_label} is the closest to your declared profile ({words})."
            if en
            else f"Voici le portefeuille simulé construit pour votre demande : parmi les "
            f"{n_scenarios} versions comparées, c'est {best_label} qui correspond le mieux à "
            f"votre profil déclaré ({words})."
        )
        description = describe_allocation(best, language)
        if description:
            p1 += " " + description

    paragraphs = [p1, _comparison_paragraph(state, best, language)]
    breaches = scenario_breaches(state, best.name)
    if breaches:
        sentences = [breach_sentence(state, b, language) for b in breaches[:MAX_BREACH_SENTENCES]]
        sentences = list(dict.fromkeys(sentences))
        if len(breaches) > MAX_BREACH_SENTENCES:
            sentences.append(
                "Other declared limits are crossed as well."
                if en
                else "D'autres limites déclarées sont aussi dépassées."
            )
        paragraphs.append(" ".join(sentences))
    paragraphs.append(POINTER_EN if en else POINTER_FR)
    return "\n\n".join(paragraphs)


def _asset_claim(state: GraphState, language: str) -> dict | None:
    """Historical metrics of the requested asset, as one claim for the data section."""
    idea = state.profile.requested_idea if state.profile else None
    ticker = idea.get("ticker") if idea else None
    if not ticker:
        return None
    found: dict[str, Evidence] = {}
    for ev in state.evidence.values():
        value = ev.value
        if isinstance(value, dict) and value.get("ticker") == ticker and value.get("metric"):
            found.setdefault(str(value["metric"]), ev)
    labels = (
        ("volatility_ann", "volatilité annualisée historique", "historical annualized volatility"),
        ("max_drawdown", "perte maximale historique", "historical maximum loss"),
        ("stress_2022", "rendement pendant le choc de marché de 2022",
         "return during the 2022 market stress"),
    )
    parts, ids = [], []
    for metric, fr, en in labels:
        ev = found.get(metric)
        if ev is not None and numeric(ev) is not None:
            parts.append(f"{en if language == 'en' else fr} {printable(ev)}")
            ids.append(ev.id)
    if not parts:
        return None
    sep = ": " if language == "en" else " : "
    return {"claim": f"{ticker}{sep}{', '.join(parts)}.", "evidence": ids}


# Internal terms that must not reach the plain-language answer, with their replacement.
_PLAIN_TERMS = {
    "fr": (
        (r"\b(?:le |du |au )?sc[ée]nario plafonn[ée]\b", "la version ajustée à vos limites"),
        (r"\b(?:le |du |au )?sc[ée]nario (?:brut )?demand[ée]\b", "votre demande telle quelle"),
        (r"\bas[_ ]requested\b", "votre demande telle quelle"),
        (r"\bcapped\b", "la version ajustée à vos limites"),
        (r"\bprofile[_ ]baseline\b", "le profil de référence"),
        (r"\b(?:indice |l'indice )?HHI(?: sectoriel)?\b", "concentration"),
        (r"\bturnover\b", "rotation du portefeuille"),
        (r"\bpersonas?\b", "profil"),
        (r"\bproxy\b", "indicateur indirect"),
        (r"\bpolicy_rate_ca\b", "taux directeur au Canada"),
        (r"\bpolicy_rate_us\b", "taux directeur aux États-Unis"),
        (r"\bcpi_yoy_ca\b", "inflation au Canada"),
        (r"\bcpi_yoy_us\b", "inflation aux États-Unis"),
    ),
    "en": (
        (r"\bthe capped scenario\b", "the version adjusted to your limits"),
        (r"\bthe requested scenario\b", "your request as is"),
        (r"\bas[_ ]requested\b", "your request as is"),
        (r"\bcapped\b", "adjusted to your limits"),
        (r"\b(?:the )?profile[_ ]baseline(?: scenario)?\b", "the reference profile"),
        (r"\bHHI\b", "concentration"),
        (r"\bturnover\b", "portfolio rotation"),
        (r"\bpersonas?\b", "profile"),
        (r"\bproxy\b", "indirect indicator"),
        (r"\bpolicy_rate_ca\b", "policy rate in Canada"),
        (r"\bpolicy_rate_us\b", "policy rate in the United States"),
        (r"\bcpi_yoy_ca\b", "inflation in Canada"),
        (r"\bcpi_yoy_us\b", "inflation in the United States"),
    ),
}
_COUNT_NOUN = {"fr": r"(sc[ée]narios|versions)", "en": r"(scenarios|versions)"}


def plain_terms(text: str, language: str = "fr") -> str:
    """Replace internal terms by their plain-language wording (answer text only)."""
    import re

    for pattern, repl in _PLAIN_TERMS["en" if language == "en" else "fr"]:
        def _sub(m, repl=repl):
            return _cap(repl) if m.group(0)[:1].isupper() else repl
        text = re.sub(pattern, _sub, text, flags=re.IGNORECASE)
    return re.sub(r"[ \t]{2,}", " ", text)


def fix_scenario_count(text: str, n: int, language: str = "fr") -> str:
    """Make "les trois scénarios" agree with the number of scenarios actually present."""
    import re

    words = _COUNT_EN if language == "en" else _COUNT_FR
    if not 2 <= n < len(words):
        return text
    noun = _COUNT_NOUN["en" if language == "en" else "fr"]
    wrong = [w for i, w in enumerate(words) if 2 <= i <= 6 and i != n]

    def _sub(m):
        word = words[n]
        return f"{_cap(word) if m.group(1)[:1].isupper() else word}{m.group(2)}{m.group(3)}"

    return re.sub(rf"\b({'|'.join(wrong)})(\s+){noun}\b", _sub, text, flags=re.IGNORECASE)


def finalise_resume(resume: str, state: GraphState, best_name: str, language: str = "fr") -> str:
    """Deterministic guarantees on a model-written answer: plain terms, the right number of
    scenarios, one sentence per crossed limit of the selected scenario, the pointer sentence."""
    from alphaforge.evidence import EID_RE

    en = language == "en"
    pointer = POINTER_EN if en else POINTER_FR
    text = plain_terms(str(resume or "").strip(), language)
    text = fix_scenario_count(text, len(state.scenarios), language)
    body = text.replace(pointer, "").rstrip()
    cited = set(EID_RE.findall(body))
    extra = []
    for entry in scenario_breaches(state, best_name)[:MAX_BREACH_SENTENCES]:
        ids = [e for e in entry.get("evidence") or [] if e in state.evidence]
        sentence = breach_sentence(state, entry, language)
        if sentence in body or sentence in extra:
            continue
        if ids and set(ids) <= cited:
            continue  # the model already wrote this breach with its figures
        extra.append(sentence)
    parts = [body] if body else []
    if extra:
        parts.append(" ".join(extra))
    parts.append(pointer)
    return "\n\n".join(parts)


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
                            f"{_cap(scenario_label(sc.name, 'en'))}: historical annualized volatility of {_fr(abs(vol) * 100, 1)} %, "
                            f"historical maximum loss of {_fr(abs(mdd) * 100, 1)} %."
                        ),
                        "evidence": ids,
                    }
                )
            else:
                donnees.append(
                    {
                        "claim": (
                            f"{_cap(scenario_label(sc.name, 'fr'))} : volatilité annualisée historique de {_fr(abs(vol) * 100, 1)} %, "
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
    asset_claim = _asset_claim(state, lang)
    if asset_claim:
        donnees.append(asset_claim)
    best_breaches = scenario_breaches(state, best.name)
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
                        f"{_cap(scenario_label(best.name, 'en'))} "
                        + (
                            "crosses at least one limit you declared, but stays the closest to"
                            if best_breaches
                            else "stays within the profile's reference caps and is the closest to"
                        )
                        + f" a '{tol_str}' risk tolerance, with a historical maximum loss of "
                        f"{_fr(abs(bm) * 100, 1)} %."
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
                        f"{_cap(scenario_label(best.name, 'fr'))} "
                        + (
                            "dépasse au moins une limite que vous avez déclarée, mais reste "
                            "l'option la plus cohérente avec"
                            if best_breaches
                            else "reste sous les plafonds de référence du profil et est "
                            "l'option la plus cohérente avec"
                        )
                        + f" une tolérance au risque « {tol_str} », avec une perte maximale "
                        f"historique de {_fr(abs(bm) * 100, 1)} %."
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
                            f"{_cap(scenario_label(best.name, 'en'))}: share of the portfolio in assets held by the ESGV fund "
                            f"(indirect proxy) of {_fr(abs(esg_val) * 100, 1)} %."
                        ),
                        "evidence": [best.metrics["esg_proxy_share"]],
                    }
                )
            else:
                donnees.append(
                    {
                        "claim": (
                            f"{_cap(scenario_label(best.name, 'fr'))} : part du portefeuille dans des titres présents dans le fonds ESGV "
                            f"(indicateur indirect) de {_fr(abs(esg_val) * 100, 1)} %."
                        ),
                        "evidence": [best.metrics["esg_proxy_share"]],
                    }
                )
    resume = template_resume(state, best, lang)

    proxy_eids = [
        eid for eid, ev in state.evidence.items()
        if (isinstance(ev.value, dict) and ev.value.get("metric") == "esg_proxy")
        or (isinstance(ev.value, str) and "Proxy ESG" in ev.value)
    ]

    if lang == "en":
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
    best_name = data.get("scenario_le_plus_coherent", "profile_baseline")
    data["resume"] = finalise_resume(data["resume"], state, best_name, lang)
    for section in ("quelles_donnees", "pourquoi_ce_choix", "limites", "ce_qui_changerait_la_reponse"):
        for item in data.get(section, []):
            if isinstance(item, dict) and "claim" in item:
                item["claim"] = plain_terms(item["claim"], lang)
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
