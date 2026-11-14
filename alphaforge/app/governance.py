"""Governance and policy compliance engine for AlphaForge AI.

Implements rule-based controls:
- Robert + TSLA: Incoherence alert between short horizon and high-volatility stock + capped alternative proposal.
- Robert + Crypto: Blocking rule (crypto strictly forbidden for near-retirement capital preservation).
- Mateo + ESG/Speculation: Warnings on high-carbon energy and speculative assets.
- Amira + Concentration: Guardrails to enforce diversification despite high risk tolerance.
- Regulatory boundary: Enforces simulation-only disclaimers.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import pandas as pd

from alphaforge.app.personas import Persona

logger = logging.getLogger(__name__)

AlertLevel = Literal["info", "attention", "bloquant"]


@dataclass
class GovernanceAlert:
    rule_name: str
    level: AlertLevel
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    suggested_action: str | None = None
    evidence_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GovernanceReport:
    persona_id: str
    passed: bool
    alerts: list[GovernanceAlert] = field(default_factory=list)
    has_blocking: bool = False
    has_attention: bool = False
    capped_alternatives: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "persona_id": self.persona_id,
            "passed": self.passed,
            "has_blocking": self.has_blocking,
            "has_attention": self.has_attention,
            "alerts": [a.to_dict() for a in self.alerts],
            "capped_alternatives": self.capped_alternatives,
        }


def check_governance_rules(
    persona: Persona,
    proposed_weights: dict[str, float] | pd.Series,
    universe_df: pd.DataFrame,
    risk_summary_df: pd.DataFrame | None = None,
    user_requests: list[str] | None = None,
    evidence_map: dict[str, str] | None = None,
) -> GovernanceReport:
    """Evaluate proposed portfolio allocation and user requests against governance policies."""
    weights = pd.Series(proposed_weights) if isinstance(proposed_weights, dict) else proposed_weights
    evidence_map = evidence_map or {}
    alerts: list[GovernanceAlert] = []
    capped_alts: dict[str, float] = {}

    class_map = dict(zip(universe_df["ticker"], universe_df["asset_class"]))
    sector_map = dict(zip(universe_df["ticker"], universe_df["sector"]))

    # Helper: get weight by class
    def get_class_weight(cls_name: str) -> float:
        tickers = [t for t in weights.index if class_map.get(t) == cls_name]
        return float(weights[tickers].sum()) if tickers else 0.0

    # Helper: get weight by sector
    def get_sector_weight(sec_name: str) -> float:
        tickers = [t for t in weights.index if sector_map.get(t) == sec_name]
        return float(weights[tickers].sum()) if tickers else 0.0

    crypto_weight = get_class_weight("crypto")
    bond_weight = get_class_weight("etf_bond")
    tech_weight = get_sector_weight("Information Technology")
    energy_weight = get_sector_weight("Energy")

    user_reqs_upper = [r.upper() for r in (user_requests or [])]

    # --- RULE 1: Crypto Policy ---
    if persona.id == "robert":
        has_crypto_requested = any(
            any(k in r for k in ["BTC", "ETH", "CRYPTO", "BITCOIN", "ETHER"])
            for r in user_reqs_upper
        )
        if crypto_weight > 0.001 or has_crypto_requested:
            alerts.append(
                GovernanceAlert(
                    rule_name="crypto_prohibition_robert",
                    level="bloquant",
                    message=(
                        "Crypto-assets (BTC-USD, ETH-USD) are strictly prohibited for Robert. "
                        "Robert is 59 with a 3-5 year horizon approaching retirement; volatile cryptoassets with historical drawdowns >70% "
                        "violate his capital preservation mandate."
                    ),
                    details={"crypto_weight": round(crypto_weight, 4), "requested": has_crypto_requested},
                    suggested_action="Block crypto allocation completely (set weight to 0.0%).",
                    evidence_ids=[evidence_map.get("crypto_risk", "E_RISK")] if "crypto_risk" in evidence_map else [],
                )
            )
    elif persona.id == "mateo":
        if crypto_weight > 0.001:
            alerts.append(
                GovernanceAlert(
                    rule_name="speculative_crypto_warning_mateo",
                    level="attention",
                    message=(
                        f"Crypto-asset allocation ({crypto_weight:.1%}) detected. "
                        "Mateo's profile explicitly notes little interest in highly speculative investments."
                    ),
                    details={"crypto_weight": round(crypto_weight, 4)},
                    suggested_action="Exclude crypto assets from Mateo's balanced portfolio.",
                )
            )
    elif persona.id == "amira":
        if crypto_weight > persona.constraints.crypto_cap + 0.001:
            alerts.append(
                GovernanceAlert(
                    rule_name="crypto_cap_amira",
                    level="attention",
                    message=(
                        f"Crypto allocation ({crypto_weight:.1%}) exceeds Amira's diversification cap of "
                        f"{persona.constraints.crypto_cap:.1%}."
                    ),
                    details={"crypto_weight": round(crypto_weight, 4), "cap": persona.constraints.crypto_cap},
                    suggested_action=f"Reduce total crypto to <= {persona.constraints.crypto_cap:.1%}.",
                )
            )

    # --- RULE 2: Robert Hyped Asset Temptation (TSLA / High-Vol Speculative Equities) ---
    if persona.id == "robert":
        tsla_weight = float(weights.get("TSLA", 0.0))
        tsla_requested = any("TSLA" in r or "TESLA" in r for r in user_reqs_upper)

        if tsla_requested or tsla_weight > 0.001:
            tsla_vol = None
            tsla_dd = None
            if risk_summary_df is not None and "TSLA" in risk_summary_df.index:
                tsla_vol = float(risk_summary_df.loc["TSLA", "annualized_volatility"])
                tsla_dd = float(risk_summary_df.loc["TSLA", "max_drawdown"])

            vol_str = f"{tsla_vol:.1%}" if tsla_vol else "~58%"
            dd_str = f"{tsla_dd:.1%}" if tsla_dd else "~-71%"

            if tsla_requested or tsla_weight > 0.03:
                alerts.append(
                    GovernanceAlert(
                        rule_name="robert_tsla_incoherence",
                        level="attention",
                        message=(
                            f"Alerte d'incohérence d'adéquation : Robert a demandé l'intégration de Tesla (TSLA). "
                            f"L'horizon de 3 à 5 ans et le mandat de préservation du capital de Robert vers la retraite entrent en conflit "
                            f"avec la volatilité historique de TSLA ({vol_str}) et sa perte maximale de {dd_str}."
                        ),
                        details={"tsla_weight": round(tsla_weight, 4), "tsla_vol": tsla_vol, "tsla_drawdown": tsla_dd},
                        suggested_action="Refus constructif : plafonner TSLA à un satellite de 3.0% maximum pour préserver le capital.",
                        evidence_ids=[evidence_map.get("tsla_risk", "E_TSLA")] if "tsla_risk" in evidence_map else [],
                    )
                )
                capped_alts["TSLA"] = 0.03
            else:
                alerts.append(
                    GovernanceAlert(
                        rule_name="robert_tsla_capped_satellite",
                        level="info",
                        message=(
                            f"Alignement constructif : TSLA est maintenu à un poids satellite prudent de {tsla_weight:.1%} "
                            f"(<= 3.0%), offrant une exposition contrôlée sans compromettre le capital retraite."
                        ),
                        details={"tsla_weight": round(tsla_weight, 4)},
                    )
                )

    # --- RULE 3: Bond Floor / Capital Preservation Check ---
    if persona.constraints.bond_floor > 0:
        if bond_weight < persona.constraints.bond_floor - 0.01:
            severity: AlertLevel = "bloquant" if persona.id == "robert" else "attention"
            alerts.append(
                GovernanceAlert(
                    rule_name="bond_floor_deficiency",
                    level=severity,
                    message=(
                        f"Fixed income allocation ({bond_weight:.1%}) is below the required minimum floor of "
                        f"{persona.constraints.bond_floor:.1%} for {persona.name}."
                    ),
                    details={"bond_weight": round(bond_weight, 4), "floor": persona.constraints.bond_floor},
                    suggested_action=f"Increase bond ETFs (e.g., ZST.TO, XBB.TO, AGG) to at least {persona.constraints.bond_floor:.1%}.",
                )
            )

    # --- RULE 4: Sector Concentration & ESG Checks ---
    if persona.id == "amira" and tech_weight > 0.401:
        alerts.append(
            GovernanceAlert(
                rule_name="tech_overconcentration_amira",
                level="attention",
                message=(
                    f"Technology sector weight ({tech_weight:.1%}) exceeds the 40% cap. "
                    "Amira explicitly requested diversification beyond technology."
                ),
                details={"tech_weight": round(tech_weight, 4), "cap": 0.40},
                suggested_action="Reallocate excess tech exposure into diversified broad-market equities or non-tech growth.",
            )
        )

    if persona.id == "mateo":
        # Provisional ESG screening alert (per Datathon Case & GitHub issue #4)
        alerts.append(
            GovernanceAlert(
                rule_name="provisional_esg_screening_mateo",
                level="info",
                message=(
                    "Provisional ESG Screening Notice: Oil sands, pipelines, and fossil fuel assets (CNQ.TO, ENB.TO, XOM) "
                    "are excluded based on provisional team assumptions (source: 'hypothese_equipe — à remplacer par source ESG'; ref GitHub issue #4). "
                    "Vanguard ESG U.S. Stock ETF (ESGV) is utilized as the primary ESG-screened equity vehicle."
                ),
                details={
                    "provisional_exclusions": ["CNQ.TO", "ENB.TO", "XOM"],
                    "source": "hypothese_equipe — à remplacer par source ESG",
                    "issue_reference": "GitHub issue #4",
                    "esg_core_vehicle": "ESGV",
                },
            )
        )

        fossil_present = [t for t in ["CNQ.TO", "ENB.TO", "XOM"] if weights.get(t, 0.0) > 0.001]
        if fossil_present:
            alerts.append(
                GovernanceAlert(
                    rule_name="fossil_exclusion_breach_mateo",
                    level="attention",
                    message=(
                        f"Provisional ESG Warning: Fossil fuel assets {fossil_present} detected in Mateo's portfolio. "
                        "Mateo explicitly requests avoiding companies involved in significant environmental controversies."
                    ),
                    details={"fossil_assets": fossil_present},
                    suggested_action="Exclude fossil fuel assets (CNQ.TO, ENB.TO, XOM) from portfolio.",
                )
            )

        if energy_weight > 0.051:
            alerts.append(
                GovernanceAlert(
                    rule_name="energy_esg_screening_mateo",
                    level="attention",
                    message=(
                        f"Energy sector weight ({energy_weight:.1%}) exceeds Mateo's 5% ESG controversy limit. "
                        "Mateo seeks to avoid companies with major environmental/social controversy exposure."
                    ),
                    details={"energy_weight": round(energy_weight, 4), "cap": 0.05},
                    suggested_action="Screen out non-renewable oil & gas holdings in favor of ESG-screened equities (ESGV).",
                )
            )

    # --- RULE 5: Single Stock Concentration Policy ---
    for ticker, w_val in weights.items():
        # Only single individual corporate equities are subject to idiosyncratic single-stock cap.
        # Broad market ETFs (ESGV, XIU.TO, SPY, QQQ) and bond/commodity ETFs (ZST, XBB, AGG, GLD) are diversified pools.
        is_single_equity = class_map.get(ticker) == "equity"
        if is_single_equity and w_val > persona.constraints.single_asset_cap + 0.005:
            alerts.append(
                GovernanceAlert(
                    rule_name="single_asset_concentration",
                    level="attention",
                    message=(
                        f"Asset '{ticker}' weight ({w_val:.1%}) exceeds the single asset limit of "
                        f"{persona.constraints.single_asset_cap:.1%}."
                    ),
                    details={"ticker": ticker, "weight": round(float(w_val), 4), "cap": persona.constraints.single_asset_cap},
                    suggested_action=f"Trim {ticker} to <= {persona.constraints.single_asset_cap:.1%}.",
                )
            )

    # --- RULE 6: Incoherent Profile / Horizon Adequation ---
    if persona.age >= 65 and persona.risk_profile == "high" and (persona.horizon_years_max <= 3 or "retraite" in persona.investment_objective.lower() or "liquidi" in persona.investment_objective.lower()):
        alerts.append(
            GovernanceAlert(
                rule_name="incoherence_profil_age_horizon",
                level="attention",
                message=(
                    f"Incohérence majeure de profil : investisseur âgé de {persona.age} ans avec un horizon court "
                    f"({persona.horizon_years_max} ans) demandant un profil de risque spéculatif élevé. "
                    "Un tel profil viole les principes de convenance et d'adéquation (mandat de préservation du capital prioritaire)."
                ),
                details={"age": persona.age, "horizon_years_max": persona.horizon_years_max, "risk_profile": persona.risk_profile},
                suggested_action="Requalifier le profil de risque vers prudent ou équilibré et relever le socle obligataire.",
            )
        )

    # --- RULE 7: Simulation Boundaries (Always active) ---
    alerts.append(
        GovernanceAlert(
            rule_name="simulation_boundary_notice",
            level="info",
            message=(
                "Mandatory Boundary: Simulation only. This output is an educational decision-support aid. "
                "No live transactions are executed and no personalized financial advice is provided."
            ),
        )
    )

    has_bloquant = any(a.level == "bloquant" for a in alerts)
    has_att = any(a.level == "attention" for a in alerts)
    passed = not has_bloquant

    return GovernanceReport(
        persona_id=persona.id,
        passed=passed,
        alerts=alerts,
        has_blocking=has_bloquant,
        has_attention=has_att,
        capped_alternatives=capped_alts,
    )
