"""Persona hypotheses (PRD 7). Created by the skeleton; owned by Track B from B-2 on."""

from __future__ import annotations

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
        "account_type": "non_registered",
        "has_emergency_fund": True,
        "has_high_interest_debt": False,
        "debt_level": "none",
        "net_worth_share": 0.20,
        "net_worth_cad": 500_000.0,
        "liquidity_need_12m": "none",
        "current_holdings": [],
        "investment_knowledge": "intermediate",
        "withdrawal_plan": "none",
        "income_stability": "stable",
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
        "account_type": "non_registered",
        "has_emergency_fund": True,
        "has_high_interest_debt": False,
        "debt_level": "mortgage_only",
        "net_worth_share": 0.15,
        "net_worth_cad": 500_000.0,
        "liquidity_need_12m": "none",
        "current_holdings": ["pension"],
        "investment_knowledge": "intermediate",
        "withdrawal_plan": "none",
        "income_stability": "stable",
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
        "account_type": "rrsp",
        "has_emergency_fund": True,
        "has_high_interest_debt": False,
        "debt_level": "none",
        "net_worth_share": 0.25,
        "net_worth_cad": 400_000.0,
        "liquidity_need_12m": "none",
        "current_holdings": ["pension"],
        "investment_knowledge": "beginner",
        "withdrawal_plan": "capital_preservation",
        "income_stability": "stable",
        "example_request": "Je veux mettre 25 % de mon portefeuille dans TSLA.",
    },
}


# --- Questionnaire answers -> codes and declared limits (final report, fixes 3 and P1) -----
import logging  # noqa: E402
import re  # noqa: E402
import unicodedata  # noqa: E402

_log = logging.getLogger(__name__)

# Every preference the engine knows, as a code. Questionnaire labels are mapped to these;
# anything else is rejected loudly rather than passed through as raw text.
PREFERENCE_CODES: frozenset[str] = frozenset(
    {
        "likes_tech",
        "likes_crypto",
        "likes_energy",
        "likes_financials",
        "likes_dividends",
        "likes_healthcare",
        "likes_bonds",
        "likes_gold",
        "wants_diversification",
        "wants_balance",
        "wants_income",
        "wants_growth",
        "esg_tilt",
    }
)
# (pattern on the accent-free lower-case answer, code). First match wins.
_PREFERENCE_LABELS: list[tuple[str, str]] = [
    (r"responsable|\besg\b|durable|sustainab", "esg_tilt"),
    (r"\btechno|\btech\b|\bia\b|\bai\b|intelligence artificielle", "likes_tech"),
    (r"crypto|bitcoin", "likes_crypto"),
    (r"energie|energy|ressources|resources|petrole|\boil\b", "likes_energy"),
    (r"banque|bank|financ", "likes_financials"),
    (r"dividende|dividend|services publics|utilit", "likes_dividends"),
    (r"sante|health|consommation|consumer", "likes_healthcare"),
    (r"obligation|bond|revenu fixe|fixed income", "likes_bonds"),
    (r"\bor\b|gold|refuge", "likes_gold"),
    (r"diversifi", "wants_diversification"),
    (r"equilibr|balanced", "wants_balance"),
    (r"revenu|income", "wants_income"),
    (r"croissance|growth", "wants_growth"),
]
PREFERENCE_LABEL_FR: dict[str, str] = {
    "likes_tech": "technologies",
    "likes_crypto": "cryptoactifs",
    "likes_energy": "énergie et ressources",
    "likes_financials": "banques et finance",
    "likes_dividends": "dividendes et services publics",
    "likes_healthcare": "santé et consommation",
    "likes_bonds": "obligations et revenu fixe",
    "likes_gold": "or et valeurs refuges",
    "wants_diversification": "diversification",
    "wants_balance": "équilibre",
    "wants_income": "revenu",
    "wants_growth": "croissance",
    "esg_tilt": "investissement responsable (ESG)",
}
_CODE_RE = re.compile(r"^(?:likes|wants)_[a-z0-9_]{2,30}$")


def _plain(text: str) -> str:
    """Lower-case, accent-free text for matching questionnaire labels."""
    norm = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in norm if not unicodedata.combining(c)).lower().strip()


def preference_code(answer: str) -> str | None:
    """Code of one preference answer (a code or a questionnaire label), None if unknown."""
    raw = str(answer).strip()
    if raw in PREFERENCE_CODES or _CODE_RE.match(raw):
        return raw
    plain = _plain(raw)
    if not plain:
        return None
    for pattern, code in _PREFERENCE_LABELS:
        if re.search(pattern, plain):
            return code
    return None


def normalise_preferences(answers: list | None) -> tuple[list[str], list[str]]:
    """(codes, unmapped answers). Unknown answers are logged and returned, never passed on."""
    codes: list[str] = []
    unknown: list[str] = []
    for a in answers or []:
        code = preference_code(a)
        if code is None:
            if str(a).strip():
                _log.warning("Unmapped preference answer rejected: %r", a)
                unknown.append(str(a).strip())
        elif code not in codes:
            codes.append(code)
    return codes, unknown


def _ratio(value) -> float | None:
    """25 or "25 %" or 0.25 -> 0.25. None when the answer holds no usable number."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        x = float(value)
    else:
        m = re.search(r"\d+(?:[.,]\d+)?", str(value))
        if not m:
            return None
        x = float(m.group(0).replace(",", "."))
        if "%" in str(value) or x > 1:
            x /= 100.0
        return x if 0 <= x <= 1 else None
    if x < 0:
        return None
    if x > 1:
        x /= 100.0
    return x if x <= 1 else None


def crypto_target_min(answer) -> float | None:
    """Minimum crypto share implied by the crypto preference answer, as a ratio.

    "15 % et plus" -> 0.15; "Favorable (5 à 15 %)" -> 0.05; "Jusqu'à 5 %" -> 0.0 (an upper
    bound sets no minimum); "Aucune" / "Exclusion totale (0 % crypto)" -> 0.0; unknown -> None.
    """
    if answer is None:
        return None
    if isinstance(answer, (int, float)) and not isinstance(answer, bool):
        return _ratio(answer)
    plain = _plain(answer)
    if not plain or "non specifie" in plain or "not specified" in plain:
        return None
    if re.search(r"aucun|exclu|\bnone\b|\bno crypto\b|\bnon\b", plain):
        return 0.0
    nums = [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", plain)]
    if not nums:
        return None
    if re.search(r"jusqu|up to|maximum|\bmax\b|au plus|at most|moins de|less than", plain):
        return 0.0
    low = min(nums) if len(nums) > 1 else nums[0]
    return round(low / 100.0, 4) if low <= 100 else None


def currency_pref(answer) -> str | None:
    """"cad" | "usd" | "mixed", None when no currency limit is declared."""
    if answer is None:
        return None
    plain = _plain(answer)
    if re.search(r"mixte|mixed|cad\s*/\s*usd|cad et usd|cad and usd", plain):
        return "mixed"
    if re.search(r"\bcad\b|canadien|canadian", plain):
        return "cad"
    if re.search(r"\busd\b|americain|us dollar", plain):
        return "usd"
    return None


def age_band(answer) -> str | None:
    """"18–29 ans" -> "18-29"; "60+" kept as "60+". None when there is no number."""
    if answer is None:
        return None
    text = str(answer).strip()
    nums = re.findall(r"\d+", text)
    if not nums:
        return None
    if len(nums) >= 2:
        return f"{nums[0]}-{nums[1]}"
    plain = _plain(text)
    if "+" in text or "plus" in plain or "over" in plain:
        return f"{nums[0]}+"
    if "moins" in plain or "under" in plain or "<" in text:
        return f"<{nums[0]}"
    return nums[0]


def declared_limits(persona_data: dict | None) -> dict:
    """Declared limits of a questionnaire profile as `Profile` fields. Missing keys -> None."""
    p = persona_data or {}
    return {
        "max_loss_12m": _ratio(p.get("max_loss_pct")),
        "crypto_target_min": crypto_target_min(p.get("crypto_preference")),
        "sector_cap": _ratio(p.get("sector_cap_pct")),
        "currency_pref": currency_pref(p.get("currency_preference")),
        "age_band": age_band(p.get("age_band")),
    }
