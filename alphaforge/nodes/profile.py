"""Agent 1: profile (PRD 5.1). Owned by Track B.

The persona table (alphaforge/personas.py) gives the base profile. The model reads the free
text and fills gaps (requested idea, budget, horizon, extra preferences). Hard constraints
from the persona are never removed by the model. Contradictions are detected in code.

Invariant: the node either returns a `profile` or calls `interrupt()`. If the model fails,
it falls back to the persona table plus a regex read of the request.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any, Literal

from langgraph.types import interrupt
from pydantic import BaseModel, Field

from alphaforge import llm
from alphaforge.data.dynamic_ingestion import (
    COMMON_ALIASES,
    ensure_requested_asset,
    ensure_ticker_in_db,
    is_stop_token,
    resolve_candidate_symbol,
)
from alphaforge.data.market_db import get_merged_universe_dict
from alphaforge.evidence import EvidenceRegistry
from alphaforge.i18n import detect_language
from alphaforge.nodes.scenarios import CAPS
from alphaforge.personas import PERSONAS
from alphaforge.state import (
    GraphState,
    KycCompleteness,
    KycField,
    Profile,
    effective_risk,
    risk_gap,
)
from alphaforge.tracing import traced

KNOWN_CONSTRAINTS = {"no_crypto", "esg_only", "no_controversies"}
# Single-stock reference caps from the scenario builder's table (one source of truth).
SINGLE_STOCK_CAP = {level: caps["single_stock"] for level, caps in CAPS.items()}
TOLERANCE_FR = {
    "high": "élevée",
    "moderate": "modérée",
    "low_moderate": "faible à modérée",
    "low": "faible",
}
TOLERANCE_EN = {
    "high": "high",
    "moderate": "moderate",
    "low_moderate": "low to moderate",
    "low": "low",
}
CRYPTO_MIN_HORIZON_YEARS = 5

ASK_GOAL = "Que souhaitez-vous faire : construire une allocation ou évaluer une idée précise ?"
ASK_GOAL_EN = "What would you like to do: build an allocation or evaluate a specific investment idea?"

# Weights written in words (FR and EN), checked before digits.
_WORD_WEIGHTS = [
    (r"\b(?:la|une)\s+moiti[ée]\b|\bhalf\b", 50.0),
    (r"\btrois\s+quarts?\b|\bthree\s+quarters?\b", 75.0),
    (r"\bun\s+quart\b|\ba\s+quarter\b", 25.0),
    (r"\bun\s+tiers\b|\ba\s+third\b", 33.33),
    (r"\bdeux\s+tiers\b|\btwo\s+thirds\b", 66.67),
    (r"\bun\s+cinqui[èe]me\b", 20.0),
    (r"\bun\s+dixi[èe]me\b", 10.0),
]
# A request is specific enough to build from if it names any of these.
_INTENT_RE = re.compile(
    r"portefeuille|allocation|r[ée]partition|[ée]quilibr|diversifi|responsable|durable|esg|"
    r"horizon|\bans?\b|retraite|crypto|techno|action|obligation|fnb|etf|revenu|"
    r"pr[ée]serv|croissance|risque|\$|%|\d|portfolio|balanced|growth|income|years?|sustainable",
    re.I,
)

STRICT_ESG_RE = re.compile(
    r"\b(?:sans\s+[ée]nergies?(?:\s+fossiles?)?|sans\s+p[ée]trole|fossil[- ]free|no\s+fossil(?:\s+fuels?)?|"
    r"uniquement\s+esg|only\s+esg|strictly\s+esg|strictement\s+esg|"
    r"(?:exclure|exclusion)\s+.*?(?:esg|fossile|p[ée]trole|non[- ]esg)|"
    r"exclude\s+.*?(?:esg|fossil|oil|non[- ]esg))\b",
    re.I,
)

SOFT_ESG_RE = re.compile(
    r"\b(?:meilleur(?:e?s?)?\s+(?:profil\s+)?esg|better\s+esg|"
    r"plus\s+responsable(?:s)?|more\s+responsible|"
    r"plus\s+durable(?:s)?|more\s+sustainable|"
    r"(?:favoriser|privil[ée]gier|tilt|biais|orientation|accent)\s+(?:sur\s+|vers\s+|en\s+|pour\s+)?(?:l'|le\s+|les\s+)?esg|"
    r"(?:favor|favour|prefer)\s+(?:the\s+)?esg|esg\s+tilt|"
    r"(?:pr[ée]f[ée]rence|souhait)\s+(?:pour\s+|en\s+)?(?:l'|le\s+)?esg|esg\s+preference|"
    r"sensible\s+[àa]\s+(?:l'|le\s+)?esg)\b",
    re.I,
)


class Extraction(BaseModel):
    """What the model reads from the free-text request. Every field is optional."""

    request_type: Literal["build", "judge"] = "build"
    ticker: str | None = None
    weight_pct: float | None = Field(default=None, description="share of the portfolio, in percent")
    budget_cad: float | None = None
    horizon_years: int | None = None
    account_type: Literal["tfsa", "rrsp", "fhsa", "non_registered", "mixed"] | None = None
    extra_constraints: list[str] = Field(default_factory=list)
    extra_preferences: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    requested_allocation: dict[str, float] | None = None
    requested_vehicle: str | None = None


SYSTEM = (
    "You read the request of a retail investor for an educational simulation tool. "
    "Keep apart: horizon (when the money is needed), risk tolerance (what the person says they "
    "accept) and risk capacity (what their situation can absorb); age alone sets none of them. "
    "Extract only what the text says. Never invent a number, a ticker or a preference. "
    "Weights in words count: 'un quart' = 25, 'la moitié' = 50. "
    "request_type is 'judge' when the person proposes a specific asset or weight to evaluate, "
    "'build' when they want an allocation. "
    "If the person names a specific asset, stock, ETF, or crypto (e.g. 'TSMC', 'NVDA', 'Dogecoin', 'Amazon', 'Bitcoin', 'Tesla', 'ASML', 'Palantir'), "
    "extract its standard market ticker symbol (e.g. 'TSM' for TSMC, 'AMZN' for Amazon, 'TSLA' for Tesla, 'DOGE-USD' for Dogecoin, 'BTC-USD' for Bitcoin, 'PLTR' for Palantir). "
    "If it is in the starter universe, use that exact ticker; if outside, return its standard Yahoo Finance ticker symbol so it can be dynamically ingested. "
    "If no specific asset is named, ticker must be null. "
    "extra_constraints may only use: no_crypto, esg_only, no_controversies. "
    "Strict wording ('sans énergies fossiles', 'uniquement ESG', 'exclure') maps to extra_constraints: esg_only. "
    "extra_preferences are short snake_case tags (e.g. likes_tech, wants_income, esg_tilt). "
    "Soft ESG wishes ('meilleur ESG', 'plus responsable', 'plus durable', 'better ESG', 'more sustainable') "
    "map to extra_preferences: esg_tilt. "
    "conflicts: up to 2 short French sentences about a contradiction between the request and "
    "the persona hypotheses, or an empty list. No advice, no forecast."
)


REQUEST_CLASS_CODES = frozenset({"crypto", "equity", "bond", "gold"})  # asset-class keys of an allocation


def _universe() -> dict[str, dict]:
    return get_merged_universe_dict()


def _resolve_ticker(raw: str | None) -> str | None:
    """Map a model or regex ticker to a ticker of the curated universe (or of the local DB).

    A ticker outside both is handed to the dynamic ingestion, which only downloads it when
    ``AF_DYNAMIC_INGESTION`` is on; otherwise, or on any failure, the result is None and
    the asset stays "hors univers — non analysé" (#164, #175).
    """
    if not raw:
        return None
    raw_str = raw.strip()
    key = raw_str.upper()
    universe = _universe()
    for t in universe:
        if key in (t.upper(), t.upper().split(".")[0]):
            return t
    if key in ("CRYPTO", "BITCOIN", "BTC"):
        return "BTC-USD"
    if key in ("ETHER", "ETHEREUM", "ETH"):
        return "ETH-USD"
    if key in ("SP500", "S&P 500", "S&P500", "SNP500", "S&P", "SPY"):
        return "SPY"
    if key in ("NASDAQ", "NAS100", "QQQ"):
        return "QQQ"
    if key in ("TSX", "TSX60", "XIU"):
        return "XIU.TO"
    if key.lower() in REQUEST_CLASS_CODES or is_stop_token(key):
        return None
    sym = COMMON_ALIASES.get(raw_str.lower()) or key
    if sym in universe:
        return sym
    return ensure_ticker_in_db(sym)


def _regex_extract(text: str) -> Extraction:
    """Fallback reader used when the model is unavailable or returns invalid JSON."""
    primary_text = text.split("\n\n[Contexte investisseur]")[0]
    lowered = primary_text.lower()
    weight = None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:%|pour\s*cent|percent)", lowered)
    if m:
        weight = float(m.group(1).replace(",", "."))
    else:
        for rx, value in _WORD_WEIGHTS:
            if re.search(rx, lowered):
                weight = value
                break
    ticker = None
    for t, row in _universe().items():
        base = t.split(".")[0].lower()
        name = row["name"].split()[0].lower()
        if re.search(rf"\b{re.escape(base)}\b", lowered) or (
            len(name) > 3 and re.search(rf"\b{re.escape(name)}\b", lowered)
        ):
            ticker = t
            break
    if not ticker:
        if re.search(r"\b(?:ethereum|ether|eth)\b", lowered):
            ticker = "ETH-USD"
        elif re.search(r"\b(?:bitcoin|btc)\b", lowered):
            ticker = "BTC-USD"
        elif re.search(r"\b(?:sp500|s&p\s*500|snp500|s&p)\b", lowered):
            ticker = "SPY"
        elif re.search(r"\b(?:nasdaq|nas100)\b", lowered):
            ticker = "QQQ"
        elif re.search(r"\b(?:tsx\s*60|tsx)\b", lowered):
            ticker = "XIU.TO"
        elif re.search(r"\b(?:nvidia)\b", lowered):
            ticker = "NVDA"
        elif re.search(r"\b(?:tesla)\b", lowered):
            ticker = "TSLA"
        elif re.search(r"\b(?:apple)\b", lowered):
            ticker = "AAPL"
        elif re.search(r"\b(?:microsoft)\b", lowered):
            ticker = "MSFT"
        elif re.search(r"\b(?:google|alphabet)\b", lowered):
            ticker = "GOOGL"
        elif re.search(r"\b(?:amazon)\b", lowered):
            ticker = "AMZN"
        elif re.search(r"\b(?:shopify)\b", lowered):
            ticker = "SHOP.TO"
        else:
            # A security named outside the universe ("l'action PLTR", "dogecoin"): resolved
            # only if it is already local or the dynamic ingestion (off by default) gets it.
            cand = resolve_candidate_symbol(primary_text)
            if cand:
                ticker = _resolve_ticker(cand)
    horizon = None
    m_h = re.search(r"(\d+)\s*(?:ans?|years?|yrs?)\b", lowered)
    if m_h:
        horizon = int(m_h.group(1))
    act = None
    if re.search(r"\b(?:celiapp|fhsa)\b", lowered):
        act = "fhsa"
    elif re.search(r"\b(?:celi|tfsa)\b", lowered):
        act = "tfsa"
    elif re.search(r"\b(?:reer|rrsp|cri|ferr)\b", lowered):
        act = "rrsp"
    elif re.search(r"\b(?:mixte|mixed)\b", lowered):
        act = "mixed"
    elif re.search(r"\b(?:non[- ]enregistr[ée]|taxable|imposable)\b", lowered):
        act = "non_registered"

    req_vehicle = None
    from alphaforge.tax import LISTED_CRYPTO_ETFS
    for v in sorted(LISTED_CRYPTO_ETFS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(v.lower())}\b", lowered):
            req_vehicle = v
            if not ticker:
                ticker = LISTED_CRYPTO_ETFS[v]
            break

    req_alloc = None
    if ticker and weight is not None and 0 < weight <= 100:
        req_alloc = {ticker: round(weight / 100.0, 4)}
    else:
        # A weight needs a "%"/"pour cent" or an "en/de crypto" context: "je détiens 2
        # cryptos" is a count, not a 2 % target (#186, item 10).
        m_crypto = re.search(
            r"(\d+(?:[.,]\d+)?)\s*(?:(?:%|pour\s*cent)\s*(?:en\s+|de\s+|d')?|en\s+|de\s+|d')crypto",
            lowered,
        )
        if m_crypto:
            w_c = float(m_crypto.group(1).replace(",", ".")) / 100.0
            if 0 < w_c <= 1:
                req_alloc = {"crypto": round(w_c, 4)}

    extra_constraints: list[str] = []
    extra_preferences: list[str] = []
    if STRICT_ESG_RE.search(lowered):
        extra_constraints.append("esg_only")
    elif SOFT_ESG_RE.search(lowered):
        extra_preferences.append("esg_tilt")

    return Extraction(
        request_type="judge" if ticker else "build",
        ticker=ticker,
        weight_pct=weight,
        horizon_years=horizon,
        account_type=act,
        extra_constraints=extra_constraints,
        extra_preferences=extra_preferences,
        requested_allocation=req_alloc,
        requested_vehicle=req_vehicle,
    )


def extract_profile(
    state_persona: str,
    text: str,
    *,
    kind: llm.ModelKind = "main",
    llm_client=None,
    language: str = "fr",
) -> tuple[Extraction, bool]:
    """Read the request. Returns (extraction, used_fallback)."""
    if not text.strip():
        return Extraction(), False
    persona = state_persona if isinstance(state_persona, dict) else PERSONAS[state_persona]
    obj = persona.get("objective", "balanced")
    hor = persona.get("horizon_years", 5)
    tol = persona.get("risk_tolerance", "moderate")
    cap = persona.get("risk_capacity", "moderate")
    con = persona.get("constraints", [])
    pref = persona.get("preferences", [])
    lang_label = "English" if language == "en" else "French"
    # Extract ticker & weight only from the primary question, never from the appended investor context
    primary_text = text.split("\n\n[Contexte investisseur]")[0].split("[Contexte investisseur]")[0].strip()
    prompt = (
        f"Persona hypotheses: objective={obj}, horizon={hor} years, tolerance={tol}, capacity={cap}, "
        f"constraints={con}, preferences={pref}.\n"
        f"Starter universe tickers: {', '.join(sorted(_universe()))}.\n"
        f'Request ({lang_label}): """{primary_text}"""'
    )
    conflicts_inst = (
        "conflicts: up to 2 short English sentences about a contradiction between the request and "
        "the persona hypotheses, or an empty list. No advice, no forecast."
        if language == "en"
        else
        "conflicts: up to 2 short French sentences about a contradiction between the request and "
        "the persona hypotheses, or an empty list. No advice, no forecast."
    )
    system = (
        "You read the request of a retail investor for an educational simulation tool. "
        "Keep apart: horizon (when the money is needed), risk tolerance (what the person says they "
        "accept) and risk capacity (what their situation can absorb); age alone sets none of them. "
        "Extract only what the text says. Never invent a number, a ticker or a preference. "
        "Weights in words count: 'un quart' = 25, 'la moitié' = 50, 'one quarter' = 25, 'half' = 50. "
        "request_type is 'judge' when the person proposes a specific asset or weight to evaluate, "
        "'build' when they want an allocation. "
        "If the person names a specific asset, stock, ETF, or crypto (e.g. 'TSMC', 'NVDA', 'Dogecoin', 'Amazon', 'Bitcoin', 'Tesla', 'ASML', 'Palantir'), "
        "extract its standard market ticker symbol (e.g. 'TSM' for TSMC, 'AMZN' for Amazon, 'TSLA' for Tesla, 'DOGE-USD' for Dogecoin, 'BTC-USD' for Bitcoin, 'PLTR' for Palantir). "
        "If it is in the starter universe, use that exact ticker; if outside, return its standard Yahoo Finance ticker symbol so it can be dynamically ingested. "
        "If no specific asset is named, ticker must be null. "
        "requested_allocation holds the weights the request names, as fractions: keys are listed tickers or the "
        "asset-class codes crypto, equity, bond, gold (e.g. 'garder 50 % en crypto' -> {\"crypto\": 0.5}); null if none. "
        "extra_constraints may only use: no_crypto, esg_only, no_controversies. "
        "Strict wording ('sans énergies fossiles', 'uniquement ESG', 'exclure') maps to extra_constraints: esg_only. "
        "extra_preferences are short snake_case tags (e.g. likes_tech, wants_income, esg_tilt). "
        "Soft ESG wishes ('meilleur ESG', 'plus responsable', 'plus durable', 'better ESG', 'more sustainable') "
        "map to extra_preferences: esg_tilt. "
        f"{conflicts_inst}"
    )
    try:
        res = llm.call_json(prompt, Extraction, kind=kind, system=system, llm=llm_client)
        lowered_p = primary_text.lower()
        if STRICT_ESG_RE.search(lowered_p) and "esg_only" not in res.extra_constraints:
            res.extra_constraints.append("esg_only")
            if "esg_tilt" in res.extra_preferences:
                res.extra_preferences.remove("esg_tilt")
        elif not STRICT_ESG_RE.search(lowered_p) and SOFT_ESG_RE.search(lowered_p) and "esg_tilt" not in res.extra_preferences:
            res.extra_preferences.append("esg_tilt")
        # The model does not always fill the allocation the question names ("garder 50 % en
        # crypto", "15 % en Bitcoin via BTCC.B"). The deterministic reading of the same text
        # fills what the model left empty; it never overrides what the model did extract.
        rx = _regex_extract(primary_text)
        if res.ticker is None and rx.ticker:
            res.ticker = rx.ticker
            if res.weight_pct is None:
                res.weight_pct = rx.weight_pct
            res.request_type = "judge"
        if res.requested_allocation is None and res.ticker and res.weight_pct is not None and 0 < res.weight_pct <= 100:
            res.requested_allocation = {res.ticker: round(res.weight_pct / 100.0, 4)}
        if res.requested_allocation is None and rx.requested_allocation:
            res.requested_allocation = rx.requested_allocation
        if res.requested_vehicle is None:
            from alphaforge.tax import LISTED_CRYPTO_ETFS
            for v in sorted(LISTED_CRYPTO_ETFS, key=len, reverse=True):
                if re.search(rf"\b{re.escape(v.lower())}\b", lowered_p):
                    res.requested_vehicle = v
                    break
        return res, False
    except llm.LLMError:
        return _regex_extract(text), True


def detect_conflict(
    *,
    tolerance: str,
    horizon_years: int,
    constraints: list[str],
    idea: dict | None,
    max_loss_pct: float | None = None,
    capacity: str | None = None,
    language: str = "fr",
) -> list[str]:
    """Contradictions between the requested idea and the stated profile (deterministic)."""
    out: list[str] = []
    level = effective_risk(tolerance, capacity) if capacity else tolerance
    is_en = language == "en"
    if capacity and risk_gap(tolerance, capacity) >= 2:
        if is_en:
            out.append(
                f"Stated risk tolerance '{TOLERANCE_EN.get(tolerance, tolerance)}' exceeds "
                f"financial capacity '{TOLERANCE_EN.get(capacity, capacity)}': profile limits "
                "follow capacity, the more conservative of the two."
            )
        else:
            out.append(
                f"La tolérance au risque déclarée « {TOLERANCE_FR.get(tolerance, tolerance)} » dépasse "
                f"nettement la capacité financière « {TOLERANCE_FR.get(capacity, capacity)} » : les "
                "limites du profil suivent la capacité, la plus prudente des deux."
            )
    if max_loss_pct is not None:
        if is_en:
            tol_en = TOLERANCE_EN.get(tolerance, tolerance)
            if (max_loss_pct <= 5.0 and tolerance in ("high", "moderate")) or (
                max_loss_pct <= 15.0 and tolerance == "high"
            ):
                out.append(
                    f"A 12-month loss tolerance of {max_loss_pct:.0f}% is in contradiction "
                    f"with stated risk tolerance '{tol_en}'."
                )
        else:
            tol_fr = TOLERANCE_FR.get(tolerance, tolerance)
            if (max_loss_pct <= 5.0 and tolerance in ("high", "moderate")) or (
                max_loss_pct <= 15.0 and tolerance == "high"
            ):
                out.append(
                    f"Une tolérance de perte sur 12 mois de {max_loss_pct:.0f} % est en contradiction "
                    f"avec une tolérance au risque déclarée « {tol_fr} »."
                )
    if not idea:
        return out
    ticker, weight = idea["ticker"], idea["weight"]
    cap = SINGLE_STOCK_CAP[level]
    asset = _universe().get(ticker, {})
    if asset.get("asset_class") == "equity" and weight > cap:
        if is_en:
            lvl_str = TOLERANCE_EN.get(level, level)
            basis = "effective risk level" if level != tolerance else "risk tolerance"
            out.append(
                f"{weight:.0%} in {ticker} exceeds the reference ceiling of {cap:.0%} per stock "
                f"for a '{lvl_str}' {basis} and a {horizon_years}-year horizon."
            )
        else:
            lvl_str = TOLERANCE_FR.get(level, level)
            basis = "un niveau de risque retenu" if level != tolerance else "une tolérance au risque"
            out.append(
                f"{weight:.0%} dans {ticker} dépasse le plafond de référence de {cap:.0%} par action "
                f"pour {basis} « {lvl_str} » et un horizon de {horizon_years} ans."
            )
    if asset.get("asset_class") == "crypto":
        if "no_crypto" in constraints:
            if is_en:
                out.append(f"{ticker} is a crypto asset, excluded by the profile constraints.")
            else:
                out.append(f"{ticker} est un cryptoactif, exclu par les contraintes du profil.")
        elif horizon_years < CRYPTO_MIN_HORIZON_YEARS:
            if is_en:
                out.append(
                    f"{ticker} is very volatile for an investment horizon of {horizon_years} years "
                    f"(less than {CRYPTO_MIN_HORIZON_YEARS} years)."
                )
            else:
                out.append(
                    f"{ticker} est très volatil pour un horizon de {horizon_years} ans "
                    f"(moins de {CRYPTO_MIN_HORIZON_YEARS} ans)."
                )
    return out


REQUIRED_KYC_SPECS = [
    ("has_emergency_fund", "Fonds d'urgence (3 à 6 mois de dépenses)"),
    ("has_high_interest_debt", "Absence de dettes à taux d'intérêt élevé"),
    ("net_worth_share", "Part du patrimoine représentée"),
    ("investment_knowledge", "Connaissances et expérience en investissement"),
    ("horizon_years", "Horizon d'investissement"),
    ("risk_tolerance", "Tolérance au risque"),
    ("risk_capacity", "Capacité financière"),
]

OPTIONAL_KYC_SPECS = [
    ("income_stability", "Stabilité des revenus"),
    ("liquidity_need_12m", "Besoins de liquidités à 12 mois"),
    ("current_holdings", "Autres avoirs (actions employeur, pension)"),
    ("withdrawal_plan", "Plan de retraits"),
    ("budget_cad", "Budget d'investissement"),
]


def extract_kyc_from_text(text: str) -> dict[str, Any]:
    """Deterministic extraction of KYC indicators from text."""
    lowered = text.lower()
    res: dict[str, Any] = {}

    # Emergency fund:
    if re.search(
        r"\b(?:sans|pas de|aucun|aucune)\s+(?:fonds|r[ée]serve|[ée]pargne)\s+d'urgence\b|\bpas de fonds\b|\baucun fonds\b|\bpas d'[ée]pargne de pr[ée]caution\b",
        lowered,
    ):
        res["has_emergency_fund"] = False
    elif re.search(
        r"\b(?:fonds d'urgence|r[ée]serve d'urgence|[ée]pargne de pr[ée]caution)\b|\b(?:j'ai un fonds|r[ée]serve de liquidit[ée]s?|urgence assur[ée]e)\b",
        lowered,
    ):
        res["has_emergency_fund"] = True

    # High interest debt:
    if re.search(
        r"\b(?:carte[s]? de cr[ée]dit|pr[êe]t[s]? personnel[s]?|dette[s]? [àa] taux [ée]lev[ée]|dettes importantes)\b",
        lowered,
    ):
        res["has_high_interest_debt"] = True
        res["debt_level"] = "high_interest"
    elif re.search(
        r"\b(?:sans|pas de|aucune)\s+dette[s]?\b|\baucune dette\b|\bpas de dette\b|\bhypoth[èe]que seulement\b|\bpr[êe]t hypoth[ée]caire uniquement\b",
        lowered,
    ):
        res["has_high_interest_debt"] = False
        res["debt_level"] = "none"

    # Net worth share:
    m_pct = re.search(
        r"(\d+(?:[.,]\d+)?)\s*%\s*(?:de mon patrimoine|de ma valeur nette|de mes avoirs|du total)",
        lowered,
    )
    if m_pct:
        res["net_worth_share"] = float(m_pct.group(1).replace(",", ".")) / 100.0
    elif re.search(r"\b(?:la moiti[ée]|half)\b.*(?:patrimoine|valeur nette|avoirs)", lowered):
        res["net_worth_share"] = 0.50
    elif re.search(r"\b(?:un quart|quarter)\b.*(?:patrimoine|valeur nette|avoirs)", lowered):
        res["net_worth_share"] = 0.25
    elif re.search(r"\b(?:majorit[ée]|presque tout|totalit[ée])\b.*(?:patrimoine|avoirs)", lowered):
        res["net_worth_share"] = 0.80

    # Knowledge:
    if re.search(
        r"\bd[ée]butant\b|\bnovice\b|\bbeginner\b|\baucune exp[ée]rience\b|\bpeu d'exp[ée]rience\b",
        lowered,
    ):
        res["investment_knowledge"] = "beginner"
    elif re.search(r"\bavanc[ée]\b|\bexpert\b|\badvanced\b|\bgrande exp[ée]rience\b", lowered):
        res["investment_knowledge"] = "advanced"
    elif re.search(r"\binterm[ée]diaire\b|\bintermediate\b|\bexp[ée]rience moyenne\b", lowered):
        res["investment_knowledge"] = "intermediate"

    # Withdrawal plan:
    if re.search(r"\blump[- ]sum\b|\bd[ée]caissement unique\b|\bretrait unique\b|\ben une fois\b", lowered):
        res["withdrawal_plan"] = "lump_sum"
    elif re.search(r"\brevenu[s]? r[ée]gulier[s]?\b|\bretraits r[ée]guliers\b|\bpension r[ée]guli[èe]re\b", lowered):
        res["withdrawal_plan"] = "regular_income"
    elif re.search(r"\baucun retrait\b|\br[ée]investissement total\b|\br[ée]investir\b", lowered):
        res["withdrawal_plan"] = "none"

    return res


def apply_clarification_answer(key: str, answer: str, kyc_data: dict[str, Any]) -> None:
    ans_lower = answer.strip().lower()
    if ans_lower in ("je ne sais pas", "pas sûr", "aucune idée", "skip", "passer"):
        return
    if key == "emergency_fund":
        if re.search(r"\bnon\b|\baucun\b|\bpas de\b|\bpas d'urgence\b", ans_lower):
            kyc_data["has_emergency_fund"] = False
        elif re.search(r"\boui\b|\bj'ai\b|\bconstitu[ée]\b|\bpr[ée]sent\b|\bcouvert\b", ans_lower):
            kyc_data["has_emergency_fund"] = True
    elif key == "high_interest_debt":
        if re.search(r"\boui\b|\bcarte\b|\bcr[ée]dit\b|\bpersonnel\b", ans_lower):
            kyc_data["has_high_interest_debt"] = True
            kyc_data["debt_level"] = "high_interest"
        elif re.search(r"\bnon\b|\baucune\b|\bpas de\b|\bhypoth[èe]que\b", ans_lower):
            kyc_data["has_high_interest_debt"] = False
            kyc_data["debt_level"] = "none"
    elif key == "net_worth_share":
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", ans_lower)
        if m:
            kyc_data["net_worth_share"] = float(m.group(1).replace(",", ".")) / 100.0
        elif "moitié" in ans_lower or "50" in ans_lower:
            kyc_data["net_worth_share"] = 0.50
        elif "quart" in ans_lower or "25" in ans_lower:
            kyc_data["net_worth_share"] = 0.25
        elif "majorité" in ans_lower or "tout" in ans_lower:
            kyc_data["net_worth_share"] = 0.75
        else:
            kyc_data["net_worth_share"] = 0.20
    elif key == "investment_knowledge":
        if "débutant" in ans_lower or "novice" in ans_lower:
            kyc_data["investment_knowledge"] = "beginner"
        elif "avancé" in ans_lower or "expert" in ans_lower:
            kyc_data["investment_knowledge"] = "advanced"
        elif "intermédiaire" in ans_lower:
            kyc_data["investment_knowledge"] = "intermediate"
    elif key == "withdrawal_plan":
        if "unique" in ans_lower or "lump" in ans_lower:
            kyc_data["withdrawal_plan"] = "lump_sum"
        elif "régulier" in ans_lower or "revenu" in ans_lower:
            kyc_data["withdrawal_plan"] = "regular_income"
        elif "aucun" in ans_lower or "réinvest" in ans_lower:
            kyc_data["withdrawal_plan"] = "none"


def get_next_clarification_question(
    persona_id: str,
    persona_data: dict | None,
    text: str,
    ext: Extraction,
    asked: set[str],
    current_kyc: dict[str, Any],
    language: str = "fr",
) -> tuple[str | None, str | None]:
    """Next clarification question ranked by impact on caps. Deterministic (no LLM call)."""
    ask_goal = ASK_GOAL_EN if language == "en" else ASK_GOAL
    # Priority 1: Goal or idea weight
    if "goal" not in asked and not text.strip():
        return "goal", ask_goal
    if "goal" not in asked and ext.ticker is None and not _INTENT_RE.search(text):
        return "goal", ask_goal
    if "weight" not in asked and ext.ticker and ext.weight_pct is None:
        if language == "en":
            return "weight", f"What share of your portfolio would you like to allocate to {ext.ticker} (in %)?"
        return "weight", f"Quelle part de votre portefeuille souhaitez-vous consacrer à {ext.ticker} (en %) ?"

    # KYC fields check (ranking by impact on caps):
    base = persona_data or (PERSONAS[persona_id] if persona_id in PERSONAS else {})
    from_text = extract_kyc_from_text(text)
    combined = {**base, **from_text, **current_kyc}

    # Priority 2: Emergency fund
    if "emergency_fund" not in asked and combined.get("has_emergency_fund") is None:
        return (
            "emergency_fund",
            (
                "Do you have a liquid emergency fund (3 to 6 months of living expenses) to cover your needs for the next 12 months?"
                if language == "en"
                else "Disposez-vous d'un fonds d'urgence liquide (3 à 6 mois de dépenses courantes) pour couvrir vos besoins des 12 prochains mois ?"
            ),
        )

    # Priority 3: High-interest debt
    if "high_interest_debt" not in asked and combined.get("has_high_interest_debt") is None:
        return (
            "high_interest_debt",
            (
                "Do you have debts, especially high-interest debt (credit cards, personal loans) to pay off as a priority?"
                if language == "en"
                else "Avez-vous des dettes, en particulier des dettes à taux d'intérêt élevé (cartes de crédit, prêts personnels) à rembourser en priorité ?"
            ),
        )

    # Priority 4: Net worth share
    if "net_worth_share" not in asked and combined.get("net_worth_share") is None:
        return (
            "net_worth_share",
            (
                "Approximately what portion of your overall net worth does this investment represent (e.g. less than 25%, half, majority)?"
                if language == "en"
                else "Quelle part approximative de votre patrimoine global cet investissement représente-t-il (ex. moins de 25 %, la moitié, la majorité) ?"
            ),
        )

    # Priority 5: Investment knowledge
    if "investment_knowledge" not in asked and combined.get("investment_knowledge") is None:
        return (
            "investment_knowledge",
            (
                "What is your level of investment experience and knowledge (beginner, intermediate, advanced)?"
                if language == "en"
                else "Quel est votre niveau d'expérience et de connaissance en matière d'investissements (débutant, intermédiaire, avancé) ?"
            ),
        )

    return None, None


def build_kyc_completeness_and_assumptions(
    persona_id: str,
    persona_data: dict | None,
    text: str,
    kyc_answers: dict[str, Any],
    as_of_date: dt.date,
    profile_fields: dict[str, Any],
) -> tuple[dict[str, Any], KycCompleteness, dict[str, Any]]:
    """Build KycCompleteness model and register assumptions for missing fields.

    Returns (resolved_kyc_dict, KycCompleteness, evidence_items).
    """
    reg = EvidenceRegistry(prefix="EK")
    text_kyc = extract_kyc_from_text(text)

    resolved: dict[str, Any] = {}
    fields: dict[str, KycField] = {}
    missing_required: list[str] = []

    ASSUMED_DEFAULTS = {
        # Unanswered safety-relevant fields stay unknown (None) rather than taking the
        # favourable value: a suitability check must not assume what it could not confirm.
        "has_emergency_fund": (
            None,
            "fonds d'urgence non confirmé (réponse non obtenue)",
            "Fonds d'urgence non confirmé : à vérifier avant toute décision",
        ),
        "has_high_interest_debt": (
            None,
            "dettes à taux d'intérêt élevé non confirmées (réponse non obtenue)",
            "Dettes à taux d'intérêt élevé non confirmées : à vérifier avant toute décision",
        ),
        "net_worth_share": (
            0.20,
            "investissement estimé à 20 % du patrimoine net global",
            "Part du patrimoine net estimée à 20 %",
        ),
        "investment_knowledge": (
            "intermediate",
            "niveau de connaissances financières supposé intermédiaire",
            "Niveau de connaissance financière supposé intermédiaire",
        ),
        "withdrawal_plan": (
            "none",
            "aucun retrait anticipé prévu (réinvestissement)",
            "Aucun plan de retrait anticipé supposé",
        ),
        "income_stability": (
            "unknown",
            "stabilité des revenus non confirmée (réponse non obtenue)",
            "Stabilité des revenus non confirmée : à vérifier",
        ),
        "liquidity_need_12m": (
            "none",
            "aucun besoin de liquidité exceptionnel à 12 mois",
            "Besoins de liquidités à 12 mois couverts",
        ),
        "current_holdings": (
            [],
            "aucun titre employeur ou pension influençant les plafonds",
            "Aucune concentration d'actifs préexistante déclarée",
        ),
    }

    # Evaluate required fields
    for field_name, label in REQUIRED_KYC_SPECS:
        if field_name in profile_fields and profile_fields[field_name] is not None:
            source = "questionnaire" if persona_data else ("persona" if persona_id in PERSONAS else "text")
            val = profile_fields[field_name]
            fields[field_name] = KycField(
                name=field_name, label=label, required=True, collected=True, source=source, value=val
            )
            resolved[field_name] = val
            continue

        if field_name in kyc_answers and kyc_answers[field_name] is not None:
            val = kyc_answers[field_name]
            fields[field_name] = KycField(
                name=field_name, label=label, required=True, collected=True, source="text", value=val
            )
            resolved[field_name] = val
        elif field_name in text_kyc and text_kyc[field_name] is not None:
            val = text_kyc[field_name]
            fields[field_name] = KycField(
                name=field_name, label=label, required=True, collected=True, source="text", value=val
            )
            resolved[field_name] = val
        elif persona_data and field_name in persona_data and persona_data[field_name] is not None:
            val = persona_data[field_name]
            fields[field_name] = KycField(
                name=field_name, label=label, required=True, collected=True, source="questionnaire", value=val
            )
            resolved[field_name] = val
        elif persona_id in PERSONAS and field_name in PERSONAS[persona_id] and PERSONAS[persona_id][field_name] is not None:
            val = PERSONAS[persona_id][field_name]
            fields[field_name] = KycField(
                name=field_name, label=label, required=True, collected=True, source="persona", value=val
            )
            resolved[field_name] = val
        else:
            missing_required.append(field_name)
            default_val, method_desc, note_desc = ASSUMED_DEFAULTS.get(
                field_name, ("assumed", "hypothèse de convenance", "Valeur par défaut")
            )
            eid = reg.add(
                value="non confirmé" if default_val is None else default_val,
                source="assumption:kyc",
                date=as_of_date,
                method=f"Hypothèse KYC : {method_desc}",
                confidence="assumption",
            )
            fields[field_name] = KycField(
                name=field_name,
                label=label,
                required=True,
                collected=False,
                source="assumption",
                value=default_val,
                assumption_note=f"{note_desc} ({eid}).",
                evidence_id=eid,
            )
            resolved[field_name] = default_val

    # Evaluate optional fields
    for field_name, label in OPTIONAL_KYC_SPECS:
        if field_name in profile_fields and profile_fields[field_name] is not None:
            source = "questionnaire" if persona_data else ("persona" if persona_id in PERSONAS else "text")
            val = profile_fields[field_name]
            fields[field_name] = KycField(
                name=field_name, label=label, required=False, collected=True, source=source, value=val
            )
            resolved[field_name] = val
            continue
        if field_name in kyc_answers and kyc_answers[field_name] is not None:
            val = kyc_answers[field_name]
            fields[field_name] = KycField(
                name=field_name, label=label, required=False, collected=True, source="text", value=val
            )
            resolved[field_name] = val
        elif field_name in text_kyc and text_kyc[field_name] is not None:
            val = text_kyc[field_name]
            fields[field_name] = KycField(
                name=field_name, label=label, required=False, collected=True, source="text", value=val
            )
            resolved[field_name] = val
        elif persona_data and field_name in persona_data and persona_data[field_name] is not None:
            val = persona_data[field_name]
            fields[field_name] = KycField(
                name=field_name, label=label, required=False, collected=True, source="questionnaire", value=val
            )
            resolved[field_name] = val
        elif persona_id in PERSONAS and field_name in PERSONAS[persona_id] and PERSONAS[persona_id][field_name] is not None:
            val = PERSONAS[persona_id][field_name]
            fields[field_name] = KycField(
                name=field_name, label=label, required=False, collected=True, source="persona", value=val
            )
            resolved[field_name] = val
        else:
            fields[field_name] = KycField(
                name=field_name,
                label=label,
                required=False,
                collected=False,
                source="assumption",
                value=None,
            )
            resolved[field_name] = None

    req_names = [f[0] for f in REQUIRED_KYC_SPECS]
    opt_names = [f[0] for f in OPTIONAL_KYC_SPECS]
    collected_count = sum(1 for n in req_names if fields[n].collected)
    score = round(collected_count / len(req_names), 2)
    is_complete = len(missing_required) == 0

    completeness = KycCompleteness(
        is_complete=is_complete,
        score=score,
        required_fields=req_names,
        optional_fields=opt_names,
        missing_fields=missing_required,
        fields=fields,
    )
    return resolved, completeness, reg.items()


def needs_clarification(text: str, ext: Extraction, language: str = "fr") -> str | None:
    """ONE targeted question when an essential field is missing, else None."""
    ask_goal = ASK_GOAL_EN if language == "en" else ASK_GOAL
    primary = text.split("\n\n[Contexte investisseur]")[0].split("[Contexte investisseur]")[0].strip()
    if not primary:
        return ask_goal
    if ext.ticker is None and not _INTENT_RE.search(primary):
        return ask_goal  # e.g. "Je veux investir": no idea, no goal, no horizon
    if ext.ticker and ext.weight_pct is None:
        if language == "en":
            return f"What share of your portfolio would you like to allocate to {ext.ticker} (in %)?"
        return f"Quelle part de votre portefeuille souhaitez-vous consacrer à {ext.ticker} (en %) ?"
    return None


def _clean_tags(tags: list[str]) -> list[str]:
    out = []
    for t in tags:
        tag = re.sub(r"[^a-z0-9_]+", "_", t.strip().lower()).strip("_")
        if tag and tag not in out:
            out.append(tag)
    return out[:5]


def build_profile(
    persona_id: str,
    ext: Extraction,
    used_fallback: bool,
    persona_data: dict | None = None,
    kyc_completeness: KycCompleteness | None = None,
    resolved_kyc: dict[str, Any] | None = None,
    hard_gate_notes: list[str] | None = None,
    language: Literal["fr", "en"] = "fr",
) -> Profile:
    p = persona_data or (PERSONAS[persona_id] if persona_id in PERSONAS else {})
    ticker = _resolve_ticker(ext.ticker)
    idea = None
    if ticker and ext.weight_pct is not None and 0 < ext.weight_pct <= 100:
        idea = {"ticker": ticker, "weight": round(ext.weight_pct / 100, 4)}
    constraints = list(p.get("constraints") or [])
    for c in _clean_tags(ext.extra_constraints):
        if c in KNOWN_CONSTRAINTS and c not in constraints:
            constraints.append(c)
    preferences = list(p.get("preferences") or [])
    for t in _clean_tags(ext.extra_preferences):
        if t not in preferences:
            preferences.append(t)
    horizon = p.get("horizon_years", 5)
    if ext.horizon_years and 1 <= ext.horizon_years <= 50:
        horizon = ext.horizon_years
    budget = p.get("budget_cad")
    if ext.budget_cad and ext.budget_cad > 0:
        budget = float(ext.budget_cad)
    conflicts = detect_conflict(
        tolerance=p.get("risk_tolerance", "moderate"),
        horizon_years=horizon,
        constraints=constraints,
        idea=idea,
        max_loss_pct=p.get("max_loss_pct"),
        capacity=p.get("risk_capacity"),
        language=language,
    )
    for c in ext.conflicts[:2]:
        c = c.strip()
        if c and c not in conflicts:
            conflicts.append(c)
    if used_fallback:
        conflicts.append(
            "Assumption: Connection with the AI model failed (offline mode or missing AWS credentials); "
            "analysis was completed using deterministic fallback rules and reference profile parameters."
            if language == "en"
            else "Hypothèse : La connexion avec le modèle d'IA a échoué (mode hors-ligne ou identifiants AWS manquants) ; "
            "l'analyse a été complétée à l'aide des règles déterministes de secours et des paramètres du profil de référence."
        )
    current_holdings = None
    holdings_unanalysed: dict[str, float] = {}
    holdings_cash: float | None = None
    budget_inferred = False
    if p.get("current_holdings"):
        from alphaforge.holdings import parse_holdings

        current_holdings = parse_holdings(p["current_holdings"])
        holdings_unanalysed = dict(getattr(current_holdings, "unanalysed", {}))
        holdings_cash = getattr(current_holdings, "cash", None)
        if budget is None:
            # A balance, not a contribution: used for sizing, never compared with TFSA room.
            total_amt = getattr(current_holdings, "total_amount", None)
            if total_amt is not None and total_amt > 0:
                budget = float(total_amt)
                budget_inferred = True
            elif current_holdings and sum(current_holdings.values()) > 100:
                budget = float(sum(current_holdings.values()))
                budget_inferred = True

    from alphaforge.personas import declared_limits
    limits = declared_limits(persona_data or p)

    account_type = (
        (persona_data or {}).get("account_type")
        or (ext.account_type if getattr(ext, "account_type", None) else None)
        or p.get("account_type")
        or "non_registered"
    )
    resolved = resolved_kyc or {}
    gate_notes = list(hard_gate_notes or [])

    if resolved.get("has_emergency_fund") is False:
        conflicts.append("Garde-fou KYC : Fonds d'urgence manquant. Prioriser l'épargne de précaution.")
    if resolved.get("has_high_interest_debt") is True:
        conflicts.append("Garde-fou KYC : Dettes à taux élevé non soldées. Prioriser le remboursement des dettes.")

    # Record KYC assumptions in conflicts list so explainers and auditors see them
    if kyc_completeness:
        for f in kyc_completeness.fields.values():
            if f.required and not f.collected and f.assumption_note:
                conflicts.append(f"Hypothèse KYC ({f.evidence_id}) : {f.assumption_note}")

    age_band_val = limits.get("age_band")
    # Only a stated amount is compared with the room: a TFSA balance inferred from the
    # holdings can exceed the cumulative room through growth (#186, item 3).
    if account_type == "tfsa" and budget and age_band_val and not budget_inferred:
        from alphaforge.tax import tfsa_room_check, tfsa_room_sentences
        room_chk = tfsa_room_check(account_type, budget, age_band_val)
        if room_chk:
            fr_room, _ = tfsa_room_sentences(room_chk)
            if fr_room not in conflicts:
                conflicts.append(fr_room)

    return Profile(
        persona=persona_id,
        objective=p.get("objective", "balanced"),
        horizon_years=horizon,
        risk_tolerance=p.get("risk_tolerance", "moderate"),
        risk_capacity=p.get("risk_capacity", "moderate"),
        constraints=constraints,
        preferences=preferences,
        budget_cad=budget,
        budget_inferred=budget_inferred,
        account_type=account_type,
        request_type="judge" if idea else "build",
        requested_idea=idea,
        conflicts=conflicts,
        current_holdings=current_holdings,
        not_analysed_holdings=list(holdings_unanalysed.keys()),
        has_emergency_fund=resolved.get("has_emergency_fund"),
        has_high_interest_debt=resolved.get("has_high_interest_debt"),
        debt_level=resolved.get("debt_level"),
        net_worth_share=resolved.get("net_worth_share"),
        net_worth_cad=resolved.get("net_worth_cad"),
        liquidity_need_12m=resolved.get("liquidity_need_12m"),
        investment_knowledge=resolved.get("investment_knowledge"),
        withdrawal_plan=resolved.get("withdrawal_plan"),
        income_stability=resolved.get("income_stability"),
        kyc_completeness=kyc_completeness,
        hard_gate_notes=gate_notes,
        language=language,
        requested_allocation=getattr(ext, "requested_allocation", None) or (
            {idea["ticker"]: idea["weight"]} if idea else None
        ),
        requested_vehicle=getattr(ext, "requested_vehicle", None),
        max_loss_12m=limits["max_loss_12m"],
        crypto_target_min=limits["crypto_target_min"],
        sector_cap=limits["sector_cap"],
        currency_pref=limits["currency_pref"],
        age_band=limits["age_band"],
        holdings_unanalysed=holdings_unanalysed,
        holdings_cash=holdings_cash,
    )


def is_contradictory_profile(
    conflicts: list[str],
    idea: dict | None,
    horizon_years: int,
    constraints: list[str],
) -> bool:
    """True when a profile has an irreconcilable conflict (e.g. crypto on short horizon) needing clarification."""
    if not idea:
        return bool(
            conflicts
            and any(
                "exclu" in c.lower()
                or "volatil" in c.lower()
                or "exclud" in c.lower()
                for c in conflicts
            )
        )
    ticker = idea.get("ticker", "")
    asset = _universe().get(ticker, {})
    if asset.get("asset_class") == "crypto":
        if "no_crypto" in constraints or horizon_years < CRYPTO_MIN_HORIZON_YEARS:
            return True
    return False


@traced("profile")
def profile_node(state: GraphState) -> dict:
    lang: Literal["fr", "en"] = getattr(state, "language", None) or detect_language(state.request_text)
    text = state.request_text.strip()
    # Dynamic ingestion of a security named outside the universe: no-op unless
    # AF_DYNAMIC_INGESTION=on (never in tests); any failure leaves the asset "Non analysé".
    ensure_requested_asset(text)
    update: dict = {"language": lang}
    kyc_answers: dict[str, Any] = {}
    clarified_count = state.retries.get("clarify", 0)
    asked_keys: set[str] = set()

    # LangGraph re-runs the node from the top on resume, so the decision to ask must be
    # deterministic (regex reading, no model call) for interrupt() to be reached again.
    # Clarification loop of up to 3 questions, ranked by impact on caps (#117).
    while clarified_count < 3:
        ext_pre = _regex_extract(text)
        next_key, next_q = get_next_clarification_question(
            persona_id=state.persona,
            persona_data=state.persona_data,
            text=text,
            ext=ext_pre,
            asked=asked_keys,
            current_kyc=kyc_answers,
            language=lang,
        )
        if not next_q or not next_key:
            break
        asked_keys.add(next_key)
        try:
            answer = str(interrupt({"question": next_q})).strip()
            text = f"{text} {answer}".strip()
            clarified_count += 1
            update = {"request_text": text, "retries": {"clarify": clarified_count}, "language": lang}
            apply_clarification_answer(next_key, answer, kyc_answers)
        except RuntimeError:
            break

    ext, fallback = extract_profile(
        state.persona_data or state.persona, text, kind="main", language=lang
    )

    p = state.persona_data or (PERSONAS[state.persona] if state.persona in PERSONAS else {})
    ticker = _resolve_ticker(ext.ticker)
    for k in ext.requested_allocation or {}:
        if k not in REQUEST_CLASS_CODES:
            _resolve_ticker(k)  # an allocation line naming an outside ticker may be ingested
    idea = (
        {"ticker": ticker, "weight": round(ext.weight_pct / 100, 4)}
        if ticker and ext.weight_pct is not None and 0 < ext.weight_pct <= 100
        else None
    )
    horizon = ext.horizon_years if (ext.horizon_years and 1 <= ext.horizon_years <= 50) else p.get("horizon_years", 5)
    constraints = list(p.get("constraints") or [])
    for c in _clean_tags(ext.extra_constraints):
        if c in KNOWN_CONSTRAINTS and c not in constraints:
            constraints.append(c)
    conflicts = detect_conflict(
        tolerance=p.get("risk_tolerance", "moderate"),
        horizon_years=horizon,
        constraints=constraints,
        idea=idea,
        capacity=p.get("risk_capacity"),
        language=lang,
    )

    if is_contradictory_profile(conflicts, idea, horizon, constraints):
        # Contradictory free-text profile: second pass on Opus 5.5 before asking the clarifying question
        ext, fallback = extract_profile(
            state.persona_data or state.persona, text, kind="review", language=lang
        )
        ticker = _resolve_ticker(ext.ticker)
        for k in ext.requested_allocation or {}:
            if k not in REQUEST_CLASS_CODES:
                _resolve_ticker(k)
        idea = (
            {"ticker": ticker, "weight": round(ext.weight_pct / 100, 4)}
            if ticker and ext.weight_pct is not None and 0 < ext.weight_pct <= 100
            else None
        )
        horizon = ext.horizon_years if (ext.horizon_years and 1 <= ext.horizon_years <= 50) else p.get("horizon_years", 5)
        conflicts = detect_conflict(
            tolerance=p.get("risk_tolerance", "moderate"),
            horizon_years=horizon,
            constraints=constraints,
            idea=idea,
            capacity=p.get("risk_capacity"),
            language=lang,
        )
        if is_contradictory_profile(conflicts, idea, horizon, constraints) and not state.retries.get("clarify"):
            target_asset = idea["ticker"] if idea else ("crypto assets" if lang == "en" else "cryptoactifs")
            clarif_q = (
                f"Your {horizon}-year horizon contradicts an investment in {target_asset}. "
                "Would you prefer to prioritize security for retirement or adjust your horizon?"
                if lang == "en"
                else
                f"Votre horizon de {horizon} ans contredit un investissement dans {target_asset}. "
                "Souhaitez-vous privilégier la sécurité pour votre retraite ou ajuster votre horizon ?"
            )
            try:
                answer = str(interrupt({"question": clarif_q})).strip()
                text = f"{text} {answer}".strip()
                update = {"request_text": text, "retries": {"clarify": 1}, "language": lang}
                ext, fallback = extract_profile(
                    state.persona_data or state.persona, text, kind="review", language=lang
                )
            except RuntimeError:
                pass

    budget = p.get("budget_cad")
    if ext.budget_cad and ext.budget_cad > 0:
        budget = float(ext.budget_cad)

    profile_fields = {
        "horizon_years": horizon,
        "risk_tolerance": p.get("risk_tolerance", "moderate"),
        "risk_capacity": p.get("risk_capacity", "moderate"),
        "budget_cad": budget,
    }
    resolved, completeness, kyc_evidence = build_kyc_completeness_and_assumptions(
        persona_id=state.persona,
        persona_data=state.persona_data,
        text=text,
        kyc_answers=kyc_answers,
        as_of_date=state.as_of_date,
        profile_fields=profile_fields,
    )

    # Hard gates: no emergency fund, or high-interest debt, produce a top-of-page note (#117)
    hard_gate_notes: list[str] = []
    if resolved.get("has_emergency_fund") is False:
        note = (
            "Avertissement préalable (Garde-fou : Absence de fonds d'urgence) : "
            "Vous avez indiqué ne pas disposer d'une réserve de liquidités équivalente à 3 à 6 mois de dépenses courantes. "
            "Tout investissement sur les marchés financiers comporte un risque de perte en capital. "
            "Une épargne de précaution de 3 à 6 mois de dépenses se constitue habituellement avant d'immobiliser "
            "des capitaux sur les marchés."
        )
        hard_gate_notes.append(note)
        conflicts.append("Garde-fou KYC : Fonds d'urgence manquant. Prioriser l'épargne de précaution.")

    if resolved.get("has_high_interest_debt") is True:
        note = (
            "Avertissement préalable (Garde-fou : Dettes à taux élevé) : "
            "Vous avez déclaré des dettes à taux d'intérêt élevé (cartes de crédit, prêts personnels). "
            "Rembourser une dette à taux élevé évite des intérêts dont le taux est connu d'avance et ne dépend pas "
            "des marchés. Dans un cadre de planification, ce remboursement passe habituellement avant tout investissement."
        )
        hard_gate_notes.append(note)
        conflicts.append("Garde-fou KYC : Dettes à taux élevé non soldées. Prioriser le remboursement des dettes.")

    profile = build_profile(
        persona_id=state.persona,
        ext=ext,
        used_fallback=fallback,
        persona_data=state.persona_data,
        kyc_completeness=completeness,
        resolved_kyc=resolved,
        hard_gate_notes=hard_gate_notes,
        language=lang,
    )

    if (
        profile.account_type == "tfsa"
        and profile.budget_cad
        and profile.age_band
        and not profile.budget_inferred
    ):
        from alphaforge.evidence import EvidenceRegistry
        from alphaforge.tax import tfsa_room_check, tfsa_room_evidence

        room_chk = tfsa_room_check(profile.account_type, profile.budget_cad, profile.age_band)
        if room_chk:
            reg_room = EvidenceRegistry(prefix="EK", start=len(kyc_evidence) + 1)
            ev_kw = tfsa_room_evidence(room_chk, state.as_of_date)
            reg_room.add(**ev_kw)
            kyc_evidence = {**kyc_evidence, **reg_room.items()}

    if profile.request_type == "judge":
        summary = (
            f"Profile understood: evaluation of {profile.requested_idea['ticker']}."
            if lang == "en"
            else f"Profil compris : évaluation de {profile.requested_idea['ticker']}."
        )
    else:
        summary = (
            "Profile understood: constructing an allocation."
            if lang == "en"
            else "Profil compris : construction d'une allocation."
        )
    if profile.conflicts:
        summary += (
            f" {len(profile.conflicts)} tension point(s) noted."
            if lang == "en"
            else f" {len(profile.conflicts)} point(s) de tension relevé(s)."
        )
    return {**update, "evidence": kyc_evidence, "profile": profile, "summary": summary}
