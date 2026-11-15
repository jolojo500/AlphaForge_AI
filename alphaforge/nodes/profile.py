"""Agent 1: profile (PRD 5.1). Owned by Track B.

The persona table (alphaforge/personas.py) gives the base profile. The model reads the free
text and fills gaps (requested idea, budget, horizon, extra preferences). Hard constraints
from the persona are never removed by the model. Contradictions are detected in code.

Invariant: the node either returns a `profile` or calls `interrupt()`. If the model fails,
it falls back to the persona table plus a regex read of the request.
"""
from __future__ import annotations

import csv
import re
from functools import lru_cache
from typing import Literal

from langgraph.types import interrupt
from pydantic import BaseModel, Field

from alphaforge import config, llm
from alphaforge.nodes.scenarios import CAPS
from alphaforge.personas import PERSONAS
from alphaforge.state import GraphState, Profile, effective_risk, risk_gap
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
CRYPTO_MIN_HORIZON_YEARS = 5

ASK_GOAL = "Que souhaitez-vous faire : construire une allocation ou évaluer une idée précise ?"

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
    r"portefeuille|allocation|r[ée]partition|[ée]quilibr|diversifi|responsable|esg|"
    r"horizon|\bans?\b|retraite|crypto|techno|action|obligation|fnb|etf|revenu|"
    r"pr[ée]serv|croissance|risque|\$|%|\d|portfolio|balanced|growth|income|years?",
    re.I,
)


class Extraction(BaseModel):
    """What the model reads from the free-text request. Every field is optional."""

    request_type: Literal["build", "judge"] = "build"
    ticker: str | None = None
    weight_pct: float | None = Field(default=None, description="share of the portfolio, in percent")
    budget_cad: float | None = None
    horizon_years: int | None = None
    extra_constraints: list[str] = Field(default_factory=list)
    extra_preferences: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


SYSTEM = (
    "You read the request of a retail investor for an educational simulation tool. "
    "Keep apart: horizon (when the money is needed), risk tolerance (what the person says they "
    "accept) and risk capacity (what their situation can absorb); age alone sets none of them. "
    "Extract only what the text says. Never invent a number, a ticker or a preference. "
    "Weights in words count: 'un quart' = 25, 'la moitié' = 50. "
    "request_type is 'judge' when the person proposes a specific asset or weight to evaluate, "
    "'build' when they want an allocation. ticker must be one of the listed tickers, else null. "
    "extra_constraints may only use: no_crypto, esg_only, no_controversies. "
    "extra_preferences are short snake_case tags (e.g. likes_tech, wants_income). "
    "conflicts: up to 2 short French sentences about a contradiction between the request and "
    "the persona hypotheses, or an empty list. No advice, no forecast."
)


@lru_cache(maxsize=1)
def _universe() -> dict[str, dict]:
    with open(config.STARTER_DIR / "assets_universe.csv", newline="") as f:
        return {r["ticker"]: r for r in csv.DictReader(f)}


def _resolve_ticker(raw: str | None) -> str | None:
    """Map a model or regex ticker to a ticker of the 31-asset universe, else None."""
    if not raw:
        return None
    universe = _universe()
    key = raw.strip().upper()
    for t in universe:
        if key in (t.upper(), t.upper().split(".")[0]):
            return t
    if key in ("CRYPTO", "BITCOIN", "BTC"):
        return "BTC-USD"
    if key in ("ETHER", "ETHEREUM", "ETH"):
        return "ETH-USD"
    return None


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
    if not ticker and weight is not None and re.search(r"\bcrypto\b", lowered):
        ticker = "BTC-USD"
    horizon = None
    m_h = re.search(r"(\d+)\s*ans?\b", lowered)
    if m_h:
        horizon = int(m_h.group(1))
    return Extraction(
        request_type="judge" if ticker else "build",
        ticker=ticker,
        weight_pct=weight,
        horizon_years=horizon,
    )


def extract_profile(
    state_persona: str,
    text: str,
    *,
    kind: llm.ModelKind = "main",
    llm_client=None,
) -> tuple[Extraction, bool]:
    """Read the request. Returns (extraction, used_fallback)."""
    if not text.strip():
        return Extraction(), False
    persona = state_persona if isinstance(state_persona, dict) else PERSONAS[state_persona]
    prompt = (
        f"Persona hypotheses: objective={persona['objective']}, horizon={persona['horizon_years']} "
        f"years, tolerance={persona['risk_tolerance']}, capacity={persona['risk_capacity']}, "
        f"constraints={persona['constraints']}, preferences={persona['preferences']}.\n"
        f"Allowed tickers: {', '.join(sorted(_universe()))}.\n"
        f'Request (French): """{text}"""'
    )
    try:
        return llm.call_json(prompt, Extraction, kind=kind, system=SYSTEM, llm=llm_client), False
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
) -> list[str]:
    """Contradictions between the requested idea and the stated profile (deterministic)."""
    out: list[str] = []
    level = effective_risk(tolerance, capacity) if capacity else tolerance
    if capacity and risk_gap(tolerance, capacity) >= 2:
        out.append(
            f"La tolérance au risque déclarée « {TOLERANCE_FR.get(tolerance, tolerance)} » dépasse "
            f"nettement la capacité financière « {TOLERANCE_FR.get(capacity, capacity)} » : les "
            "limites du profil suivent la capacité, la plus prudente des deux."
        )
    if max_loss_pct is not None:
        tol_fr = TOLERANCE_FR.get(tolerance, tolerance)
        if max_loss_pct <= 5.0 and tolerance in ("high", "moderate"):
            out.append(
                f"Une tolérance de perte sur 12 mois de {max_loss_pct:.0f} % est en contradiction "
                f"avec une tolérance au risque déclarée « {tol_fr} »."
            )
        elif max_loss_pct <= 15.0 and tolerance == "high":
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
        lvl_str = TOLERANCE_FR.get(level, level)
        basis = "un niveau de risque retenu" if level != tolerance else "une tolérance au risque"
        out.append(
            f"{weight:.0%} dans {ticker} dépasse le plafond de référence de {cap:.0%} par action "
            f"pour {basis} « {lvl_str} » et un horizon de {horizon_years} ans."
        )
    if asset.get("asset_class") == "crypto":
        if "no_crypto" in constraints:
            out.append(f"{ticker} est un cryptoactif, exclu par les contraintes du profil.")
        elif horizon_years < CRYPTO_MIN_HORIZON_YEARS:
            out.append(
                f"{ticker} est très volatil pour un horizon de {horizon_years} ans "
                f"(moins de {CRYPTO_MIN_HORIZON_YEARS} ans)."
            )
    return out


def needs_clarification(text: str, ext: Extraction) -> str | None:
    """ONE targeted question when an essential field is missing, else None."""
    if not text.strip():
        return ASK_GOAL
    if ext.ticker is None and not _INTENT_RE.search(text):
        return ASK_GOAL  # e.g. "Je veux investir": no idea, no goal, no horizon
    if ext.ticker and ext.weight_pct is None:
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
    persona_id: str, ext: Extraction, used_fallback: bool, persona_data: dict | None = None
) -> Profile:
    p = persona_data or PERSONAS[persona_id]
    ticker = _resolve_ticker(ext.ticker)
    idea = None
    if ticker and ext.weight_pct is not None and 0 < ext.weight_pct <= 100:
        idea = {"ticker": ticker, "weight": round(ext.weight_pct / 100, 4)}
    constraints = list(p["constraints"])
    for c in _clean_tags(ext.extra_constraints):
        if c in KNOWN_CONSTRAINTS and c not in constraints:
            constraints.append(c)
    preferences = list(p["preferences"])
    for t in _clean_tags(ext.extra_preferences):
        if t not in preferences:
            preferences.append(t)
    horizon = p["horizon_years"]
    if ext.horizon_years and 1 <= ext.horizon_years <= 50:
        horizon = ext.horizon_years
    budget = p["budget_cad"]
    if ext.budget_cad and ext.budget_cad > 0:
        budget = float(ext.budget_cad)
    conflicts = detect_conflict(
        tolerance=p["risk_tolerance"],
        horizon_years=horizon,
        constraints=constraints,
        idea=idea,
        max_loss_pct=p.get("max_loss_pct"),
        capacity=p.get("risk_capacity"),
    )
    for c in ext.conflicts[:2]:
        c = c.strip()
        if c and c not in conflicts:
            conflicts.append(c)
    if used_fallback:
        conflicts.append(
            "Hypothèse : la demande a été lue de façon simplifiée ; le profil repose sur les "
            "hypothèses du persona."
        )
    return Profile(
        persona=persona_id,
        objective=p["objective"],
        horizon_years=horizon,
        risk_tolerance=p["risk_tolerance"],
        risk_capacity=p["risk_capacity"],
        constraints=constraints,
        preferences=preferences,
        budget_cad=budget,
        request_type="judge" if idea else "build",
        requested_idea=idea,
        conflicts=conflicts,
    )


def is_contradictory_profile(
    conflicts: list[str],
    idea: dict | None,
    horizon_years: int,
    constraints: list[str],
) -> bool:
    """True when a profile has an irreconcilable conflict (e.g. crypto on short horizon) needing clarification."""
    if not idea:
        return bool(conflicts and any("exclu" in c or "volatil" in c for c in conflicts))
    ticker = idea.get("ticker", "")
    asset = _universe().get(ticker, {})
    if asset.get("asset_class") == "crypto":
        if "no_crypto" in constraints or horizon_years < CRYPTO_MIN_HORIZON_YEARS:
            return True
    return False


@traced("profile")
def profile_node(state: GraphState) -> dict:
    text = state.request_text.strip()
    update: dict = {}
    # LangGraph re-runs the node from the top on resume, so the decision to ask must be
    # deterministic (regex reading, no model call) for interrupt() to be reached again.
    question = needs_clarification(text, _regex_extract(text))
    if question and not state.retries.get("clarify"):
        try:
            answer = str(interrupt({"question": question})).strip()
            text = f"{text} {answer}".strip()
            update = {"request_text": text, "retries": {"clarify": 1}}
        except RuntimeError:
            pass

    ext, fallback = extract_profile(state.persona_data or state.persona, text, kind="main")

    p = state.persona_data or PERSONAS[state.persona]
    ticker = _resolve_ticker(ext.ticker)
    idea = (
        {"ticker": ticker, "weight": round(ext.weight_pct / 100, 4)}
        if ticker and ext.weight_pct is not None and 0 < ext.weight_pct <= 100
        else None
    )
    horizon = ext.horizon_years if (ext.horizon_years and 1 <= ext.horizon_years <= 50) else p["horizon_years"]
    constraints = list(p["constraints"])
    for c in _clean_tags(ext.extra_constraints):
        if c in KNOWN_CONSTRAINTS and c not in constraints:
            constraints.append(c)
    conflicts = detect_conflict(
        tolerance=p["risk_tolerance"], horizon_years=horizon, constraints=constraints, idea=idea,
        capacity=p.get("risk_capacity"),
    )

    if is_contradictory_profile(conflicts, idea, horizon, constraints):
        # Contradictory free-text profile: second pass on Opus 5.5 before asking the clarifying question
        ext, fallback = extract_profile(state.persona_data or state.persona, text, kind="review")
        ticker = _resolve_ticker(ext.ticker)
        idea = (
            {"ticker": ticker, "weight": round(ext.weight_pct / 100, 4)}
            if ticker and ext.weight_pct is not None and 0 < ext.weight_pct <= 100
            else None
        )
        horizon = ext.horizon_years if (ext.horizon_years and 1 <= ext.horizon_years <= 50) else p["horizon_years"]
        conflicts = detect_conflict(
            tolerance=p["risk_tolerance"], horizon_years=horizon, constraints=constraints, idea=idea,
        capacity=p.get("risk_capacity"),
        )
        if is_contradictory_profile(conflicts, idea, horizon, constraints) and not state.retries.get("clarify"):
            target_asset = idea["ticker"] if idea else "cryptoactifs"
            clarif_q = (
                f"Votre horizon de {horizon} ans contredit un investissement dans {target_asset}. "
                "Souhaitez-vous privilégier la sécurité pour votre retraite ou ajuster votre horizon ?"
            )
            try:
                answer = str(interrupt({"question": clarif_q})).strip()
                text = f"{text} {answer}".strip()
                update = {"request_text": text, "retries": {"clarify": 1}}
                ext, fallback = extract_profile(state.persona_data or state.persona, text, kind="review")
            except RuntimeError:
                pass

    profile = build_profile(state.persona, ext, fallback, state.persona_data)
    if profile.request_type == "judge":
        summary = f"Profil compris : évaluation de {profile.requested_idea['ticker']}."
    else:
        summary = "Profil compris : construction d'une allocation."
    if profile.conflicts:
        summary += f" {len(profile.conflicts)} point(s) de tension relevé(s)."
    return {**update, "profile": profile, "summary": summary}
