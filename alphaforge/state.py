"""Shared typed state. FROZEN CONTRACT (PRD 3.3): only the orchestrator edits this file."""

from __future__ import annotations

import datetime as dt
import operator
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

PersonaId = str
ScenarioName = Literal["as_requested", "capped", "profile_baseline"]

SCENARIO_NAMES: tuple[str, ...] = ("as_requested", "capped", "profile_baseline")

# Every scenario carries all of these keys in `metrics` (metric name -> evidence id).
SCENARIO_METRICS: tuple[str, ...] = (
    "volatility_ann",
    "max_drawdown",
    "stress_2022",
    "top_weight",
    "sector_concentration_hhi",
    "us_exposure",
)


class Profile(BaseModel):
    persona: PersonaId
    objective: str
    horizon_years: int
    risk_tolerance: Literal["low", "low_moderate", "moderate", "high"]
    risk_capacity: Literal["low", "moderate", "high"]
    constraints: list[str] = Field(default_factory=list)  # hard rules
    preferences: list[str] = Field(default_factory=list)  # soft
    budget_cad: float | None = None
    request_type: Literal["build", "judge"] = "build"
    requested_idea: dict | None = None  # {"ticker": "TSLA", "weight": 0.25}
    excluded_tickers: list[str] = Field(default_factory=list)  # set by what-if
    conflicts: list[str] = Field(default_factory=list)
    clarification_needed: str | None = None


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


def _merge(left: dict, right: dict) -> dict:
    return {**(left or {}), **(right or {})}


class GraphState(BaseModel):
    as_of_date: dt.date
    persona: PersonaId
    # Run-scoped persona table entry for questionnaire profiles. Kept in state (and
    # checkpoints) instead of mutating the global PERSONAS table.
    persona_data: dict[str, Any] | None = None
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
