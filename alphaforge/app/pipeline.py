"""End-to-end investment analysis pipeline for AlphaForge AI.

Orchestrates:
1. Observable ExecutionTrace collection & live event streaming.
2. EvidenceRegistry registration of all quantitative steps.
3. OrchestratorAgent (data loading, risk metrics, strategic optimization, stress testing).
4. GovernanceAgent (rules 1-6 + Claude Opus escalation for ambiguous/free-text profiles).
5. ExplainerAgent (grounded in E# evidence, Pydantic validation, deterministic verification, 1 regeneration).
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Callable

from alphaforge.app.agents.explainer import ExplainerAgent
from alphaforge.app.agents.governance import GovernanceAgent
from alphaforge.app.agents.interpreter import RequestInterpreterAgent
from alphaforge.app.agents.orchestrator import OrchestratorAgent
from alphaforge.app.bedrock import BedrockConverseClient
from alphaforge.app.evidence import EvidenceRegistry
from alphaforge.app.personas import Persona, PersonaConstraints, get_persona
from alphaforge.app.trace import ExecutionTrace, TraceEvent

logger = logging.getLogger(__name__)


def _build_custom_persona(profile_data: dict[str, Any] | str) -> tuple[Persona, bool]:
    """Construct a Persona object from custom or free-text profile data."""
    if isinstance(profile_data, str):
        # Free-text profile string
        base = get_persona("mateo")
        custom = Persona(
            id="profil_libre",
            name="Profil Libre",
            age=40,
            profession="Investisseur Autonome",
            family_status="Indéterminé",
            investment_experience="Intermédiaire",
            investment_objective=profile_data[:100],
            horizon_label="5 à 10 ans",
            horizon_years_min=5,
            horizon_years_max=10,
            risk_profile="moderate",
            case_preferences=[profile_data],
            reality_test="Analyse qualitative approfondie par Claude Opus requise pour profil non standardisé.",
            team_assumptions={"profil": "libre", "source": "saisie_utilisateur"},
            constraints=base.constraints,
        )
        return custom, True

    # Dict-based profile
    risk = profile_data.get("risk_profile", "moderate")
    base_id = "amira" if risk == "high" else ("robert" if "low" in risk else "mateo")
    base = get_persona(base_id)

    custom = Persona(
        id="profil_libre",
        name=profile_data.get("name", "Investisseur Libre"),
        age=int(profile_data.get("age", 40)),
        profession=profile_data.get("profession", "Professionnel"),
        family_status=profile_data.get("family_status", "Non spécifié"),
        investment_experience=profile_data.get("investment_experience", "Intermédiaire"),
        investment_objective=profile_data.get("investment_objective", "Croissance équilibrée du capital"),
        horizon_label=profile_data.get("horizon_label", "5 à 10 ans"),
        horizon_years_min=int(profile_data.get("horizon_years_min", 5)),
        horizon_years_max=int(profile_data.get("horizon_years_max", 10)),
        risk_profile=risk,
        case_preferences=profile_data.get("case_preferences", ["Objectifs définis par l'utilisateur"]),
        reality_test="Profil personnalisé soumis à la gouvernance élargie.",
        team_assumptions={"custom": "true"},
        constraints=base.constraints,
    )
    return custom, True


def run_analysis(
    persona_or_profile: str | dict[str, Any] | Persona,
    capital: float = 100000.0,
    question: str = "",
    on_event: Callable[[TraceEvent], None] | None = None,
    bedrock_client: BedrockConverseClient | None = None,
    force_opus: bool = False,
) -> dict[str, Any]:
    """Execute end-to-end AlphaForge investment analysis with observable trace and evidence verification.

    Args:
        persona_or_profile: Persona ID ('amira', 'mateo', 'robert'), custom dict, or Persona instance.
        capital: Fictitious investment capital in CAD (default: 100,000 $).
        question: Free-text question or specific asset request (e.g., 'Je veux ajouter Tesla TSLA').
        on_event: Real-time callback for observable trace events (Streamlit st.status).
        bedrock_client: Optional shared BedrockConverseClient.
        force_opus: Force Claude Opus governance evaluation.

    Returns:
        Structured result dict matching AnalysisResult schema:
        {run_id, persona, capital, allocation, dollar_amounts, metrics, stress_test, evidence, explanation, alerts, trace, verification}
    """
    trace = ExecutionTrace(on_event=on_event)
    registry = EvidenceRegistry()
    client = bedrock_client or BedrockConverseClient()

    # 1. Resolve Persona
    is_free_text = False
    if isinstance(persona_or_profile, Persona):
        persona = persona_or_profile
    elif isinstance(persona_or_profile, str) and persona_or_profile.lower().strip() in ("amira", "mateo", "robert"):
        persona = get_persona(persona_or_profile.lower().strip())
    else:
        persona, is_free_text = _build_custom_persona(persona_or_profile)

    user_requests = [question] if question.strip() else []

    # 2. Instantiate Agents
    interpreter = RequestInterpreterAgent(bedrock_client=client)
    orchestrator = OrchestratorAgent(bedrock_client=client)
    governance = GovernanceAgent(bedrock_client=client)
    explainer = ExplainerAgent(bedrock_client=client)

    # 3. Interpret Natural Language Request
    parsed_request = interpreter.interpret(
        question=question,
        registry=registry,
        trace=trace,
    )

    # 4. Quantitative Orchestration (Bedrock Tool Loop & Core Pipeline)
    orchestrator_output = orchestrator.run(
        persona=persona,
        capital=capital,
        parsed_request=parsed_request,
        registry=registry,
        trace=trace,
    )

    # 5. Governance Evaluation (Natural Language Adequation + Rules + Opus)
    if trace:
        trace.step_start("5. Contrôle de Gouvernance & Conformité", "Validation des politiques d'adéquation et détection de risques.")

    gov_report = governance.evaluate(
        persona=persona,
        proposed_weights=orchestrator_output["weights"],
        universe_df=orchestrator_output["universe_df"],
        risk_summary_df=orchestrator_output["risk_summary_df"],
        user_requests=user_requests,
        parsed_request=parsed_request,
        orchestrator_output=orchestrator_output,
        registry=registry,
        trace=trace,
        force_opus=force_opus,
        is_free_text=is_free_text,
    )

    # 6. Explainer Generation with Verifier Loop
    explanation_payload, verif_report = explainer.generate_explanation(
        persona=persona,
        capital=capital,
        user_question=question,
        orchestrator_output=orchestrator_output,
        governance_report=gov_report,
        registry=registry,
        trace=trace,
    )

    trace.done(f"Analyse terminée avec succès pour {persona.name}. Fidélité numérique vérifiée : {verif_report.is_valid}.")

    return {
        "run_id": trace.run_id,
        "persona": asdict(persona),
        "persona_name": persona.name,
        "capital": capital,
        "parsed_request": parsed_request.model_dump(),
        "execution_path": orchestrator_output.get("execution_path", "deterministic"),
        "requested_evaluations": orchestrator_output.get("requested_evaluations", []),
        "allocation": orchestrator_output["weights"],
        "dollar_amounts": orchestrator_output["dollar_amounts"],
        "metrics": orchestrator_output["metrics"],
        "stress_test": orchestrator_output["stress_test"],
        "evidence": registry.to_dict(),
        "explanation": explanation_payload,
        "alerts": [a.to_dict() for a in gov_report.alerts],
        "trace": trace.to_dict(),
        "verification": verif_report.to_dict(),
    }
