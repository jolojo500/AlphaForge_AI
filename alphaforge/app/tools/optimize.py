"""Portfolio optimization engine using cvxpy for AlphaForge AI.

Implements:
- Constrained Minimum Variance optimization without return forecasting.
- Convex Risk Parity / Equal Risk Contribution (Spinu formulation).
- Robust handling of per-asset caps, sector caps, class caps/floors, and exclusions.
- Volatility constraint upper-bounding.
- Diversification entropy regularization.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

import cvxpy as cp
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252


@dataclass
class OptimizationResult:
    weights: dict[str, float]
    annualized_vol: float
    solver_status: str
    objective_type: str
    active_assets: int
    constraints_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "weights": self.weights,
            "annualized_vol": round(self.annualized_vol, 4),
            "solver_status": self.solver_status,
            "objective_type": self.objective_type,
            "active_assets": self.active_assets,
            "constraints_summary": self.constraints_summary,
        }


def optimize_min_variance(
    returns_df: pd.DataFrame,
    universe_df: pd.DataFrame,
    per_asset_caps: dict[str, float] | float | None = None,
    per_asset_floors: dict[str, float] | float | None = None,
    sector_caps: dict[str, float] | None = None,
    sector_floors: dict[str, float] | None = None,
    class_caps: dict[str, float] | None = None,
    class_floors: dict[str, float] | None = None,
    target_vol: float | None = None,
    exclusions: list[str] | None = None,
    diversification_entropy: float = 0.0,
    annualization_factor: int = TRADING_DAYS_PER_YEAR,
) -> OptimizationResult:
    """Solve constrained minimum variance portfolio optimization using cvxpy.

    min_w  w^T Sigma w  [- lambda * sum(log(w))]
    s.t.   sum(w) == 1
           w >= 0
           w_i == 0 for i in exclusions
           w_i <= cap_i
           w_i >= floor_i
           sum_{i in sector} w_i <= sector_cap
           sum_{i in class} w_i <= class_cap
           sum_{i in class} w_i >= class_floor
           (optional) w^T Sigma w <= target_vol^2
    """
    tickers = list(returns_df.columns)
    n = len(tickers)
    exclusions_set = set(exclusions or [])

    # Covariance matrix (annualized)
    sigma_np = returns_df.cov().to_numpy() * annualization_factor
    # Numerical safeguard: ensure positive semi-definite
    sigma_np = (sigma_np + sigma_np.T) / 2.0
    min_eig = np.min(np.linalg.eigvalsh(sigma_np))
    if min_eig < 1e-8:
        sigma_np += (1e-8 - min_eig) * np.eye(n)

    w = cp.Variable(n)
    constraints: list[cp.Constraint] = [cp.sum(w) == 1, w >= 0]

    # Map tickers to metadata
    sector_map = dict(zip(universe_df["ticker"], universe_df["sector"]))
    class_map = dict(zip(universe_df["ticker"], universe_df["asset_class"]))

    # Exclusions
    for i, t in enumerate(tickers):
        if t in exclusions_set:
            constraints.append(w[i] == 0)

    # Per-asset caps
    if per_asset_caps is not None:
        if isinstance(per_asset_caps, (int, float)):
            for i, t in enumerate(tickers):
                if t not in exclusions_set:
                    constraints.append(w[i] <= float(per_asset_caps))
        elif isinstance(per_asset_caps, dict):
            for i, t in enumerate(tickers):
                if t in per_asset_caps and t not in exclusions_set:
                    constraints.append(w[i] <= float(per_asset_caps[t]))

    # Per-asset floors
    if per_asset_floors is not None:
        if isinstance(per_asset_floors, (int, float)):
            for i, t in enumerate(tickers):
                if t not in exclusions_set:
                    constraints.append(w[i] >= float(per_asset_floors))
        elif isinstance(per_asset_floors, dict):
            for i, t in enumerate(tickers):
                if t in per_asset_floors and t not in exclusions_set:
                    constraints.append(w[i] >= float(per_asset_floors[t]))

    # Sector caps
    if sector_caps:
        for sector_name, cap_val in sector_caps.items():
            sector_indices = [i for i, t in enumerate(tickers) if sector_map.get(t) == sector_name and t not in exclusions_set]
            if sector_indices:
                constraints.append(cp.sum(w[sector_indices]) <= float(cap_val))

    # Sector floors
    if sector_floors:
        for sector_name, floor_val in sector_floors.items():
            sector_indices = [i for i, t in enumerate(tickers) if sector_map.get(t) == sector_name and t not in exclusions_set]
            if sector_indices:
                constraints.append(cp.sum(w[sector_indices]) >= float(floor_val))

    # Class caps
    if class_caps:
        for class_name, cap_val in class_caps.items():
            class_indices = [i for i, t in enumerate(tickers) if class_map.get(t) == class_name and t not in exclusions_set]
            if class_indices:
                constraints.append(cp.sum(w[class_indices]) <= float(cap_val))

    # Class floors
    if class_floors:
        for class_name, floor_val in class_floors.items():
            class_indices = [i for i, t in enumerate(tickers) if class_map.get(t) == class_name and t not in exclusions_set]
            if class_indices:
                constraints.append(cp.sum(w[class_indices]) >= float(floor_val))

    # Target volatility cap
    if target_vol is not None and target_vol > 0:
        constraints.append(cp.quad_form(w, sigma_np) <= float(target_vol**2))

    # Objective
    port_variance = cp.quad_form(w, sigma_np)
    if diversification_entropy > 0:
        # Entropy regularized to encourage diversification across non-excluded assets
        active_indices = [i for i, t in enumerate(tickers) if t not in exclusions_set]
        obj = cp.Minimize(port_variance - diversification_entropy * cp.sum(cp.log(w[active_indices])))
    else:
        obj = cp.Minimize(port_variance)

    problem = cp.Problem(obj, constraints)
    try:
        problem.solve(solver=cp.OSQP, eps_abs=1e-6, eps_rel=1e-6, max_iter=10000)
    except Exception as e:
        logger.warning(f"OSQP solver failed: {e}. Falling back to ECOS / SCS.")
        problem.solve(solver=cp.SCS, max_iters=10000)

    if problem.status not in ["optimal", "optimal_inaccurate"]:
        raise ValueError(f"Optimization failed with status: {problem.status}. Check constraints feasibility.")

    raw_weights = w.value
    weights_dict: dict[str, float] = {}
    for i, t in enumerate(tickers):
        val = float(raw_weights[i])
        if val > 1e-4:
            weights_dict[t] = round(val, 4)

    # Normalize weights so sum is exactly 1.0
    tot = sum(weights_dict.values())
    for t in weights_dict:
        weights_dict[t] = round(weights_dict[t] / tot, 4)

    # Re-normalize any small rounding difference
    diff = round(1.0 - sum(weights_dict.values()), 4)
    if diff != 0 and weights_dict:
        first_k = max(weights_dict, key=weights_dict.get)
        weights_dict[first_k] = round(weights_dict[first_k] + diff, 4)

    # Compute actual annualized portfolio vol
    w_vec = np.array([weights_dict.get(t, 0.0) for t in tickers])
    actual_vol = float(np.sqrt(w_vec.T @ sigma_np @ w_vec))

    constraints_summary = {
        "per_asset_caps": per_asset_caps,
        "sector_caps": sector_caps,
        "sector_floors": sector_floors,
        "class_caps": class_caps,
        "class_floors": class_floors,
        "target_vol": target_vol,
        "exclusions": list(exclusions_set),
    }

    return OptimizationResult(
        weights=weights_dict,
        annualized_vol=actual_vol,
        solver_status=problem.status,
        objective_type="constrained_min_variance",
        active_assets=len(weights_dict),
        constraints_summary=constraints_summary,
    )


def optimize_risk_parity(
    returns_df: pd.DataFrame,
    universe_df: pd.DataFrame,
    exclusions: list[str] | None = None,
    risk_budgets: dict[str, float] | None = None,
    annualization_factor: int = TRADING_DAYS_PER_YEAR,
) -> OptimizationResult:
    """Solve Spinu's convex formulation for Risk Parity (Equal Risk Contribution).

    min_x  1/2 x^T Sigma x - sum(b_i * log(x_i))
    weights = x / sum(x)
    """
    exclusions_set = set(exclusions or [])
    active_tickers = [t for t in returns_df.columns if t not in exclusions_set]
    k = len(active_tickers)

    ret_sub = returns_df[active_tickers]
    sigma_np = ret_sub.cov().to_numpy() * annualization_factor
    sigma_np = (sigma_np + sigma_np.T) / 2.0
    min_eig = np.min(np.linalg.eigvalsh(sigma_np))
    if min_eig < 1e-8:
        sigma_np += (1e-8 - min_eig) * np.eye(k)

    # Default equal risk budget 1/k
    if risk_budgets:
        b_vec = np.array([risk_budgets.get(t, 1.0 / k) for t in active_tickers])
        b_vec = b_vec / np.sum(b_vec)
    else:
        b_vec = np.ones(k) / k

    x = cp.Variable(k, pos=True)
    obj = cp.Minimize(0.5 * cp.quad_form(x, sigma_np) - cp.sum(cp.multiply(b_vec, cp.log(x))))
    problem = cp.Problem(obj)
    problem.solve(solver=cp.SCS, max_iters=10000)

    if problem.status not in ["optimal", "optimal_inaccurate"]:
        raise ValueError(f"Risk parity solver failed: {problem.status}")

    raw_x = x.value
    weights_np = raw_x / np.sum(raw_x)

    weights_dict: dict[str, float] = {}
    for i, t in enumerate(active_tickers):
        val = float(weights_np[i])
        if val > 1e-4:
            weights_dict[t] = round(val, 4)

    tot = sum(weights_dict.values())
    for t in weights_dict:
        weights_dict[t] = round(weights_dict[t] / tot, 4)

    # Re-normalize
    diff = round(1.0 - sum(weights_dict.values()), 4)
    if diff != 0 and weights_dict:
        first_k = max(weights_dict, key=weights_dict.get)
        weights_dict[first_k] = round(weights_dict[first_k] + diff, 4)

    w_vec = np.array([weights_dict.get(t, 0.0) for t in active_tickers])
    actual_vol = float(np.sqrt(w_vec.T @ sigma_np @ w_vec))

    return OptimizationResult(
        weights=weights_dict,
        annualized_vol=actual_vol,
        solver_status=problem.status,
        objective_type="equal_risk_parity",
        active_assets=len(weights_dict),
        constraints_summary={"exclusions": list(exclusions_set), "risk_budgets": "equal"},
    )


@dataclass
class StrategicSleeveConfig:
    """Strategic asset allocation sleeve definition."""
    name: str  # equity, bonds, crypto, gold_cash
    target_weight: float  # e.g. 0.80
    weight_band: tuple[float, float]  # e.g. (0.75, 0.85)
    asset_classes: list[str]  # e.g. ["equity", "etf_equity"]
    single_asset_cap: float | None = None  # default cap for intra-sleeve assets (e.g. 0.166)
    per_asset_caps: dict[str, float] | float | None = None
    per_asset_floors: dict[str, float] | float | None = None
    sector_caps: dict[str, float] | None = None
    sector_floors: dict[str, float] | None = None
    exclusions: list[str] | None = None
    fixed_allocations: dict[str, float] | None = None  # e.g. {"GLD": 1.0} or {"BTC-USD": 0.5, "ETH-USD": 0.5}
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "target_weight": self.target_weight,
            "weight_band": self.weight_band,
            "asset_classes": self.asset_classes,
            "single_asset_cap": self.single_asset_cap,
            "per_asset_caps": self.per_asset_caps,
            "per_asset_floors": self.per_asset_floors,
            "sector_caps": self.sector_caps,
            "sector_floors": self.sector_floors,
            "exclusions": self.exclusions,
            "fixed_allocations": self.fixed_allocations,
            "rationale": self.rationale,
        }


def optimize_two_level_portfolio(
    returns_df: pd.DataFrame,
    universe_df: pd.DataFrame,
    sleeves: list[StrategicSleeveConfig],
    target_vol_band: tuple[float, float] | None = None,
    annualization_factor: int = TRADING_DAYS_PER_YEAR,
) -> OptimizationResult:
    """Execute two-level portfolio allocation:

    Level 1: Strategic sleeve targets (equity, bonds, crypto, gold) aligned with persona horizon and risk profile.
    Level 2: Intra-sleeve quantitative optimization (constrained minimum variance under preference tilts and caps).
    """
    total_sleeve_weight = sum(s.target_weight for s in sleeves)
    if not (0.98 <= total_sleeve_weight <= 1.02):
        raise ValueError(f"Sleeve target weights must sum to 1.0, got {total_sleeve_weight}")

    combined_weights: dict[str, float] = {}
    sleeve_results: dict[str, Any] = {}
    class_map = dict(zip(universe_df["ticker"], universe_df["asset_class"]))

    for sleeve in sleeves:
        if sleeve.target_weight <= 1e-5:
            continue

        if sleeve.fixed_allocations:
            tot_fixed = sum(sleeve.fixed_allocations.values())
            intra_weights = {t: w / tot_fixed for t, w in sleeve.fixed_allocations.items()}
            sleeve_results[sleeve.name] = {
                "intra_weights": intra_weights,
                "sleeve_weight": sleeve.target_weight,
                "method": "fixed_allocation",
            }
        else:
            avail_tickers = [
                t
                for t in returns_df.columns
                if class_map.get(t) in sleeve.asset_classes and t not in (sleeve.exclusions or [])
            ]
            if not avail_tickers:
                raise ValueError(f"No available tickers for sleeve '{sleeve.name}' with classes {sleeve.asset_classes}")

            sub_returns = returns_df[avail_tickers]
            sub_univ = universe_df[universe_df["ticker"].isin(avail_tickers)]

            # Resolve sleeve per-asset caps with single_asset_cap default
            intra_caps = sleeve.per_asset_caps
            if sleeve.single_asset_cap is not None:
                if isinstance(intra_caps, dict):
                    resolved_caps = {t: intra_caps.get(t, sleeve.single_asset_cap) for t in avail_tickers}
                elif intra_caps is None:
                    resolved_caps = sleeve.single_asset_cap
                else:
                    resolved_caps = intra_caps
            else:
                resolved_caps = intra_caps

            res = optimize_min_variance(
                returns_df=sub_returns,
                universe_df=sub_univ,
                per_asset_caps=resolved_caps,
                per_asset_floors=sleeve.per_asset_floors,
                sector_caps=sleeve.sector_caps,
                sector_floors=sleeve.sector_floors,
                exclusions=sleeve.exclusions,
                annualization_factor=annualization_factor,
            )
            intra_weights = res.weights
            sleeve_results[sleeve.name] = {
                "intra_weights": intra_weights,
                "sleeve_weight": sleeve.target_weight,
                "method": "constrained_min_variance",
                "status": res.solver_status,
            }

        # Scale intra-weights by sleeve target weight
        for ticker, intra_w in intra_weights.items():
            combined_weights[ticker] = combined_weights.get(ticker, 0.0) + intra_w * sleeve.target_weight

    # Filter negligible weights
    clean_weights: dict[str, float] = {}
    for t, w in combined_weights.items():
        if w > 1e-4:
            clean_weights[t] = round(w, 4)

    # Normalize to 1.0 exactly
    tot = sum(clean_weights.values())
    for t in clean_weights:
        clean_weights[t] = round(clean_weights[t] / tot, 4)
    diff = round(1.0 - sum(clean_weights.values()), 4)
    if diff != 0 and clean_weights:
        max_k = max(clean_weights, key=clean_weights.get)
        clean_weights[max_k] = round(clean_weights[max_k] + diff, 4)

    # Calculate portfolio volatility
    cov = returns_df.cov().to_numpy() * annualization_factor
    tickers_list = list(returns_df.columns)
    w_vec = np.array([clean_weights.get(t, 0.0) for t in tickers_list])
    realized_vol = float(np.sqrt(w_vec.T @ cov @ w_vec))

    within_band = None
    if target_vol_band:
        within_band = (target_vol_band[0] - 0.01) <= realized_vol <= (target_vol_band[1] + 0.01)

    return OptimizationResult(
        weights=clean_weights,
        annualized_vol=realized_vol,
        solver_status="optimal",
        objective_type="two_level_strategic_sleeves",
        active_assets=len(clean_weights),
        constraints_summary={
            "sleeves": [s.to_dict() for s in sleeves],
            "sleeve_breakdown": sleeve_results,
            "target_vol_band": target_vol_band,
            "within_target_vol_band": within_band,
        },
    )
