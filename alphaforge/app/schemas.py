"""Pydantic schemas for AlphaForge AI explainability, governance, and analysis.

Defines standard data contracts adhering to docs/PLAN.md:
- ExplanationPayload (resume, quelles_donnees, pourquoi_ce_choix, limites, ce_qui_changerait_la_reponse, alertes_gouvernance)
- TraceEvent schemas
- AnalysisResult contracts
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class QuelleDonnee(BaseModel):
    """Claim describing the quantitative input data grounded in evidence."""
    claim: str = Field(..., description="Fact-based claim describing input data.")
    evidence_ids: list[str] = Field(default_factory=list, description="List of evidence IDs (E1, E2, ...).")


class PourquoiCeChoix(BaseModel):
    """Claim explaining the rationale for the allocation decision grounded in evidence."""
    claim: str = Field(..., description="Fact-based rationale for the portfolio choice.")
    evidence_ids: list[str] = Field(default_factory=list, description="List of evidence IDs (E1, E2, ...).")


class Limite(BaseModel):
    """Documented limitation of data, method, or model hypothesis."""
    text: str = Field(..., description="Description of the limitation or risk factor.")
    type: Literal["donnee", "methode", "hypothese"] = Field(
        ..., description="Category of limitation: donnee, methode, or hypothese."
    )


class AlerteGouvernance(BaseModel):
    """Governance alert raised during profile or allocation evaluation."""
    niveau: Literal["info", "attention", "bloquant"] = Field(
        ..., description="Severity level: info (blue), attention (orange), or bloquant (red)."
    )
    message: str = Field(..., description="Detailed governance message and rationale.")
    evidence_ids: list[str] = Field(default_factory=list, description="Relevant evidence IDs.")


class ExplanationPayload(BaseModel):
    """Structured explanation matching the 4-part BNCD explainability rubric."""
    resume: str = Field(..., description="Executive summary in <= 80 words.")
    quelles_donnees: list[QuelleDonnee] = Field(
        default_factory=list, description="What data were used, with evidence references."
    )
    pourquoi_ce_choix: list[PourquoiCeChoix] = Field(
        default_factory=list, description="Why this portfolio was selected, with evidence references."
    )
    limites: list[Limite] = Field(
        default_factory=list, description="Methodological and data limitations."
    )
    ce_qui_changerait_la_reponse: list[str] = Field(
        default_factory=list, description="What market conditions or profile changes would alter this allocation."
    )
    alertes_gouvernance: list[AlerteGouvernance] = Field(
        default_factory=list, description="Governance alerts associated with this profile and portfolio."
    )


class AnalysisResult(BaseModel):
    """Final output contract of an AlphaForge AI analysis run."""
    run_id: str
    persona_name: str
    capital: float
    allocation: dict[str, float]
    metrics: dict[str, float]
    stress_test: dict[str, Any]
    evidence: dict[str, Any]
    explanation: dict[str, Any]
    alerts: list[dict[str, Any]]
    trace: list[dict[str, Any]]
    verification: dict[str, Any]
