"""Stress testing and sensitivity analysis engine for AlphaForge AI.

Implements:
- 2022 market episode replay (simultaneous stock and bond drawdown).
- Rolling window risk dynamics (rolling vol, worst drawdown periods).
- Cap and allocation sensitivity analysis (evaluating how allocating to volatile assets like TSLA or BTC impacts portfolio risk).
"""

from __future__ import annotations

import logging
from typing import Any, Literal

import numpy as np
import pandas as pd

from alphaforge.app.tools.optimize import optimize_min_variance
from alphaforge.app.tools.risk import (
    annualized_volatility,
    cvar_95,
    max_drawdown,
    portfolio_returns,
    portfolio_risk_metrics,
)

logger = logging.getLogger(__name__)

EPISODE_2022_START = "2022-01-01"
EPISODE_2022_END = "2022-12-31"


def stress_test_2022_episode(
    weights: dict[str, float] | pd.Series,
    returns_df: pd.DataFrame,
    start_date: str = EPISODE_2022_START,
    end_date: str = EPISODE_2022_END,
) -> dict[str, Any]:
    """Replay the 2022 stagflationary rate-hike shock.

    In 2022, central bank tightening caused both equities and traditional bonds
    to drop simultaneously, breaking standard 60/40 negative correlation assumptions.
    """
    p_ret = portfolio_returns(weights, returns_df)
    r_sub = p_ret.loc[start_date:end_date]
    if len(r_sub) == 0:
        raise ValueError(f"No return data in interval {start_date} to {end_date}")

    cum_ret = float(np.exp(r_sub.sum()) - 1.0)
    vol_2022 = annualized_volatility(r_sub)
    mdd_2022 = max_drawdown(r_sub)
    cvar_2022 = cvar_95(r_sub)

    # Benchmarks for comparison
    benchmarks: dict[str, dict[str, float]] = {}
    for bm in ["XIU.TO", "SPY", "XBB.TO"]:
        if bm in returns_df.columns:
            bm_sub = returns_df[bm].loc[start_date:end_date]
            benchmarks[bm] = {
                "cumulative_return": round(float(np.exp(bm_sub.sum()) - 1.0), 4),
                "annualized_vol": round(annualized_volatility(bm_sub), 4),
                "max_drawdown": round(max_drawdown(bm_sub), 4),
            }

    # Standard 60/40 benchmark (60% XIU.TO + 40% XBB.TO)
    if "XIU.TO" in returns_df.columns and "XBB.TO" in returns_df.columns:
        b60_40 = 0.6 * returns_df["XIU.TO"].loc[start_date:end_date] + 0.4 * returns_df["XBB.TO"].loc[start_date:end_date]
        benchmarks["Benchmark_60_40_CAD"] = {
            "cumulative_return": round(float(np.exp(b60_40.sum()) - 1.0), 4),
            "annualized_vol": round(annualized_volatility(b60_40), 4),
            "max_drawdown": round(max_drawdown(b60_40), 4),
        }

    return {
        "episode": "2022 Stagflation / Rate-Hike Shock",
        "start_date": start_date,
        "end_date": end_date,
        "portfolio": {
            "cumulative_return": round(cum_ret, 4),
            "annualized_volatility": round(vol_2022, 4),
            "max_drawdown": round(mdd_2022, 4),
            "cvar_95": round(cvar_2022, 4),
        },
        "benchmarks": benchmarks,
        "historical_lesson": (
            "During 2022, Canadian aggregate bonds (XBB.TO) fell alongside equities. "
            "Ultra short-term bonds (ZST.TO) and cash equivalents preserved capital substantially better."
        ),
    }


def rolling_risk_windows(
    weights: dict[str, float] | pd.Series,
    returns_df: pd.DataFrame,
    window_days: int = 63,  # ~1 quarter of trading days
) -> dict[str, Any]:
    """Calculate rolling volatility and identify peak risk regimes over historical sample."""
    p_ret = portfolio_returns(weights, returns_df)
    rolling_vol = p_ret.rolling(window_days).std() * np.sqrt(252)
    rolling_cum = np.exp(p_ret.rolling(window_days).sum()) - 1.0

    peak_vol_date = str(rolling_vol.idxmax())
    peak_vol_val = float(rolling_vol.max())
    min_vol_date = str(rolling_vol.idxmin())
    min_vol_val = float(rolling_vol.min())
    mean_vol_val = float(rolling_vol.mean())

    worst_window_date = str(rolling_cum.idxmin())
    worst_window_ret = float(rolling_cum.min())

    return {
        "window_days": window_days,
        "mean_rolling_vol": round(mean_vol_val, 4),
        "peak_rolling_vol": round(peak_vol_val, 4),
        "peak_vol_date": peak_vol_date,
        "min_rolling_vol": round(min_vol_val, 4),
        "min_vol_date": min_vol_date,
        "worst_rolling_return": round(worst_window_ret, 4),
        "worst_window_date": worst_window_date,
    }


def sensitivity_to_asset_cap(
    returns_df: pd.DataFrame,
    universe_df: pd.DataFrame,
    target_asset: str,
    cap_range: list[float] | None = None,
    base_constraints: dict[str, Any] | None = None,
    mode: Literal["cap", "fixed_weight"] = "fixed_weight",
) -> list[dict[str, Any]]:
    """Evaluate how allocating to or capping an asset impacts portfolio risk.

    If mode == "fixed_weight", forces target_asset to exact tested weight (w_target == val),
    demonstrating the exact consequence of holding e.g. 0%, 3%, 5%, 10% TSLA for Robert.
    If mode == "cap", sets upper bound (w_target <= val).
    """
    if cap_range is None:
        cap_range = [0.0, 0.02, 0.05, 0.08, 0.10, 0.15]

    base = base_constraints or {}
    results = []

    for val in cap_range:
        current_caps = dict(base.get("per_asset_caps") or {}) if isinstance(base.get("per_asset_caps"), dict) else {}
        current_floors = dict(base.get("per_asset_floors") or {}) if isinstance(base.get("per_asset_floors"), dict) else {}

        if mode == "fixed_weight":
            current_caps[target_asset] = val
            current_floors[target_asset] = val
        else:
            current_caps[target_asset] = val

        exclusions = [e for e in base.get("exclusions", []) if e != target_asset]
        if val == 0.0:
            exclusions.append(target_asset)
            if target_asset in current_floors:
                del current_floors[target_asset]

        try:
            opt = optimize_min_variance(
                returns_df=returns_df,
                universe_df=universe_df,
                per_asset_caps=current_caps if current_caps else None,
                per_asset_floors=current_floors if current_floors else None,
                sector_caps=base.get("sector_caps"),
                class_caps=base.get("class_caps"),
                class_floors=base.get("class_floors"),
                target_vol=base.get("target_vol"),
                exclusions=exclusions,
                annualization_factor=252,
            )

            p_metrics = portfolio_risk_metrics(opt.weights, returns_df)
            stress_2022 = stress_test_2022_episode(opt.weights, returns_df)

            results.append(
                {
                    "target_asset": target_asset,
                    "tested_allocation": round(val, 4),
                    "realized_weight": round(opt.weights.get(target_asset, 0.0), 4),
                    "annualized_volatility": p_metrics["annualized_volatility"],
                    "max_drawdown": p_metrics["max_drawdown"],
                    "cvar_95": p_metrics["cvar_95"],
                    "drawdown_2022": stress_2022["portfolio"]["max_drawdown"],
                }
            )
        except Exception as e:
            logger.warning(f"Optimization infeasible for value {val} on {target_asset}: {e}")
            results.append(
                {
                    "target_asset": target_asset,
                    "tested_allocation": round(val, 4),
                    "realized_weight": None,
                    "error": str(e),
                }
            )

    return results
