"""Verifier (PRD 5.10). Owned by Track B.

The LLM audits reasoning; this code audits numbers. Deterministic checks:
cited ids exist, numbers match their cited evidence, no advice, order or forecast wording
(in the explanation, the scenario notes and the red-team objections), all required sections
are present, and no claim that a scenario respects the user's limits while the guardrail
check (`state.guardrails`) reports a breach for it.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

from alphaforge.evidence import EID_RE, numeric
from alphaforge.state import Evidence, GraphState
from alphaforge.tracing import traced

CLAIM_SECTIONS = ("quelles_donnees", "pourquoi_ce_choix", "limites", "ce_qui_changerait_la_reponse")
# Claims in these sections state facts about the analysis, so they must cite evidence.
MUST_CITE = ("quelles_donnees", "pourquoi_ce_choix")
SECTIONS = CLAIM_SECTIONS  # kept for importers of the stub
REQUIRED_TEXT = ("resume", "incertitude", "avertissement", "scenario_le_plus_coherent")
SCENARIO_NAMES = ("as_requested", "capped", "profile_baseline")

SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "quelles_donnees": ("quelles_donnees", "what_data"),
    "pourquoi_ce_choix": ("pourquoi_ce_choix", "why_this_choice"),
    "limites": ("limites", "limits"),
    "ce_qui_changerait_la_reponse": (
        "ce_qui_changerait_la_reponse",
        "what_would_change",
        "what_would_change_the_answer",
    ),
}
TEXT_ALIASES: dict[str, tuple[str, ...]] = {
    "resume": ("resume", "summary"),
    "incertitude": ("incertitude", "uncertainty"),
    "avertissement": ("avertissement", "disclaimer", "warning"),
    "scenario_le_plus_coherent": ("scenario_le_plus_coherent", "most_consistent_scenario"),
}

REL_TOL = 0.01

# Advice and forecast phrasing, French and English (PRD 5.10). Matched on lowercase text.
_WORDING = [
    r"vous devriez (?:acheter|vendre|investir|placer|mettre|choisir|privil[ée]gier)",
    r"\b(?:nous |je )?(?:vous )?recommand(?:ons|ez|e|é|ée|és|ées)\b",
    r"\b(?:nous |je )?(?:vous )?conseill(?:ons|ez|e|é|ée|és|ées)\b",
    r"\b(?:achetez|vendez|investissez)\b",
    r"il faut (?:acheter|vendre|investir)",
    r"vous (?:allez|pourrez) gagner",
    r"(?:rendement|gain|profit)s? (?:garanti|assur[ée]|certain)",
    r"\bgaranti(?:e|s|es)?\b",
    r"\bsans risque\b",
    r"rendement[s]? (?:attendu|esp[ée]r[ée]|pr[ée]vu)s?",
    r"\b(?:rapportera|rapporteront|g[ée]n[ée]rera|g[ée]n[ée]reront|produira|produiront|atteindra|atteindront)\b",
    r"\bva (?:rapporter|monter|augmenter|surperformer)\b",
    r"\bdevrait (?:rapporter|monter|augmenter|surperformer)\b",
    r"\bsurperformera\b",
    r"\byou should\b",
    r"\bwe (?:recommend|advise)\b",
    r"i (?:recommend|advise) (?:that )?you",
    r"\bguaranteed?\b",
    r"\brisk[- ]free\b",
    r"expected returns?",
    r"\bwill (?:return|yield|earn|generate|reach|gain|rise|outperform|grow)\b",
    r"\bpr[ée]visions?\b",
    r"\bforecasts?\b",
    # Buy/sell verbs addressed to the reader (final report, P0-7). Nouns stay allowed
    # ("frais à la vente", "aucune recommandation d'achat").
    r"\b(?:r?acheter|(?:re)?vendre|rachetez|revendez)\b",
    r"\bbuy\b(?!-and-hold| and hold)",
    r"\bsell\b(?!-offs?\b)",
    # Hold recommendation (PRD 5.10, Issue #168).
    r"(?<!buy-and-)(?<!buy and )\bhold\b",
    # Internal identifiers that must not leak into user text (Issues #168, #171).
    r"\bas_requested\b",
    r"\bcapped\b",
    r"\bprofile_baseline\b",
    r"\bpersonas?\b",
    r"\b(?:policy_rate_ca|policy_rate_us|cpi_yoy_ca|cpi_yoy_us)\b",
    # Forward-looking phrases.
    r"\bpotentiel de (?:croissance|hausse|gain|rendement)s?\b",
    r"\b(?:fort|haut|grand|bon|meilleur|important|excellent)s? potentiels?\b",
    r"\bpermettr(?:a|ont)\b",
    r"\b(?:growth|upside|return) potential\b",
    r"\b(?:strong|high|great|significant) potential\b",
    r"\bwill (?:deliver|allow|enable|provide|benefit|increase|appreciate|pay)\b",
    # Tips on how to trade.
    r"\bnorbert\b",
]
_WORDING_RE = [re.compile(p) for p in _WORDING]
# Order labels in capitals, matched on the text as written ("VENTE BTC-USD -100 000 $").
_ORDER_LABEL_RE = re.compile(r"\b(?:ACHATS?|VENTES?|BUY|SELL|HOLD)\b")
_NEGATION_RE = re.compile(
    r"\b(?:pas|aucun|aucune|ne|jamais|non|sans|n'|no|not|never|cannot|without)\b[^.;:]{0,30}$"
)

# Allowed phrasing for historical labels and disclaimers (PRD 5.10, Issue #122).
ALLOW_LIST_WORDING = [
    re.compile(r"historique[s]?,?\s+(?:pas|sans|non)\s+(?:une?\s+)?pr[ée]vision", re.IGNORECASE),
    re.compile(r"(?:pas|sans|aucune?|ne\s+constitue\s+pas)\s+(?:une?\s+)?pr[ée]vision", re.IGNORECASE),
    re.compile(r"historical,?\s+(?:not|no)\s+(?:a\s+)?forecast", re.IGNORECASE),
]

_ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_NUM_RE = re.compile(
    r"(?P<num>[-−–]?\d+(?:[ \u00a0\u202f]\d{3})*(?:[.,]\d+)?)"
    r"(?P<pct>\s*(?:%|pour cent|percent|points? de pourcentage|points?\b|pts\b|pp\b))?",
    re.IGNORECASE,
)

# Scenario names as they appear in claims, mapped to their internal name (#114).
# The plain-language names ("la version ajustée à vos limites", "votre demande telle quelle",
# "le profil de référence", "votre portefeuille actuel") come first; the older names stay
# accepted.
_SCENARIO_ALIASES = {
    "as_requested": (
        "as_requested", "telle quelle", "tel quel", "request as is", "as requested",
        "demandé", "demandée", "requested",
    ),
    "capped": (
        "capped", "ajustée à vos limites", "version ajustée", "scénario ajusté",
        "adjusted to your limits", "adjusted version", "plafonné", "plafonnée", "plafonnement",
    ),
    "profile_baseline": ("profile_baseline", "référence", "reference profile", "baseline"),
    "current": (
        "current", "portefeuille actuel", "actuel", "actuelle", "existant", "détenu", "actuels",
    ),
}

# Phrases that claim a scenario stays within the limits the user declared (final report,
# fix 3). "ajustée à vos limites" is a scenario name, not such a claim.
_LIMIT_CLAIM_RE = [
    re.compile(p)
    for p in (
        r"selon (?:vos|les|tes) garde-fous",
        r"respect\w* (?:bien |toutes |chacune de |l'ensemble de )?(?:vos|les|tes|ses) "
        r"(?:limites|garde-fous|plafonds|contraintes)",
        r"(?:dans|sous|à l'intérieur de|en deçà de) (?:toutes )?(?:vos|tes) (?:limites|garde-fous)",
        r"conformes? (?:à|a) (?:toutes )?(?:vos|tes) (?:limites|garde-fous)",
        r"aucune (?:de vos )?limites? (?:déclarée )?(?:n'est|n'a été) (?:dépassée|franchie)",
        r"(?:according to|within|inside|under) (?:all )?(?:of )?your (?:declared |stated )?"
        r"(?:limits|guardrails)",
        r"(?:respects?|meets?|satisf(?:y|ies)|honou?rs?|complies with|stays? within) "
        r"(?:all )?(?:of )?(?:your|the) (?:declared |stated )?(?:limits|guardrails)",
        r"no (?:declared |stated )?limit is (?:crossed|breached|exceeded)",
    )
]
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


# --------------------------------------------------------------------------- helpers
def _get_items(explanation: dict, section: str) -> list[dict] | None:
    aliases = SECTION_ALIASES.get(section, (section,))
    for a in aliases:
        if a in explanation:
            return explanation[a]
    return None


def _get_field(explanation: dict, key: str) -> str | None:
    aliases = TEXT_ALIASES.get(key, (key,))
    for a in aliases:
        if a in explanation:
            return explanation[a]
    return None


def _items(explanation: dict):
    """Yield (section, claim, evidence ids) for every claim item."""
    for section in CLAIM_SECTIONS:
        for item in _get_items(explanation, section) or []:
            if isinstance(item, dict):
                yield section, str(item.get("claim", "")), list(item.get("evidence") or [])


def _number_items(explanation: dict):
    """Claim items plus the free-text summary and uncertainty, whose ids are cited inline (#114)."""
    yield from _items(explanation)
    for key in ("resume", "incertitude"):
        text = _get_field(explanation, key)
        if isinstance(text, str):
            yield key, text, EID_RE.findall(text)


def _named_scenarios(text: str) -> set[str]:
    lowered = text.lower()
    return {name for name, aliases in _SCENARIO_ALIASES.items() if any(a in lowered for a in aliases)}


def _all_text(explanation: dict) -> list[tuple[str, str]]:
    """(where, text) for all free text that the user will read, disclaimer excluded."""
    out = []
    for key in ("resume", "incertitude"):
        val = _get_field(explanation, key)
        if isinstance(val, str):
            out.append((key, val))
    for section, claim, _ in _items(explanation):
        out.append((section, claim))
    return out


def extract_numbers(text: str) -> list[tuple[float, bool, int]]:
    """Numbers worth checking in `text`: (value, is_percent, decimals).

    Only percentages and decimal numbers are checked. Bare integers (years, counts, amounts
    like 100 000) are not claims about evidence. Evidence ids and ISO dates are ignored.
    """
    cleaned = EID_RE.sub(" ", _ISO_DATE_RE.sub(" ", text))
    found = []
    for m in _NUM_RE.finditer(cleaned):
        raw = re.sub(r"[ \u00a0\u202f]", "", m.group("num"))
        raw = raw.replace("−", "-").replace("–", "-").replace(",", ".")
        is_pct = bool(m.group("pct"))
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        if not is_pct and decimals == 0:
            continue
        try:
            found.append((abs(float(raw)), is_pct, decimals))
        except ValueError:
            continue
    return found


def _matches(claimed: float, is_pct: bool, decimals: int, actual: float) -> bool:
    """Claimed number vs an evidence value, allowing ratio/percent conversion and rounding."""
    actual = abs(actual)
    candidates = [actual * 100, actual] if is_pct else [actual, actual * 100]
    candidates.append(actual / 100)
    half_step = 0.5 * 10 ** (-decimals)
    for cand in candidates:
        if abs(claimed - cand) <= max(REL_TOL * abs(cand), half_step + 1e-9):
            return True
    return False


# --------------------------------------------------------------------------- checks
def check_eids(explanation: dict, evidence: Mapping[str, Evidence]) -> list[str]:
    """Every cited id exists; fact claims cite at least one id."""
    errors = []
    for section, claim, ids in _items(explanation):
        for eid in ids:
            if eid not in evidence:
                errors.append(f"{section}: preuve inconnue {eid}")
        for eid in EID_RE.findall(claim):
            if eid not in evidence:
                errors.append(f"{section}: preuve inconnue {eid} (citée dans le texte)")
        if section in MUST_CITE and not ids:
            errors.append(f"{section}: affirmation sans preuve « {claim[:60]} »")
    return errors


def check_numbers(
    explanation: dict,
    evidence: Mapping[str, Evidence],
    context: list[float] | None = None,
    scenario_weights: Mapping[str, list[float]] | None = None,
) -> list[str]:
    """Every number the user reads appears in the evidence cited next to it (±1 %).

    Checked: percentages, decimals and integers with a unit (%, points), in the four claim
    sections and in `resume` / `incertitude` (ids cited inline there). A difference between
    two cited values is accepted ("un écart de 17 points").
    `context` holds the numbers of the user's own request. `scenario_weights` maps a scenario
    name to its weights; a claim may restate the weights of the scenarios it names, only.
    """
    errors = []
    ctx = list(context or [])
    weights = scenario_weights or {}
    for section, claim, ids in _number_items(explanation):
        values = [numeric(evidence[e]) for e in ids if e in evidence]
        values = [v for v in values if v is not None]
        diffs = [abs(a - b) for i, a in enumerate(values) for b in values[i + 1 :]]
        named = [w for name in _named_scenarios(claim) for w in weights.get(name, [])]
        allowed = values + diffs + ctx + named
        for claimed, is_pct, decimals in extract_numbers(claim):
            if any(_matches(claimed, is_pct, decimals, v) for v in allowed):
                continue
            shown = f"{claimed:g} %" if is_pct else f"{claimed:g}"
            if values:
                errors.append(f"{section}: le nombre {shown} ne correspond pas aux preuves citées")
            else:
                errors.append(f"{section}: le nombre {shown} n'a aucune preuve citée")
    return errors


def check_wording(explanation: dict) -> list[str]:
    """No advice or forecast phrasing. Negated phrases and allow-listed labels are allowed."""
    errors = []
    for where, text in _all_text(explanation):
        lowered = text.lower()
        for rx in _WORDING_RE:
            for m in rx.finditer(lowered):
                if _NEGATION_RE.search(lowered[max(0, m.start() - 40) : m.start()]):
                    continue
                context = lowered[max(0, m.start() - 35) : min(len(lowered), m.end() + 35)]
                if any(al.search(context) for al in ALLOW_LIST_WORDING):
                    continue
                errors.append(f"{where}: formulation interdite « {m.group(0)} »")
        for m in _ORDER_LABEL_RE.finditer(text):
            errors.append(f"{where}: formulation interdite « {m.group(0)} »")
    return errors


def check_text_wording(texts: list[tuple[str, str]]) -> list[str]:
    """`check_wording` on free texts given as (where, text), e.g. scenario notes."""
    errors = []
    for where, text in texts:
        for err in check_wording({"resume": text}):
            errors.append(err.replace("resume:", f"{where}:", 1))
    return errors


def _breaches(guardrails: list[dict] | None) -> dict[str, list[dict]]:
    """Breached guardrail entries by scenario name (entries without a scenario are skipped)."""
    out: dict[str, list[dict]] = {}
    for g in guardrails or []:
        if isinstance(g, dict) and g.get("status") == "breach" and g.get("scenario"):
            out.setdefault(str(g["scenario"]), []).append(g)
    return out


def _claimed_scenario(sentence: str, pos: int, default: str | None) -> str | None:
    """The scenario a limit claim at `pos` talks about: the nearest scenario named in the
    sentence (before the claim first), else the scenario selected as most coherent."""
    hits = []
    for name, aliases in _SCENARIO_ALIASES.items():
        for alias in aliases:
            for m in re.finditer(re.escape(alias), sentence):
                hits.append((m.start(), name))
    before = [h for h in hits if h[0] <= pos]
    if before:
        return max(before)[1]
    if hits:
        return min(hits)[1]
    return default


def check_limit_claims(explanation: dict, guardrails: list[dict] | None) -> list[str]:
    """No text may say a scenario respects the user's limits when a guardrail is breached."""
    breaches = _breaches(guardrails)
    if not breaches:
        return []
    best = _get_field(explanation, "scenario_le_plus_coherent")
    errors = []
    for where, text in _all_text(explanation):
        for sentence in _SENTENCE_SPLIT_RE.split(text.lower()):
            for rx in _LIMIT_CLAIM_RE:
                for m in rx.finditer(sentence):
                    if _NEGATION_RE.search(sentence[max(0, m.start() - 40) : m.start()]):
                        continue
                    name = _claimed_scenario(sentence, m.start(), best)
                    if name not in breaches:
                        continue
                    b = breaches[name][0]
                    label = b.get("label_fr") or b.get("limit") or "limite déclarée"
                    errors.append(
                        f"{where}: « {m.group(0)} » affirme que le scénario {name} respecte vos "
                        f"limites alors que la vérification des limites signale un dépassement "
                        f"({label}). Décris le dépassement au lieu de cette formule."
                    )
    return list(dict.fromkeys(errors))


def check_sections(explanation: dict) -> list[str]:
    """The four questions, the uncertainty and the disclaimer are present and non-empty."""
    errors = []
    for section in CLAIM_SECTIONS:
        items = _get_items(explanation, section)
        if not isinstance(items, list) or not items:
            errors.append(f"{section}: section manquante ou vide")
            continue
        for item in items:
            if not isinstance(item, dict) or not str(item.get("claim", "")).strip():
                errors.append(f"{section}: affirmation vide")
    for key in REQUIRED_TEXT:
        val = _get_field(explanation, key)
        if not isinstance(val, str) or not val.strip():
            errors.append(f"{key}: champ manquant ou vide")
    if _get_field(explanation, "scenario_le_plus_coherent") not in SCENARIO_NAMES:
        errors.append("scenario_le_plus_coherent: nom de scénario invalide")
    if "simulation" not in str(_get_field(explanation, "avertissement") or "").lower():
        errors.append("avertissement: mention de simulation absente")
    return errors


def _context_numbers(state: GraphState) -> list[float]:
    """Numbers from the user's own request (horizon, budget, requested weight)."""
    out: list[float] = []
    p = state.profile
    if p:
        out += [float(p.horizon_years)]
        if p.budget_cad:
            out.append(float(p.budget_cad))
        if p.requested_idea:
            out.append(float(p.requested_idea["weight"]))
        if p.current_holdings:
            out += [float(v) for v in p.current_holdings.values()]
        if p.requested_allocation:
            out += [float(v) for v in p.requested_allocation.values()]
        # Limits the user declared in the questionnaire are the user's own numbers.
        for limit in (p.max_loss_12m, p.crypto_target_min, p.sector_cap):
            if isinstance(limit, (int, float)):
                out.append(float(limit))
    for g in state.guardrails or []:
        declared = g.get("declared") if isinstance(g, dict) else None
        if isinstance(declared, (int, float)) and not isinstance(declared, bool):
            out.append(float(declared))
    return out


def _scenario_weights(state: GraphState) -> dict[str, list[float]]:
    return {sc.name: [float(w) for w in sc.weights.values()] for sc in state.scenarios}


def verify(state: GraphState) -> list[str]:
    explanation = state.explanation
    if not explanation:
        return ["explication absente"]
    errors = check_sections(explanation)
    errors += check_eids(explanation, state.evidence)
    errors += check_numbers(
        explanation, state.evidence, _context_numbers(state), _scenario_weights(state)
    )
    errors += check_wording(explanation)
    errors += check_limit_claims(explanation, state.guardrails)
    # The notes and objections are shown next to the answer: same wording rules.
    side_texts = [
        (f"notes du scénario {sc.name}", note) for sc in state.scenarios for note in sc.notes
    ]
    side_texts += [
        ("objection", str(o.get("objection", ""))) for o in state.objections if isinstance(o, dict)
    ]
    errors += check_text_wording(side_texts)
    return errors


@traced("verifier")
def verifier_node(state: GraphState) -> dict:
    errors = verify(state)
    passed = not errors
    update = {
        "verification": {"passed": passed, "errors": errors},
        "summary": (
            "Vérification réussie : preuves, nombres, formulations et sections conformes."
            if passed
            else f"{len(errors)} erreur(s) détectée(s) dans l'explication."
        ),
    }
    if not passed:
        update["retries"] = {"explain": state.retries.get("explain", 0) + 1}
    return update
