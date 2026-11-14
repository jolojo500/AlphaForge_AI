"""Governance Agent for AlphaForge AI.

Hierarchical Governance Architecture:
1. Natural Language Intent & Adequation Engine:
   - Consumes ParsedRequest to evaluate requested positions against investor horizon and mandate.
   - Robert + TSLA: Incoherence ATTENTION alert with TSLA's own metrics as evidence + computed constructive alternative (3% satellite).
   - Amira + 100% Crypto: Diversification ATTENTION alert + capped 10% alternative.
   - Mateo + ENB: ESG tension ATTENTION alert + clean dividend alternatives.
   - Out-of-scope / Unknown assets: Unsuitability and regulatory boundary warnings.
2. Deterministic Rule Engine:
   - Evaluates codified rules (TSLA temptation, crypto prohibition, ESG thresholds, bond floor, concentration limits, disclaimer).
3. Claude Opus Escalation (global.anthropic.claude-opus-5-5):
   - Triggered when dealing with unstructured free-text profiles, contradictory risk tolerances,
     or requests containing out-of-scope/unsupported instruments (leverage, penny stocks, options).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pandas as pd

from alphaforge.app.bedrock import BedrockConverseClient, MODEL_OPUS
from alphaforge.app.evidence import EvidenceRegistry
from alphaforge.app.governance import (
    GovernanceAlert,
    GovernanceReport,
    check_governance_rules,
)
from alphaforge.app.personas import Persona
from alphaforge.app.schemas import ParsedRequest
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
        parsed_request: ParsedRequest | None = None,
        orchestrator_output: dict[str, Any] | None = None,
        registry: EvidenceRegistry | None = None,
        trace: ExecutionTrace | None = None,
        force_opus: bool = False,
        is_free_text: bool = False,
    ) -> GovernanceReport:
        """Run governance checks using natural language adequation, deterministic rules, and Opus escalation."""
        # 1. Deterministic Rule-Based Evaluation
        report = check_governance_rules(
            persona=persona,
            proposed_weights=proposed_weights,
            universe_df=universe_df,
            risk_summary_df=risk_summary_df,
            user_requests=user_requests,
        )

        # 2. Evaluate Parsed Request Intent & Adequation (Natural Language Reality Checks)
        if parsed_request:
            self._evaluate_parsed_request(
                persona=persona,
                parsed_request=parsed_request,
                orchestrator_output=orchestrator_output or {},
                report=report,
                trace=trace,
            )

        # Emit trace events for alerts
        if trace is not None:
            for alert in report.alerts:
                trace.governance_alert(
                    level=alert.level,
                    rule_id=alert.rule_name,
                    message=alert.message,
                )

        # 3. Escalation to Claude Opus for free-text or ambiguous situations
        should_escalate = force_opus or is_free_text or (
            parsed_request and parsed_request.out_of_scope
        ) or (
            user_requests and any(
                kw in " ".join(user_requests).lower()
                for kw in ["levier", "leverage", "option", "penny", "derives", "tout mettre"]
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

    def _evaluate_parsed_request(
        self,
        persona: Persona,
        parsed_request: ParsedRequest,
        orchestrator_output: dict[str, Any],
        report: GovernanceReport,
        trace: ExecutionTrace | None = None,
    ) -> None:
        """Apply specialized adequation rules to parsed natural language requests."""
        requested_evals = orchestrator_output.get("requested_evaluations", [])
        eval_map = {e["comparison"]["ticker"]: e for e in requested_evals if "comparison" in e}

        # Group crypto requests for Amira to avoid duplicate alerts (Issue #33)
        crypto_reqs = [p for p in parsed_request.requested_positions if p.ticker in ("BTC-USD", "ETH-USD")]
        handled_crypto = False

        for req_pos in parsed_request.requested_positions:
            ticker = req_pos.ticker
            raw_weight = req_pos.weight

            # --- CASE 1: Robert + TSLA (Hyped Asset Temptation vs Capital Preservation) ---
            if persona.id == "robert" and ticker == "TSLA":
                eval_data = eval_map.get("TSLA", {})
                e_asset_id = eval_data.get("asset_evidence_id", "E2")
                e_comp_id = eval_data.get("comparison_evidence_id", "E3")
                comp = eval_data.get("comparison", {})

                base_vol = comp.get("baseline", {}).get("annualized_volatility", 0.0399)
                req_vol = comp.get("requested", {}).get("annualized_volatility", 0.1263)
                alt_vol = comp.get("capped_alternative", {}).get("annualized_volatility", 0.0454)
                tsla_vol = eval_data.get("asset_metrics", {}).get("annualized_volatility", 0.5818)
                tsla_dd = eval_data.get("asset_metrics", {}).get("max_drawdown", -0.7088)

                # Format weight string without inventing silent 0.20
                if raw_weight is not None:
                    weight_label = f"{raw_weight:.1%}"
                    weight_val = raw_weight
                else:
                    weight_label = "une allocation dans Tesla (pondération non précisée)"
                    weight_val = 0.05

                # Remove generic rule alerts to prioritize the precise evidence-backed alert
                report.alerts = [a for a in report.alerts if not a.rule_name.startswith("robert_tsla")]

                report.alerts.append(
                    GovernanceAlert(
                        rule_name="incoherence_horizon_robert_tsla",
                        level="attention",
                        message=(
                            f"Incohérence majeure identifiée : Robert (59 ans, horizon 3-5 ans, mandat de préservation du capital vers la retraite) "
                            f"demande {weight_label} dans Tesla (TSLA). TSLA affiche une volatilité historique de {tsla_vol:.2%} "
                            f"et une perte maximale de {tsla_dd:.2%}. Intégrer cette position porterait la volatilité du portefeuille "
                            f"à {req_vol:.2%} (dépassant le plafond cible de 6.00%). "
                            f"Alternative constructive : un satellite plafonné à 3.0% (volatilité {alt_vol:.2%}) permet une exposition "
                            f"à la croissance sans compromettre le socle obligataire défensif."
                        ),
                        details={
                            "ticker": "TSLA",
                            "requested_weight": weight_val,
                            "capped_weight": 0.03,
                            "tsla_volatility": tsla_vol,
                            "tsla_max_dd": tsla_dd,
                            "requested_portfolio_vol": req_vol,
                            "capped_alternative_vol": alt_vol,
                            "is_weight_hypothesized": req_pos.is_hypothesized,
                        },
                        suggested_action="Plafonner TSLA à 3.0% (satellite) dans le volet actions plutôt que l'allocation demandée.",
                        evidence_ids=[e_asset_id, e_comp_id],
                    )
                )
                report.has_attention = True
                report.capped_alternatives["TSLA"] = 0.03

            # --- CASE 1b: Robert + Crypto (Strict Prohibition) ---
            elif persona.id == "robert" and ticker in ("BTC-USD", "ETH-USD") and not handled_crypto:
                handled_crypto = True
                eval_data = eval_map.get(ticker, {})
                e_asset_id = eval_data.get("asset_evidence_id", "E2")
                report.alerts.append(
                    GovernanceAlert(
                        rule_name="crypto_prohibition_robert",
                        level="bloquant",
                        message=(
                            f"Interdiction absolue des crypto-actifs pour Robert : Robert (59 ans, horizon 3-5 ans vers la retraite, "
                            f"mandat de préservation du capital) demande une exposition en {ticker}. "
                            f"Les crypto-actifs affichent des pertes historiques sévères (>70%) et sont formellement exclus de sa politique d'investissement."
                        ),
                        details={"ticker": ticker, "requested_weight": raw_weight, "cap": 0.0},
                        suggested_action="Refus strict : bloquer toute allocation en cryptomonnaies pour Robert (poids 0.0%).",
                        evidence_ids=[e_asset_id] if e_asset_id else [],
                    )
                )
                report.has_blocking = True
                report.passed = False

            # --- CASE 2: Amira + Crypto (Concentration Risk Alert, Single Consolidated Alert) ---
            elif persona.id == "amira" and ticker in ("BTC-USD", "ETH-USD") and not handled_crypto:
                handled_crypto = True
                total_crypto = sum(p.weight for p in crypto_reqs if p.weight is not None)
                if total_crypto == 0:
                    total_crypto = parsed_request.total_requested_weight or 1.00

                crypto_cap = persona.constraints.crypto_cap  # 0.10
                if total_crypto > crypto_cap:
                    e_comp_ids = [eval_map[p.ticker]["comparison_evidence_id"] for p in crypto_reqs if p.ticker in eval_map]
                    positions_str = ", ".join([f"{p.weight:.1%} en {p.ticker}" for p in crypto_reqs if p.weight is not None])
                    split_note = " (répartition équipondérée 50/50)" if any(p.is_hypothesized for p in crypto_reqs) else ""

                    report.alerts.append(
                        GovernanceAlert(
                            rule_name="concentration_crypto_amira",
                            level="attention",
                            message=(
                                f"Alerte de concentration excessive : Amira demande {total_crypto:.1%} dans les crypto-actifs "
                                f"({positions_str}{split_note}). Bien qu'Amira ait une tolérance au risque élevée, concentrer "
                                f"le capital au-delà du plafond de {crypto_cap:.1%} viole le principe fondamental de diversification "
                                f"et expose à des pertes maximales historiques sévères (-73.31% sur BTC-USD, -77.19% sur ETH-USD). "
                                f"Alternative constructive : maintenir la poche crypto plafonnée à {crypto_cap:.1%} pour participer à la croissance "
                                f"tout en conservant la robustesse du portefeuille."
                            ),
                            details={
                                "total_requested_crypto": total_crypto,
                                "cap": crypto_cap,
                                "positions": [p.model_dump() for p in crypto_reqs],
                            },
                            suggested_action=f"Maintenir l'exposition crypto totale plafonnée à {crypto_cap:.1%}.",
                            evidence_ids=e_comp_ids if e_comp_ids else [],
                        )
                    )
                    report.has_attention = True

            # --- CASE 3: Mateo + ENB (ESG Tension with Fossil Fuel Yield) ---
            elif persona.id == "mateo" and ticker == "ENB.TO":
                report.alerts.append(
                    GovernanceAlert(
                        rule_name="tension_esg_mateo_enbridge",
                        level="attention",
                        message=(
                            "Tension d'objectifs ESG : Mateo demande l'intégration d'Enbridge (ENB.TO) pour son rendement de dividende. "
                            "Or, Enbridge est un exploitant majeur d'infrastructures de transport d'hydrocarbures et de sables bitumineux, "
                            "ce qui entre en contradiction directe avec les préférences d'exclusion ESG de Mateo. "
                            "Alternative constructive : privilégier des titres de dividendes de qualité à plus faible intensité carbone "
                            "(ex: Fortis FTS.TO, banques canadiennes) ou le FNB ESG (ESGV) pour maintenir la conformité éthique."
                        ),
                        details={"ticker": "ENB.TO", "requested_weight": raw_weight, "esg_status": "provisional_exclusion"},
                        suggested_action="Exclure ENB.TO au profit d'actifs de dividende conformes aux critères ESG (ex: FTS.TO, ESGV).",
                    )
                )
                report.has_attention = True

        # --- CASE 4: Out-of-Scope / Unknown Assets ---
        if parsed_request.out_of_scope:
            report.alerts.append(
                GovernanceAlert(
                    rule_name="requete_hors_mandat",
                    level="attention",
                    message=(
                        "Demande hors mandat réglementaire ou instruments non supportés : la requête mentionne des instruments spéculatifs "
                        "(options, effet de levier ou actifs non cotés). Dans le cadre d'une simulation éducative de courtage direct, "
                        "seuls les 31 actifs liquides de l'univers de référence sans effet de levier sont analysés."
                    ),
                    details={"unknown_entities": parsed_request.unknown_entities},
                    suggested_action="Restreindre l'analyse aux actions, FNB et cryptomonnaies de l'univers officiel.",
                )
            )
            report.has_attention = True

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

        try:
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
