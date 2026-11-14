"""Governance Agent for AlphaForge AI.

Hierarchical Governance Architecture:
1. Deterministic Rule Engine First:
   - Evaluates codified rules (TSLA temptation, crypto prohibition, ESG thresholds, bond floor, concentration limits, disclaimer).
2. Claude Opus Escalation (global.anthropic.claude-opus-5-5):
   - Triggered when dealing with unstructured free-text profiles, contradictory risk tolerances,
     or requests containing out-of-scope/unsupported instruments (leverage, penny stocks, options).
   - Produces institutional risk warnings and constructive refusal recommendations.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pandas as pd

from alphaforge.app.bedrock import BedrockConverseClient, MODEL_OPUS
from alphaforge.app.governance import (
    GovernanceAlert,
    GovernanceReport,
    check_governance_rules,
)
from alphaforge.app.personas import Persona, get_persona
from alphaforge.app.trace import ExecutionTrace

logger = logging.getLogger(__name__)


OPUS_GOVERNANCE_SYSTEM_PROMPT = """Tu es l'Agent de Gouvernance Institutionnelle et de Conformité Réglementaire d'AlphaForge AI.
Ton mandat est d'évaluer la cohérence, l'adéquation investisseur et le respect réglementaire de la demande.

Principes stricts :
1. SIMULATION ÉDUCATIVE : Tout conseil d'investissement personnalisé ou incitation transactionnelle directe est strictement interdit.
2. REFUS CONSTRUCTIF : Lorsqu'un investisseur demande un actif incompatible avec son profil (ex. horizon court vers la retraite demandant des actifs ultra-volatils comme TSLA ou crypto), formule une alerte claire et propose une alternative prudente et plafonnée.
3. ADÉQUATION INVESTISSEUR : Compare l'âge, l'horizon temporel, et la tolérance au risque. Signale toute incohérence.
4. FORMAT DE SORTIE : Réponds STRICTEMENT en format JSON valide avec la clé 'alerts' contenant une liste d'objets :
   [
     {
       "rule_name": "nom_regle",
       "level": "info" | "attention" | "bloquant",
       "message": "Explication claire du risque ou de l'incohérence.",
       "suggested_action": "Action corrective ou recommandation d'allocation."
     }
   ]
Ne retourne AUCUN texte en dehors du bloc JSON.
"""


class GovernanceAgent:
    """Evaluates investor profile, proposed portfolio, and user queries against compliance standards."""

    def __init__(self, bedrock_client: BedrockConverseClient | None = None):
        self.bedrock = bedrock_client or BedrockConverseClient()

    def evaluate(
        self,
        persona: Persona,
        proposed_weights: dict[str, float],
        universe_df: pd.DataFrame,
        risk_summary_df: pd.DataFrame | None = None,
        user_requests: list[str] | None = None,
        trace: ExecutionTrace | None = None,
        force_opus: bool = False,
        is_free_text: bool = False,
    ) -> GovernanceReport:
        """Run governance checks using deterministic rules first, escalating to Claude Opus if necessary."""
        # 1. Deterministic Rule-Based Evaluation
        report = check_governance_rules(
            persona=persona,
            proposed_weights=proposed_weights,
            universe_df=universe_df,
            risk_summary_df=risk_summary_df,
            user_requests=user_requests,
        )

        # Emit trace events for deterministic alerts
        if trace is not None:
            for alert in report.alerts:
                trace.governance_alert(
                    level=alert.level,
                    rule_id=alert.rule_name,
                    message=alert.message,
                )

        # 2. Escalation to Claude Opus for free-text or ambiguous situations
        should_escalate = force_opus or is_free_text or (
            user_requests and any(
                kw in " ".join(user_requests).lower()
                for kw in ["levier", "leverage", "option", "penny", "derives", "crypto", "tout mettre"]
            )
        )

        if should_escalate:
            try:
                opus_alerts = self._escalate_to_opus(
                    persona=persona,
                    proposed_weights=proposed_weights,
                    user_requests=user_requests or [],
                    existing_alerts=report.alerts,
                    trace=trace,
                )
                if opus_alerts:
                    for oa in opus_alerts:
                        report.alerts.append(oa)
                        if oa.level == "bloquant":
                            report.has_blocking = True
                            report.passed = False
                        elif oa.level == "attention":
                            report.has_attention = True
                        if trace is not None:
                            trace.governance_alert(
                                level=oa.level,
                                rule_id=oa.rule_name,
                                message=oa.message,
                            )
            except Exception as e:
                logger.warning(f"Claude Opus governance escalation encountered an error: {e}")

        return report

    def _escalate_to_opus(
        self,
        persona: Persona,
        proposed_weights: dict[str, float],
        user_requests: list[str],
        existing_alerts: list[GovernanceAlert],
        trace: ExecutionTrace | None = None,
    ) -> list[GovernanceAlert]:
        """Invoke Claude Opus for qualitative and deep suitability compliance analysis."""
        prompt = (
            f"Profil investisseur : {persona.name}, {persona.age} ans, profession: {persona.profession}\n"
            f"Objectif : {persona.investment_objective}\n"
            f"Horizon : {persona.horizon_label}\n"
            f"Profil de risque : {persona.risk_profile}\n"
            f"Demandes spécifiques de l'utilisateur : {user_requests}\n"
            f"Poids proposés dans le portefeuille : {proposed_weights}\n"
            f"Alertes déterministes déjà levées : {[a.rule_name for a in existing_alerts]}\n\n"
            "Analyse qualitativement si la demande de l'utilisateur présente des risques d'adéquation, "
            "d'incohérence avec son horizon ou de dépassement des limites réglementaires. "
            "Sois concis : maximum 1 à 3 alertes courtes en JSON strict."
        )

        response = self.bedrock.converse(
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            system_prompt=OPUS_GOVERNANCE_SYSTEM_PROMPT,
            model_id=MODEL_OPUS,
            max_tokens=2500,
        )

        raw_text = self.bedrock.extract_text(response)
        alerts: list[GovernanceAlert] = []

        # Parse JSON output from Opus
        try:
            # Strip markdown code blocks if present
            cleaned = raw_text.strip()
            if cleaned.startswith("```"):
                lines = cleaned.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                cleaned = "\n".join(lines).strip()

            try:
                data = json.loads(cleaned)
            except Exception:
                for fix in ["}", "]}", "]}}"]:
                    try:
                        data = json.loads(cleaned + fix)
                        break
                    except Exception:
                        continue
                else:
                    data = {}
            alert_items = data.get("alerts", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            for item in alert_items:
                if isinstance(item, dict):
                    level = item.get("level", "attention")
                    if level not in ("info", "attention", "bloquant"):
                        level = "attention"
                    alerts.append(
                        GovernanceAlert(
                            rule_name=f"opus_{item.get('rule_name', 'suitability_alert')}",
                            level=level,
                            message=item.get("message", ""),
                            suggested_action=item.get("suggested_action"),
                        )
                    )
        except Exception as e:
            logger.warning(f"Could not parse Opus governance JSON response: {e}. Raw: {raw_text[:200]}")

        return alerts
