"""Verifier (PRD 5.10). Owned by Track B.

The LLM audits reasoning; this code audits numbers. Four deterministic checks:
cited ids exist, numbers match their cited evidence, no advice or forecast wording,
all required sections are present.
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
]
_WORDING_RE = [re.compile(p) for p in _WORDING]
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
_SCENARIO_ALIASES = {
    "as_requested": ("as_requested", "demandé", "demandée", "requested"),
    "capped": ("capped", "plafonné", "plafonnée", "plafonnement"),
    "profile_baseline": ("profile_baseline", "référence", "baseline"),
    "current": ("current", "actuel", "actuelle", "existant", "détenu", "actuels"),
}


# --------------------------------------------------------------------------- helpers
def _items(explanation: dict):
    """Yield (section, claim, evidence ids) for every claim item."""
    for section in CLAIM_SECTIONS:
        for item in explanation.get(section) or []:
            if isinstance(item, dict):
                yield section, str(item.get("claim", "")), list(item.get("evidence") or [])


def _number_items(explanation: dict):
    """Claim items plus the free-text summary and uncertainty, whose ids are cited inline (#114)."""
    yield from _items(explanation)
    for key in ("resume", "incertitude"):
        text = explanation.get(key)
        if isinstance(text, str):
            yield key, text, EID_RE.findall(text)


def _named_scenarios(text: str) -> set[str]:
    lowered = text.lower()
    return {name for name, aliases in _SCENARIO_ALIASES.items() if any(a in lowered for a in aliases)}


def _all_text(explanation: dict) -> list[tuple[str, str]]:
    """(where, text) for all free text that the user will read, disclaimer excluded."""
    out = []
    for key in ("resume", "incertitude"):
        if isinstance(explanation.get(key), str):
            out.append((key, explanation[key]))
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
    return errors


def check_sections(explanation: dict) -> list[str]:
    """The four questions, the uncertainty and the disclaimer are present and non-empty."""
    errors = []
    for section in CLAIM_SECTIONS:
        items = explanation.get(section)
        if not isinstance(items, list) or not items:
            errors.append(f"{section}: section manquante ou vide")
            continue
        for item in items:
            if not isinstance(item, dict) or not str(item.get("claim", "")).strip():
                errors.append(f"{section}: affirmation vide")
    for key in REQUIRED_TEXT:
        val = explanation.get(key)
        if not isinstance(val, str) or not val.strip():
            errors.append(f"{key}: champ manquant ou vide")
    if explanation.get("scenario_le_plus_coherent") not in SCENARIO_NAMES:
        errors.append("scenario_le_plus_coherent: nom de scénario invalide")
    if "simulation" not in str(explanation.get("avertissement", "")).lower():
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
