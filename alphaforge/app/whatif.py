"""What-if simulation and persona comparison engine for AlphaForge AI.

Complies strictly with BNCD Case & Architecture Guidelines:
- Purely deterministic re-optimization (no LLM / Bedrock calls, sub-second latency).
- Sliders: crypto cap, volatility target / horizon, single-asset cap.
- Produces re-optimized allocation + structured diff table vs baseline (weights, vol, max DD, 2022 stress).
- Systematically registers evidence into EvidenceRegistry with verified [E#] tags.
- Explains the quantitative impact in 1-2 deterministic sentences (no LLM) referencing evidence tags.
- Provides multi-asset 2022 stagflation stress curve overlay generation for persona comparison.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from alphaforge.app.evidence import EvidenceRegistry
from alphaforge.app.governance import GovernanceReport, check_governance_rules
from alphaforge.app.personas import (
    Persona,
    StrategicSleeveConfig,
    get_persona,
)
from alphaforge.app.tools.optimize import (
    OptimizationResult,
    optimize_two_level_portfolio,
)
from alphaforge.app.tools.prices import get_processed_dataset
from alphaforge.app.tools.risk import (
    portfolio_returns,
    portfolio_risk_metrics,
)
from alphaforge.app.tools.stress import (
    EPISODE_2022_END,
    EPISODE_2022_START,
    stress_test_2022_episode,
)

logger = logging.getLogger(__name__)


@dataclass
class WhatIfParams:
    """Parameters for what-if sensitivity analysis."""

    crypto_cap: float | None = None
    single_asset_cap: float | None = None
    target_vol: float | None = None
    horizon_years: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WhatIfResult:
    """Structured output of what-if re-optimization."""

    persona_id: str
    persona_name: str
    params: WhatIfParams
    baseline_weights: dict[str, float]
    whatif_weights: dict[str, float]
    baseline_metrics: dict[str, Any]
    whatif_metrics: dict[str, Any]
    baseline_stress: dict[str, Any]
    whatif_stress: dict[str, Any]
    diff_table: list[dict[str, Any]]
    explanation: str
    evidence_ids: dict[str, str]
    evidence_records: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_whatif_sleeves(
    base_sleeves: list[StrategicSleeveConfig],
    crypto_cap: float | None = None,
    single_asset_cap: float | None = None,
    target_vol: float | None = None,
    horizon_years: int | None = None,
) -> list[StrategicSleeveConfig]:
    """Pure function adjusting strategic sleeves for what-if constraints.

    Guarantees:
    - Total sleeve target weight sums to 1.0.
    - Crypto sleeve dynamically created, resized, or eliminated according to crypto_cap.
    - Equity vs. bond ratio adjusted smoothly according to target_vol or horizon_years.
    - Single asset cap scaled into intra-sleeve caps with feasibility lower bounds.
    """
    sleeves = [copy.deepcopy(s) for s in base_sleeves]

    # 1. Gold / commodity buffer (default 5%)
    gold_sleeve = next((s for s in sleeves if s.name == "gold_cash"), None)
    w_gold = gold_sleeve.target_weight if gold_sleeve else 0.05

    # 2. Crypto allocation
    crypto_sleeve = next((s for s in sleeves if s.name == "crypto"), None)
    if crypto_cap is not None:
        w_crypto = max(0.0, min(0.30, float(crypto_cap)))
    else:
        w_crypto = crypto_sleeve.target_weight if crypto_sleeve else 0.0

    w_rem = round(1.0 - w_gold - w_crypto, 4)
    if w_rem <= 0.10:
        w_crypto = 0.25
        w_rem = round(1.0 - w_gold - w_crypto, 4)

    # 3. Equity vs. Bond allocation (derived from target vol or horizon)
    eq_sleeve = next((s for s in sleeves if s.name == "equity"), None)
    bond_sleeve = next((s for s in sleeves if s.name == "bonds"), None)

    if target_vol is not None:
        # Interpolate equity fraction between 4% (0.15) and 18% (0.95)
        f_eq = float(np.clip((target_vol - 0.035) / (0.18 - 0.035), 0.15, 0.95))
    elif horizon_years is not None:
        if horizon_years <= 3:
            f_eq = 0.20
        elif horizon_years <= 5:
            f_eq = 0.35
        elif horizon_years <= 8:
            f_eq = 0.50
        elif horizon_years <= 12:
            f_eq = 0.65
        else:
            f_eq = 0.85
    else:
        base_eq_w = eq_sleeve.target_weight if eq_sleeve else 0.60
        base_bd_w = bond_sleeve.target_weight if bond_sleeve else 0.35
        f_eq = base_eq_w / max(base_eq_w + base_bd_w, 0.01)

    w_eq = round(f_eq * w_rem, 4)
    w_bd = round(w_rem - w_eq, 4)

    out_sleeves: list[StrategicSleeveConfig] = []

    # Update equity sleeve
    if eq_sleeve:
        eq_sleeve.target_weight = w_eq
        eq_sleeve.weight_band = (
            round(max(0.05, w_eq - 0.05), 4),
            round(min(1.0, w_eq + 0.05), 4),
        )

        if single_asset_cap is not None and w_eq > 0.01:
            intra_cap = min(1.0, max(0.07, single_asset_cap / w_eq))
            eq_sleeve.single_asset_cap = intra_cap
            if isinstance(eq_sleeve.per_asset_caps, dict):
                eq_sleeve.per_asset_caps = {
                    t: min(c, intra_cap) for t, c in eq_sleeve.per_asset_caps.items()
                }
            else:
                eq_sleeve.per_asset_caps = intra_cap

            if isinstance(eq_sleeve.per_asset_floors, dict):
                eq_sleeve.per_asset_floors = {
                    t: min(f, intra_cap * 0.9)
                    for t, f in eq_sleeve.per_asset_floors.items()
                }

        out_sleeves.append(eq_sleeve)

    # Update bond sleeve
    if bond_sleeve:
        bond_sleeve.target_weight = w_bd
        bond_sleeve.weight_band = (
            round(max(0.0, w_bd - 0.05), 4),
            round(min(1.0, w_bd + 0.05), 4),
        )
        out_sleeves.append(bond_sleeve)

    # Update or add crypto sleeve
    if w_crypto > 0.001:
        if crypto_sleeve:
            crypto_sleeve.target_weight = w_crypto
            crypto_sleeve.weight_band = (
                round(max(0.0, w_crypto - 0.05), 4),
                round(min(1.0, w_crypto + 0.05), 4),
            )
            out_sleeves.append(crypto_sleeve)
        else:
            new_crypto = StrategicSleeveConfig(
                name="crypto",
                target_weight=w_crypto,
                weight_band=(
                    round(max(0.0, w_crypto - 0.05), 4),
                    round(min(1.0, w_crypto + 0.05), 4),
                ),
                asset_classes=["crypto"],
                fixed_allocations={"BTC-USD": 0.50, "ETH-USD": 0.50},
                rationale="Allocation simulation what-if crypto.",
            )
            out_sleeves.append(new_crypto)

    # Append gold sleeve
    if gold_sleeve:
        gold_sleeve.target_weight = w_gold
        out_sleeves.append(gold_sleeve)

    # Ensure exact 1.0 normalization
    tot = sum(s.target_weight for s in out_sleeves)
    if abs(tot - 1.0) > 1e-4 and out_sleeves:
        largest = max(out_sleeves, key=lambda s: s.target_weight)
        largest.target_weight = round(largest.target_weight + (1.0 - tot), 4)

    return out_sleeves


def compute_diff_table(
    baseline_metrics: dict[str, Any],
    whatif_metrics: dict[str, Any],
    baseline_stress: dict[str, Any],
    whatif_stress: dict[str, Any],
    baseline_weights: dict[str, float],
    whatif_weights: dict[str, float],
    evidence_ids: dict[str, str],
) -> list[dict[str, Any]]:
    """Build a structured comparative diff table between baseline and what-if.

    Each row contains:
    - category: Metric category (Risque, Stress 2022, Allocation)
    - item: Metric or Asset name
    - baseline: Formatted baseline value
    - whatif: Formatted what-if value
    - diff: Formatted delta
    - diff_val: Numeric delta for conditional styling
    - evidence_id: Grounded evidence tag (e.g. E10)
    """
    rows: list[dict[str, Any]] = []
    e_opt = evidence_ids.get("opt", "E_WHATIF_OPT")
    e_risk = evidence_ids.get("risk", "E_WHATIF_RISK")
    e_stress = evidence_ids.get("stress", "E_WHATIF_STRESS")

    # 1. Risk Metrics
    risk_metric_defs = [
        ("Volatilité annualisée (CAD)", "annualized_volatility", "pct", e_risk),
        ("Perte maximale historique (MDD)", "max_drawdown", "pct", e_risk),
        ("CVaR 95% (Expected Shortfall)", "cvar_95", "pct", e_risk),
        ("Rendement annualisé réalisé", "realized_annual_return", "pct", e_risk),
        ("Bêta vs XIU.TO", "beta_vs_benchmark", "float", e_risk),
        ("Nombre d'actifs actifs", "active_assets_count", "int", e_opt),
    ]

    for label, key, fmt, eid in risk_metric_defs:
        b_val = baseline_metrics.get(key)
        w_val = whatif_metrics.get(key)
        if b_val is None or w_val is None:
            continue

        diff_num = float(w_val) - float(b_val)
        if fmt == "pct":
            b_str = f"{float(b_val):.2%}"
            w_str = f"{float(w_val):.2%}"
            d_str = f"{diff_num:+.2%}"
        elif fmt == "int":
            b_str = f"{int(b_val)}"
            w_str = f"{int(w_val)}"
            d_str = f"{int(diff_num):+d}"
        else:
            b_str = f"{float(b_val):.4f}"
            w_str = f"{float(w_val):.4f}"
            d_str = f"{diff_num:+.4f}"

        rows.append(
            {
                "category": "Métrique de Risque",
                "item": label,
                "baseline": b_str,
                "whatif": w_str,
                "diff": d_str,
                "diff_val": diff_num,
                "evidence_id": eid,
            }
        )

    # 2. 2022 Stress Test Metrics
    b_p_stress = baseline_stress.get("portfolio", {})
    w_p_stress = whatif_stress.get("portfolio", {})

    stress_metric_defs = [
        ("Perte Max Choc Stagflation 2022", "max_drawdown", "pct", e_stress),
        ("Rendement Cumulé 2022", "cumulative_return", "pct", e_stress),
        ("Volatilité 2022", "annualized_volatility", "pct", e_stress),
    ]

    for label, key, fmt, eid in stress_metric_defs:
        b_val = b_p_stress.get(key)
        w_val = w_p_stress.get(key)
        if b_val is None or w_val is None:
            continue

        diff_num = float(w_val) - float(b_val)
        b_str = f"{float(b_val):.2%}"
        w_str = f"{float(w_val):.2%}"
        d_str = f"{diff_num:+.2%}"

        rows.append(
            {
                "category": "Stress Test 2022",
                "item": label,
                "baseline": b_str,
                "whatif": w_str,
                "diff": d_str,
                "diff_val": diff_num,
                "evidence_id": eid,
            }
        )

    # 3. Asset Weights Comparison
    all_tickers = sorted(set(list(baseline_weights.keys()) + list(whatif_weights.keys())))
    for tkr in all_tickers:
        b_w = baseline_weights.get(tkr, 0.0)
        w_w = whatif_weights.get(tkr, 0.0)
        diff_w = w_w - b_w
        if abs(diff_w) > 1e-4 or b_w > 0.005 or w_w > 0.005:
            rows.append(
                {
                    "category": "Allocation d'Actif",
                    "item": tkr,
                    "baseline": f"{b_w:.2%}",
                    "whatif": f"{w_w:.2%}",
                    "diff": f"{diff_w:+.2%}",
                    "diff_val": diff_w,
                    "evidence_id": e_opt,
                }
            )

    return rows


def generate_whatif_explanation(
    params: WhatIfParams,
    baseline_metrics: dict[str, Any],
    whatif_metrics: dict[str, Any],
    baseline_stress: dict[str, Any],
    whatif_stress: dict[str, Any],
    evidence_ids: dict[str, str],
) -> str:
    """Generate 1-2 deterministic French sentences explaining the quantitative impact.

    Strictly complies with the case guideline:
    - Zero hallucination (no LLM).
    - Exactly 1 to 2 sentences.
    - Every changed number tagged with its grounded Evidence ID.
    """
    e_param = evidence_ids.get("params", "E_PARAM")
    e_opt = evidence_ids.get("opt", "E_OPT")
    e_risk = evidence_ids.get("risk", "E_RISK")
    e_stress = evidence_ids.get("stress", "E_STRESS")

    b_vol = float(baseline_metrics.get("annualized_volatility", 0.0))
    w_vol = float(whatif_metrics.get("annualized_volatility", 0.0))
    diff_vol = w_vol - b_vol

    b_dd = float(baseline_stress.get("portfolio", {}).get("max_drawdown", 0.0))
    w_dd = float(whatif_stress.get("portfolio", {}).get("max_drawdown", 0.0))
    diff_dd = w_dd - b_dd

    n_assets = int(whatif_metrics.get("active_assets_count", 0))

    param_clauses = []
    if params.single_asset_cap is not None:
        param_clauses.append(f"du plafond par actif à **{params.single_asset_cap:.1%}** [{e_param}]")
    if params.crypto_cap is not None:
        param_clauses.append(f"du plafond crypto à **{params.crypto_cap:.1%}** [{e_param}]")
    if params.target_vol is not None:
        param_clauses.append(f"de la cible de volatilité à **{params.target_vol:.1%}** [{e_param}]")
    elif params.horizon_years is not None:
        param_clauses.append(f"de l'horizon à **{params.horizon_years} ans** [{e_param}]")

    param_text = "L'ajustement " + " et ".join(param_clauses) if param_clauses else "La recalibration des paramètres"

    # Sentence 1: Volatility & Allocation impact
    sentence1 = (
        f"{param_text} fait passer la volatilité annualisée de **{b_vol:.2%}** "
        f"à **{w_vol:.2%}** [{e_risk}] (écart de **{diff_vol:+.2%}** vs référence)."
    )

    # Sentence 2: 2022 Stress test and diversification
    sentence2 = (
        f"La perte maximale lors du choc stagflationniste 2022 s'établit à **{w_dd:.2%}** [{e_stress}] "
        f"(vs **{b_dd:.2%}** en référence, écart de **{diff_dd:+.2%}**), "
        f"avec un portefeuille réparti sur **{n_assets}** actifs certifiés [{e_opt}]."
    )

    return f"{sentence1} {sentence2}"


def run_whatif_analysis(
    persona_or_profile: str | Persona,
    capital: float = 100000.0,
    crypto_cap: float | None = None,
    single_asset_cap: float | None = None,
    target_vol: float | None = None,
    horizon_years: int | None = None,
    baseline_result: dict[str, Any] | None = None,
    registry: EvidenceRegistry | None = None,
) -> WhatIfResult:
    """Execute fast deterministic what-if analysis and register evidence.

    Args:
        persona_or_profile: Persona ID or Persona instance.
        capital: Simulated investment capital in CAD.
        crypto_cap: Slider crypto ceiling (e.g. 0.05 for 5%).
        single_asset_cap: Slider per-asset ceiling (e.g. 0.08 for 8%).
        target_vol: Slider target volatility (e.g. 0.08 for 8%).
        horizon_years: Optional slider investment horizon.
        baseline_result: Optional pre-computed baseline analysis dict.
        registry: Optional EvidenceRegistry instance.

    Returns:
        WhatIfResult containing new allocation, diff table, deterministic explanation, and evidence IDs.
    """
    # 1. Resolve Persona
    if isinstance(persona_or_profile, Persona):
        persona = persona_or_profile
    else:
        persona = get_persona(str(persona_or_profile).lower().strip())

    reg = registry if registry is not None else EvidenceRegistry()
    returns_cad, prices_cad, universe = get_processed_dataset()

    # 2. Resolve Baseline
    if baseline_result is not None:
        b_weights = baseline_result.get("allocation", {})
        b_metrics = baseline_result.get("metrics", {})
        b_stress = baseline_result.get("stress_test", {})
    else:
        base_opt = optimize_two_level_portfolio(
            returns_df=returns_cad,
            universe_df=universe,
            sleeves=persona.constraints.strategic_sleeves,
            target_vol_band=persona.constraints.target_vol_band,
        )
        b_weights = {t: round(float(w), 4) for t, w in base_opt.weights.items() if w > 0.001}
        b_metrics = portfolio_risk_metrics(b_weights, returns_cad)
        b_stress = stress_test_2022_episode(b_weights, returns_cad)

    params = WhatIfParams(
        crypto_cap=crypto_cap,
        single_asset_cap=single_asset_cap,
        target_vol=target_vol,
        horizon_years=horizon_years,
    )

    # 3. Register What-If Parameters as Evidence
    e_params = reg.register(
        tool="whatif_parameters",
        args={"persona": persona.id, **params.to_dict()},
        result=params.to_dict(),
        source="Curseurs interactifs du panneau What-If (interface utilisateur)",
        date_str="2026-11-14",
        currency="CAD",
        description=f"Paramètres de simulation What-If pour {persona.name}.",
        summary_metrics=params.to_dict(),
    )

    # 4. Re-run Deterministic Core
    whatif_sleeves = build_whatif_sleeves(
        base_sleeves=persona.constraints.strategic_sleeves,
        crypto_cap=crypto_cap,
        single_asset_cap=single_asset_cap,
        target_vol=target_vol,
        horizon_years=horizon_years,
    )

    target_band = (target_vol - 0.02, target_vol + 0.02) if target_vol else persona.constraints.target_vol_band

    w_opt = optimize_two_level_portfolio(
        returns_df=returns_cad,
        universe_df=universe,
        sleeves=whatif_sleeves,
        target_vol_band=target_band,
    )
    w_weights = {t: round(float(w), 4) for t, w in w_opt.weights.items() if w > 0.001}
    w_metrics = portfolio_risk_metrics(w_weights, returns_cad)
    w_stress = stress_test_2022_episode(w_weights, returns_cad)

    # 5. Register What-If Results as Evidence
    e_opt = reg.register(
        tool="whatif_strategic_optimization",
        args={"persona": persona.id, "active_sleeves": len(whatif_sleeves)},
        result={"weights": w_weights, "active_assets_count": len(w_weights), "solver_status": w_opt.solver_status},
        source="Solveur CVXPY (Quadratique sous contraintes What-If)",
        date_str="2026-11-14",
        currency="CAD",
        description=f"Allocation réoptimisée sous scénario What-If pour {persona.name}.",
        summary_metrics={"weights": w_weights, "active_assets_count": len(w_weights)},
    )

    e_risk = reg.register(
        tool="whatif_portfolio_risk",
        args={"assets_count": len(w_weights)},
        result=w_metrics,
        source="Moteur quantitatif AlphaForge CAD (sans modèle prédictif)",
        date_str="2026-11-14",
        currency="CAD",
        description=f"Métriques de risque réévaluées sous scénario What-If.",
        summary_metrics={
            "annualized_volatility": w_metrics.get("annualized_volatility"),
            "max_drawdown": w_metrics.get("max_drawdown"),
            "cvar_95": w_metrics.get("cvar_95"),
        },
    )

    e_stress = reg.register(
        tool="whatif_stress_test_2022",
        args={"weights_count": len(w_weights)},
        result=w_stress,
        source="Rejeu historique 2022 (Choc stagflation / hausse synchronisée des taux)",
        date_str="2026-11-14",
        currency="CAD",
        description=f"Choc stagflation 2022 sous allocation What-If.",
        summary_metrics={
            "max_drawdown_2022": w_stress.get("portfolio", {}).get("max_drawdown"),
            "cumulative_return_2022": w_stress.get("portfolio", {}).get("cumulative_return"),
        },
    )

    evidence_ids = {
        "params": e_params.id,
        "opt": e_opt.id,
        "risk": e_risk.id,
        "stress": e_stress.id,
    }

    # 6. Diff Table & Deterministic Explanation
    diff_table = compute_diff_table(
        baseline_metrics=b_metrics,
        whatif_metrics=w_metrics,
        baseline_stress=b_stress,
        whatif_stress=w_stress,
        baseline_weights=b_weights,
        whatif_weights=w_weights,
        evidence_ids=evidence_ids,
    )

    explanation = generate_whatif_explanation(
        params=params,
        baseline_metrics=b_metrics,
        whatif_metrics=w_metrics,
        baseline_stress=b_stress,
        whatif_stress=w_stress,
        evidence_ids=evidence_ids,
    )

    return WhatIfResult(
        persona_id=persona.id,
        persona_name=persona.name,
        params=params,
        baseline_weights=b_weights,
        whatif_weights=w_weights,
        baseline_metrics=b_metrics,
        whatif_metrics=w_metrics,
        baseline_stress=b_stress,
        whatif_stress=w_stress,
        diff_table=diff_table,
        explanation=explanation,
        evidence_ids=evidence_ids,
        evidence_records=reg.to_dict(),
    )


def compute_2022_stress_curve(
    portfolios: dict[str, dict[str, float]],
    returns_df: pd.DataFrame,
    start_date: str = EPISODE_2022_START,
    end_date: str = EPISODE_2022_END,
) -> pd.DataFrame:
    """Generate daily cumulative return curves across 2022 for multiple portfolios.

    Args:
        portfolios: Dict of portfolio_name -> weights dict.
        returns_df: Aligned CAD daily returns DataFrame.
        start_date: Start date of stress episode (default 2022-01-01).
        end_date: End date of stress episode (default 2022-12-31).

    Returns:
        DataFrame indexed by date containing cumulative returns (e.g. -0.12 for -12%)
        for each portfolio and standard benchmarks (XIU.TO, 60/40 CAD).
    """
    r_sub = returns_df.loc[start_date:end_date]
    if len(r_sub) == 0:
        raise ValueError(f"No return data in interval {start_date} to {end_date}")

    curves: dict[str, pd.Series] = {}

    for name, weights in portfolios.items():
        p_ret = portfolio_returns(weights, r_sub)
        curves[name] = np.exp(p_ret.cumsum()) - 1.0

    # Include TSX benchmark
    if "XIU.TO" in r_sub.columns:
        curves["TSX Composite (XIU.TO)"] = np.exp(r_sub["XIU.TO"].cumsum()) - 1.0

    # Include standard 60/40 benchmark
    if "XIU.TO" in r_sub.columns and "XBB.TO" in r_sub.columns:
        b60_40 = 0.6 * r_sub["XIU.TO"] + 0.4 * r_sub["XBB.TO"]
        curves["Portefeuille 60/40 CAD"] = np.exp(b60_40.cumsum()) - 1.0

    df_curve = pd.DataFrame(curves, index=r_sub.index)
    return df_curve


def run_persona_comparison(
    persona_a_id: str,
    persona_b_id: str,
    question: str = "",
    capital: float = 100000.0,
) -> dict[str, Any]:
    """Execute fast side-by-side quantitative comparison between two personas.

    Evaluates:
    - Same question on 2 contrasting personas.
    - Two-level strategic allocations.
    - Risk profiles & 2022 stagflation stress tests.
    - 2022 stress curve overlay time series.
    - Rule-based governance alerts highlighting contrasting adequation reactions.
    """
    returns_cad, prices_cad, universe = get_processed_dataset()

    p_a = get_persona(persona_a_id)
    p_b = get_persona(persona_b_id)

    # 1. Optimizations
    opt_a = optimize_two_level_portfolio(
        returns_df=returns_cad,
        universe_df=universe,
        sleeves=p_a.constraints.strategic_sleeves,
        target_vol_band=p_a.constraints.target_vol_band,
    )
    opt_b = optimize_two_level_portfolio(
        returns_df=returns_cad,
        universe_df=universe,
        sleeves=p_b.constraints.strategic_sleeves,
        target_vol_band=p_b.constraints.target_vol_band,
    )

    weights_a = {t: round(float(w), 4) for t, w in opt_a.weights.items() if w > 0.001}
    weights_b = {t: round(float(w), 4) for t, w in opt_b.weights.items() if w > 0.001}

    # 2. Risk Metrics
    metrics_a = portfolio_risk_metrics(weights_a, returns_cad)
    metrics_b = portfolio_risk_metrics(weights_b, returns_cad)

    # 3. Stress Tests
    stress_a = stress_test_2022_episode(weights_a, returns_cad)
    stress_b = stress_test_2022_episode(weights_b, returns_cad)

    # 4. 2022 Stress Overlay Curve
    curve_df = compute_2022_stress_curve(
        portfolios={p_a.name: weights_a, p_b.name: weights_b},
        returns_df=returns_cad,
    )

    # 5. Rule Governance Alerts for Common Question
    user_reqs = [question] if question.strip() else []
    gov_a = check_governance_rules(p_a, weights_a, universe, user_requests=user_reqs)
    gov_b = check_governance_rules(p_b, weights_b, universe, user_requests=user_reqs)

    return {
        "persona_a": p_a,
        "persona_b": p_b,
        "weights_a": weights_a,
        "weights_b": weights_b,
        "metrics_a": metrics_a,
        "metrics_b": metrics_b,
        "stress_a": stress_a,
        "stress_b": stress_b,
        "curve_df": curve_df,
        "gov_a": gov_a,
        "gov_b": gov_b,
        "capital": capital,
        "question": question,
    }
