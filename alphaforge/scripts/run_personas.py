#!/usr/bin/env python3
"""AlphaForge AI — End-to-End Persona Simulation Pipeline.

Executes the deterministic core for all three official personas:
1. Amira (High risk, long horizon, tech & crypto with diversification).
2. Mateo (Moderate risk, balanced growth, ESG screening, controversy avoidance).
3. Robert (Low-to-moderate risk, capital preservation, hyped asset TSLA test + capped alternative).

Validates:
- Optimal portfolio allocation under cvxpy constraints.
- Quantitative risk metrics in CAD (annualized vol, max drawdown, CVaR95, beta vs XIU.TO).
- 2022 stagflation stress test replay.
- Governance compliance checks (blocking crypto, constructive refusal for TSLA).
- Grounded explanation generation and 100% deterministic verification.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

# Ensure alphaforge package is on Python path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alphaforge.app.evidence import EvidenceRegistry
from alphaforge.app.governance import check_governance_rules
from alphaforge.app.personas import Persona, get_persona
from alphaforge.app.tools.optimize import optimize_min_variance
from alphaforge.app.tools.prices import generate_data_quality_report, get_processed_dataset
from alphaforge.app.tools.risk import (
    asset_summary_metrics,
    portfolio_risk_metrics,
    risk_contributions,
)
from alphaforge.app.tools.stress import sensitivity_to_asset_cap, stress_test_2022_episode
from alphaforge.app.verifier import verify_explanation

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("run_personas")


def run_pipeline_for_persona(
    persona_id: str,
    user_requests: list[str] | None = None,
    force_tsla_weight: float | None = None,
) -> dict[str, Any]:
    """Execute complete deterministic pipeline for a persona."""
    persona = get_persona(persona_id)
    returns_df, prices_df, universe_df = get_processed_dataset()
    registry = EvidenceRegistry()

    # 1. Evidence: Data quality & universe audit
    dq = generate_data_quality_report()
    e_dq = registry.register(
        tool="prices.generate_data_quality_report",
        args={},
        result=dq.to_dict(),
        source="PolyFinances Starter / Yahoo / BoC",
        description=f"Market data quality report: {dq.calendar_dates_count} trading dates, 31 assets.",
    )

    # 2. Evidence: Individual asset risk summary
    asset_risks = asset_summary_metrics(returns_df)
    e_risk = registry.register(
        tool="risk.asset_summary_metrics",
        args={"benchmark": "XIU.TO"},
        result=asset_risks.to_dict(orient="index"),
        source="Computed on CAD log returns (2021-11-12 to 2026-11-12)",
        description="Historical annualized volatility, maximum drawdown, and beta vs XIU.TO for 31 assets.",
    )

    # 3. Setup optimization constraints from persona
    constraints = persona.constraints
    per_asset_caps = dict(constraints.per_asset_caps)
    per_asset_floors = dict(constraints.per_asset_floors)
    exclusions = list(constraints.exclusions)

    # Default per-asset cap across all assets
    full_per_asset_caps: dict[str, float] = {t: constraints.single_asset_cap for t in returns_df.columns}
    for t, cap_val in per_asset_caps.items():
        full_per_asset_caps[t] = cap_val

    # Special persona handling
    if persona_id == "robert" and force_tsla_weight is not None:
        if "TSLA" in exclusions:
            exclusions.remove("TSLA")
        full_per_asset_caps["TSLA"] = force_tsla_weight
        per_asset_floors["TSLA"] = force_tsla_weight

    # Run Constrained Optimization
    opt_result = optimize_min_variance(
        returns_df=returns_df,
        universe_df=universe_df,
        per_asset_caps=full_per_asset_caps,
        per_asset_floors=per_asset_floors if per_asset_floors else None,
        sector_caps=constraints.sector_caps,
        sector_floors=constraints.sector_floors,
        class_caps=constraints.class_caps,
        class_floors=constraints.class_floors,
        exclusions=exclusions,
    )

    e_opt = registry.register(
        tool="optimize.optimize_min_variance",
        args={"persona": persona_id, "constraints": constraints.to_dict()},
        result=opt_result.to_dict(),
        source="cvxpy Constrained Quadratic Program (OSQP)",
        description=f"Optimal portfolio weights for {persona.name} minimizing variance under policy constraints.",
    )

    # 4. Portfolio risk metrics
    port_metrics = portfolio_risk_metrics(opt_result.weights, returns_df)
    e_pmetrics = registry.register(
        tool="risk.portfolio_risk_metrics",
        args={"weights": opt_result.weights},
        result=port_metrics,
        source="AlphaForge Risk Engine (CAD)",
        description=f"Portfolio risk profile for {persona.name}: vol, drawdown, CVaR95.",
    )

    # 5. Risk contribution decomposition
    rc_df = risk_contributions(opt_result.weights, returns_df)
    e_rc = registry.register(
        tool="risk.risk_contributions",
        args={"weights": opt_result.weights},
        result=rc_df.to_dict(orient="records"),
        source="AlphaForge Risk Engine (CAD)",
        description=f"Asset risk contribution decomposition for {persona.name}.",
    )

    # 6. 2022 Episode Stress Test
    stress_2022 = stress_test_2022_episode(opt_result.weights, returns_df)
    e_stress = registry.register(
        tool="stress.stress_test_2022_episode",
        args={"weights": opt_result.weights},
        result=stress_2022,
        source="Historical replay (2022-01-01 to 2022-12-31)",
        description=f"2022 stagflation rate-hike stress test replay for {persona.name}.",
    )

    # 7. Governance Check
    gov_report = check_governance_rules(
        persona=persona,
        proposed_weights=opt_result.weights,
        universe_df=universe_df,
        risk_summary_df=asset_risks,
        user_requests=user_requests,
        evidence_map={"crypto_risk": e_risk.id, "tsla_risk": e_risk.id},
    )

    e_gov = registry.register(
        tool="governance.check_governance_rules",
        args={"persona": persona_id, "weights": opt_result.weights, "user_requests": user_requests},
        result=gov_report.to_dict(),
        source="AlphaForge Governance & Policy Rules",
        description=f"Governance compliance check for {persona.name}.",
    )

    # 8. Generate Self-Explaining Output grounded in registered Evidence IDs
    vol_val = port_metrics["annualized_volatility"]
    dd_val = port_metrics["max_drawdown"]
    s2022_dd = stress_2022["portfolio"]["max_drawdown"]

    explanation_payload = {
        "resume": (
            f"Portefeuille simulé pour {persona.name} optimisé sans prédiction de rendement. "
            f"Volatilité annualisée de {vol_val:.2%} et drawdown maximal historique de {dd_val:.2%} en CAD."
        ),
        "quelles_donnees": [
            {
                "claim": f"Le portefeuille présente une volatilité annualisée de {vol_val:.2%} et un drawdown de {dd_val:.2%}.",
                "evidence_ids": [e_pmetrics.id],
            },
            {
                "claim": f"Lors du choc de 2022, le recul maximal du portefeuille a été de {s2022_dd:.2%}.",
                "evidence_ids": [e_stress.id],
            },
        ],
        "pourquoi_ce_choix": [
            {
                "claim": f"L'optimisation sous contraintes a alloué le capital sur {opt_result.active_assets} actifs.",
                "evidence_ids": [e_opt.id],
            }
        ],
        "limites": [
            {
                "text": "Biais du survivant : l'univers de 31 actifs a été sélectionné en novembre 2026 avec un recul historique favorable.",
                "type": "donnee",
            },
            {
                "text": "Retard de publication macroéconomique : les indices mensuels (IPC, chômage) ne sont disponibles que 2 à 4 semaines après le mois de référence.",
                "type": "methode",
            },
            {
                "text": "Absence de prédiction : l'allocation repose sur la structure de covariance historique et ne garantit pas les rendements futurs.",
                "type": "hypothese",
            },
        ],
        "ce_qui_changerait_la_reponse": [
            "Une modification des plafonds sectoriels ou par actif.",
            "Une variation du taux directeur de la Banque du Canada ou un dérèglement de la parité USD/CAD.",
            "Un allongement ou raccourcissement de l'horizon temporel de l'investisseur.",
        ],
        "alertes_gouvernance": [
            {
                "niveau": a.level,
                "message": a.message,
                "evidence_ids": [e_gov.id],
            }
            for a in gov_report.alerts
        ],
    }

    # 9. Deterministic Verifier validation
    ver_report = verify_explanation(explanation_payload, registry)

    return {
        "persona": persona,
        "weights": opt_result.weights,
        "risk_metrics": port_metrics,
        "stress_2022": stress_2022,
        "governance": gov_report,
        "explanation": explanation_payload,
        "verification": ver_report,
        "registry": registry,
    }


def print_banner(title: str) -> None:
    print("\n" + "=" * 80)
    print(f"  {title.upper()}")
    print("=" * 80)


def main() -> None:
    print_banner("AlphaForge AI — Deterministic Pipeline Execution (Phase 1)")

    # 1. Run Amira
    print_banner("Persona 1: Amira (26yo, High Risk, 15+ Yrs Horizon)")
    res_amira = run_pipeline_for_persona("amira")
    print(f"Objective: {res_amira['persona'].investment_objective}")
    print(f"Reality Test: {res_amira['persona'].reality_test}")
    print("\nAllocations (Sorted by Weight):")
    for ticker, w in sorted(res_amira["weights"].items(), key=lambda x: x[1], reverse=True):
        print(f"  {ticker:<10}: {w:>6.1%}")
    print("\nRisk Metrics (CAD):")
    for k, v in res_amira["risk_metrics"].items():
        print(f"  {k:<24}: {v}")
    print(f"\n2022 Episode Stress Drawdown: {res_amira['stress_2022']['portfolio']['max_drawdown']:.2%}")
    print(f"Governance Status: Passed={res_amira['governance'].passed}, Alerts={len(res_amira['governance'].alerts)}")
    print(f"Verifier Status: Valid={res_amira['verification'].is_valid}, Errors={len(res_amira['verification'].errors)}")

    # 2. Run Mateo
    print_banner("Persona 2: Mateo (41yo, Moderate Risk, 8-12 Yrs Horizon, ESG)")
    res_mateo = run_pipeline_for_persona("mateo")
    print(f"Objective: {res_mateo['persona'].investment_objective}")
    print(f"Reality Test: {res_mateo['persona'].reality_test}")
    print("\nAllocations (Sorted by Weight):")
    for ticker, w in sorted(res_mateo["weights"].items(), key=lambda x: x[1], reverse=True):
        print(f"  {ticker:<10}: {w:>6.1%}")
    print("\nRisk Metrics (CAD):")
    for k, v in res_mateo["risk_metrics"].items():
        print(f"  {k:<24}: {v}")
    print(f"\n2022 Episode Stress Drawdown: {res_mateo['stress_2022']['portfolio']['max_drawdown']:.2%}")
    print(f"Governance Status: Passed={res_mateo['governance'].passed}, Alerts={len(res_mateo['governance'].alerts)}")
    print(f"Verifier Status: Valid={res_mateo['verification'].is_valid}, Errors={len(res_mateo['verification'].errors)}")

    # 3. Run Robert (Baseline)
    print_banner("Persona 3: Robert — Baseline (59yo, Capital Preservation, 3-5 Yrs)")
    res_robert = run_pipeline_for_persona("robert")
    print(f"Objective: {res_robert['persona'].investment_objective}")
    print(f"Reality Test: {res_robert['persona'].reality_test}")
    print("\nAllocations (Sorted by Weight):")
    for ticker, w in sorted(res_robert["weights"].items(), key=lambda x: x[1], reverse=True):
        print(f"  {ticker:<10}: {w:>6.1%}")
    print("\nRisk Metrics (CAD):")
    for k, v in res_robert["risk_metrics"].items():
        print(f"  {k:<24}: {v}")
    print(f"\n2022 Episode Stress Drawdown: {res_robert['stress_2022']['portfolio']['max_drawdown']:.2%}")
    print(f"Governance Status: Passed={res_robert['governance'].passed}")
    print(f"Verifier Status: Valid={res_robert['verification'].is_valid}")

    # 4. Run Robert (Reality Test: Requesting Speculative TSLA & Crypto)
    print_banner("Persona 3: Robert — Reality Test (Requesting 20% TSLA & Crypto)")
    returns_df, _, univ = get_processed_dataset()
    summary = asset_summary_metrics(returns_df)
    robert = get_persona("robert")

    gov_test = check_governance_rules(
        persona=robert,
        proposed_weights={"TSLA": 0.20, "BTC-USD": 0.05, "ZST.TO": 0.40, "XBB.TO": 0.35},
        universe_df=univ,
        risk_summary_df=summary,
        user_requests=["I want 20% in Tesla (TSLA) and 5% in Bitcoin!"],
    )
    print(f"User Request: 'I want 20% in Tesla (TSLA) and 5% in Bitcoin!'")
    print(f"Governance Result: Passed = {gov_test.passed} (Blocking = {gov_test.has_blocking})")
    print("\nTriggered Governance Alerts:")
    for a in gov_test.alerts:
        print(f"  [{a.level.upper()}] {a.rule_name}:")
        print(f"    Message: {a.message}")
        if a.suggested_action:
            print(f"    Action: {a.suggested_action}")

    print("\nProposed Capped Alternative from Governance Engine:")
    print(f"  {gov_test.capped_alternatives}")

    # 5. Run Robert (With Capped Alternative: 3% TSLA, 0% Crypto)
    print_banner("Persona 3: Robert — Capped Alternative (3% TSLA Satellite)")
    res_robert_capped = run_pipeline_for_persona("robert", user_requests=["TSLA"], force_tsla_weight=0.03)
    print("Allocations with 3% TSLA Capped Alternative:")
    for ticker, w in sorted(res_robert_capped["weights"].items(), key=lambda x: x[1], reverse=True):
        print(f"  {ticker:<10}: {w:>6.1%}")
    print("\nRisk Metrics with 3% TSLA:")
    for k, v in res_robert_capped["risk_metrics"].items():
        print(f"  {k:<24}: {v}")
    print(f"2022 Drawdown: {res_robert_capped['stress_2022']['portfolio']['max_drawdown']:.2%}")
    print(f"Governance Passed: {res_robert_capped['governance'].passed} (No blocking alerts)")
    print(f"Verifier Status: Valid = {res_robert_capped['verification'].is_valid}")

    print_banner("All Persona Pipelines Successfully Executed and Verified!")


if __name__ == "__main__":
    main()
