"""Shared typed state. FROZEN CONTRACT (PRD 3.3): only the orchestrator edits this file."""

from __future__ import annotations

import datetime as dt
import operator
from typing import Annotated, Literal

from pydantic import BaseModel, Field

PersonaId = str
ScenarioName = Literal["as_requested", "capped", "profile_baseline", "current"]

SCENARIO_NAMES: tuple[str, ...] = ("as_requested", "capped", "profile_baseline")

# Every scenario carries all of these keys in `metrics` (metric name -> evidence id).
SCENARIO_METRICS: tuple[str, ...] = (
    "volatility_ann",
    "max_drawdown",
    "stress_2022",
    "top_weight",
    "sector_concentration_hhi",
    "us_exposure",
    "tax_drag",
)

AccountType = Literal["tfsa", "rrsp", "fhsa", "non_registered", "mixed"]


# Ordered risk scale shared by tolerance and capacity (#115). Suitability follows the more
# conservative of what the client accepts (tolerance) and what their situation can absorb
# (capacity), as KYC suitability does.
RISK_SCALE: tuple[str, ...] = ("low", "low_moderate", "moderate", "high")


def effective_risk(tolerance: str, capacity: str) -> str:
    """The lower of tolerance and capacity on RISK_SCALE (unknown values count as moderate)."""
    rank = {r: i for i, r in enumerate(RISK_SCALE)}
    t = rank.get(tolerance, rank["moderate"])
    c = rank.get(capacity, rank["moderate"])
    return RISK_SCALE[min(t, c)]


def risk_gap(tolerance: str, capacity: str) -> int:
    """How many levels tolerance sits above capacity (0 when capacity is not the limit)."""
    rank = {r: i for i, r in enumerate(RISK_SCALE)}
    return rank.get(tolerance, 2) - rank.get(capacity, 2)


class Profile(BaseModel):
    persona: PersonaId
    objective: str
    horizon_years: int
    risk_tolerance: Literal["low", "low_moderate", "moderate", "high"]
    risk_capacity: Literal["low", "moderate", "high"]
    constraints: list[str] = Field(default_factory=list)  # hard rules
    preferences: list[str] = Field(default_factory=list)  # soft
    budget_cad: float | None = None
    account_type: AccountType = "non_registered"
    request_type: Literal["build", "judge"] = "build"
    requested_idea: dict | None = None  # {"ticker": "TSLA", "weight": 0.25}
    excluded_tickers: list[str] = Field(default_factory=list)  # set by what-if
    conflicts: list[str] = Field(default_factory=list)
    clarification_needed: str | None = None
    current_holdings: dict[str, float] | None = None
    not_analysed_holdings: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
    id: str  # E + node letter + number, e.g. "EQ12" (PRD 3.4)
    value: float | str | dict
    source: str
    date: dt.date
    date_kind: Literal["observation", "publication"] = "observation"
    url: str | None = None
    method: str
    confidence: Literal["fact", "assumption", "fictional"] = "fact"


class Scenario(BaseModel):
    name: ScenarioName
    weights: dict[str, float]  # ticker -> weight, sums to 1.0
    metrics: dict[str, str] = Field(default_factory=dict)  # metric name -> evidence id
    notes: list[str] = Field(default_factory=list)
    turnover: float | None = None
    trades: list[dict] | None = None


def _merge(left: dict, right: dict) -> dict:
    return {**(left or {}), **(right or {})}


class GraphState(BaseModel):
    as_of_date: dt.date
    persona: PersonaId
    # Questionnaire profiles travel in the state instead of the global persona table (#113).
    persona_data: dict | None = None
    # Opaque id of the browser session that started the run; used for access control (#111).
    owner: str | None = None
    request_text: str = ""
    profile: Profile | None = None
    eligible_universe: list[str] = Field(default_factory=list)
    exclusions: Annotated[list[dict], operator.add] = Field(default_factory=list)
    evidence: Annotated[dict[str, Evidence], _merge] = Field(default_factory=dict)
    events: Annotated[list[dict], operator.add] = Field(default_factory=list)
    scenarios: list[Scenario] = Field(default_factory=list)
    objections: list[dict] = Field(default_factory=list)
    explanation: dict | None = None
    verification: dict | None = None
    retries: Annotated[dict[str, int], _merge] = Field(default_factory=dict)
    trace: Annotated[list[dict], operator.add] = Field(default_factory=list)
