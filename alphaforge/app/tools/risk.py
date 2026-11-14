"""Risk metrics and analytics engine for AlphaForge AI.

Calculates standard institutional risk indicators (all in CAD):
- Annualized volatility (sample std dev * sqrt(252)).
- Maximum peak-to-trough drawdown over cumulative returns.
- Conditional Value-at-Risk at 95% confidence level (CVaR95 / Expected Shortfall).
- Correlation matrix.
- Beta vs Canadian equity benchmark (XIU.TO).
- Portfolio risk decomposition and marginal/percentage risk contributions.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_BENCHMARK = "XIU.TO"
TRADING_DAYS_PER_YEAR = 252


def annualized_volatility(
    returns: pd.Series | pd.DataFrame,
    trading_days: int = TRADING_DAYS_PER_YEAR,
) -> float | pd.Series:
    """Calculate annualized volatility from daily log/simple returns."""
    if isinstance(returns, pd.DataFrame):
        return returns.std(ddof=1) * np.sqrt(trading_days)
    return float(returns.std(ddof=1) * np.sqrt(trading_days))


def max_drawdown(returns: pd.Series | pd.DataFrame) -> float | pd.Series:
    """Calculate maximum peak-to-trough drawdown.

    Returns negative number representing the deepest loss from peak (e.g., -0.25 = -25%).
    """
    if isinstance(returns, pd.DataFrame):
        cum = np.exp(returns.cumsum())
        cum_max = cum.cummax()
        dd = (cum - cum_max) / cum_max
        return dd.min()

    cum = np.exp(returns.cumsum())
    cum_max = cum.cummax()
    dd = (cum - cum_max) / cum_max
    return float(dd.min())


def cvar_95(
    returns: pd.Series | pd.DataFrame,
    alpha: float = 0.05,
) -> float | pd.Series:
    """Calculate Conditional Value-at-Risk (CVaR / Expected Shortfall) at 95% confidence.

    Defined as the expected daily loss in the worst 5% tail (returned as a positive number).
    """
    if isinstance(returns, pd.DataFrame):
        def _col_cvar(col: pd.Series) -> float:
            cutoff = col.quantile(alpha)
            tail = col[col <= cutoff]
            return float(-tail.mean()) if len(tail) > 0 else 0.0

        return returns.apply(_col_cvar)

    cutoff = returns.quantile(alpha)
    tail = returns[returns <= cutoff]
    return float(-tail.mean()) if len(tail) > 0 else 0.0


def correlation_matrix(returns: pd.DataFrame) -> pd.DataFrame:
    """Calculate Pearson correlation matrix between assets."""
    return returns.corr()


def beta_vs_benchmark(
    returns: pd.Series | pd.DataFrame,
    benchmark_returns: pd.Series,
) -> float | pd.Series:
    """Calculate market beta relative to benchmark returns (default XIU.TO).

    beta = Cov(r_i, r_b) / Var(r_b)
    """
    var_b = float(benchmark_returns.var())
    if var_b == 0 or np.isnan(var_b):
        raise ValueError("Benchmark variance is zero or NaN")

    if isinstance(returns, pd.DataFrame):
        covs = returns.apply(lambda col: col.cov(benchmark_returns))
        return covs / var_b

    return float(returns.cov(benchmark_returns) / var_b)


def portfolio_returns(
    weights: dict[str, float] | pd.Series,
    returns_df: pd.DataFrame,
) -> pd.Series:
    """Compute daily portfolio returns from asset weights."""
    w_series = pd.Series(weights) if isinstance(weights, dict) else weights
    common = w_series.index.intersection(returns_df.columns)
    if len(common) == 0:
        raise ValueError("No common tickers between weights and returns")

    w_sub = w_series[common]
    w_norm = w_sub / w_sub.sum()
    r_sub = returns_df[common]
    p_ret = r_sub.dot(w_norm)
    p_ret.name = "portfolio_return"
    return p_ret


def portfolio_risk_metrics(
    weights: dict[str, float] | pd.Series,
    returns_df: pd.DataFrame,
    benchmark_ticker: str = DEFAULT_BENCHMARK,
    trading_days: int = TRADING_DAYS_PER_YEAR,
) -> dict[str, Any]:
    """Calculate full risk profile for a weighted portfolio.

    Returns dict containing:
    - annualized_volatility
    - max_drawdown
    - cvar_95
    - beta_vs_benchmark
    - realized_annual_return (descriptive, not predictive)
    - active_assets_count
    """
    w_series = pd.Series(weights) if isinstance(weights, dict) else weights
    active_weights = w_series[w_series > 1e-4]
    p_ret = portfolio_returns(active_weights, returns_df)

    b_ret = returns_df[benchmark_ticker] if benchmark_ticker in returns_df.columns else None
    beta_val = beta_vs_benchmark(p_ret, b_ret) if b_ret is not None else np.nan

    ann_vol = annualized_volatility(p_ret, trading_days)
    mdd = max_drawdown(p_ret)
    cvar = cvar_95(p_ret)
    realized_ret = float(p_ret.mean() * trading_days)

    return {
        "annualized_volatility": round(ann_vol, 4),
        "max_drawdown": round(mdd, 4),
        "cvar_95": round(cvar, 4),
        "beta_vs_benchmark": round(beta_val, 4) if not np.isnan(beta_val) else None,
        "benchmark": benchmark_ticker,
        "realized_annual_return": round(realized_ret, 4),
        "active_assets_count": int(len(active_weights)),
    }


def risk_contributions(
    weights: dict[str, float] | pd.Series,
    returns_df: pd.DataFrame,
    trading_days: int = TRADING_DAYS_PER_YEAR,
) -> pd.DataFrame:
    """Decompose portfolio volatility into asset risk contributions.

    For asset i:
    - weight: w_i
    - Marginal Risk Contribution (MRC_i): (Sigma w)_i / sigma_p
    - Absolute Risk Contribution (RC_i): w_i * MRC_i  (sum(RC_i) = sigma_p)
    - Percentage Risk Contribution (%RC_i): RC_i / sigma_p  (sum(%RC_i) = 1.0)
    """
    w_series = pd.Series(weights) if isinstance(weights, dict) else weights
    active_tickers = [t for t in w_series.index if t in returns_df.columns and w_series[t] > 1e-6]

    if not active_tickers:
        return pd.DataFrame(columns=["weight", "marginal_risk", "abs_risk_contribution", "pct_risk_contribution"])

    w = w_series[active_tickers].to_numpy()
    w = w / np.sum(w)  # normalize

    ret_sub = returns_df[active_tickers]
    cov_matrix = ret_sub.cov().to_numpy() * trading_days

    port_var = float(w.T @ cov_matrix @ w)
    port_vol = np.sqrt(port_var) if port_var > 0 else 1e-8

    # Marginal risk contribution = (cov @ w) / port_vol
    mrc = (cov_matrix @ w) / port_vol
    abs_rc = w * mrc
    pct_rc = abs_rc / port_vol

    df_rc = pd.DataFrame(
        {
            "ticker": active_tickers,
            "weight": np.round(w, 4),
            "marginal_risk": np.round(mrc, 4),
            "abs_risk_contribution": np.round(abs_rc, 4),
            "pct_risk_contribution": np.round(pct_rc, 4),
        }
    ).sort_values("pct_risk_contribution", ascending=False).reset_index(drop=True)

    return df_rc


def asset_summary_metrics(
    returns_df: pd.DataFrame,
    benchmark_ticker: str = DEFAULT_BENCHMARK,
    trading_days: int = TRADING_DAYS_PER_YEAR,
) -> pd.DataFrame:
    """Calculate summary risk metrics for all individual assets in the returns matrix."""
    ann_vol = annualized_volatility(returns_df, trading_days)
    mdd = max_drawdown(returns_df)
    cvar = cvar_95(returns_df)

    b_ret = returns_df[benchmark_ticker] if benchmark_ticker in returns_df.columns else None
    if b_ret is not None:
        betas = beta_vs_benchmark(returns_df, b_ret)
    else:
        betas = pd.Series(np.nan, index=returns_df.columns)

    summary = pd.DataFrame(
        {
            "ticker": returns_df.columns,
            "annualized_volatility": np.round(ann_vol, 4),
            "max_drawdown": np.round(mdd, 4),
            "cvar_95": np.round(cvar, 4),
            "beta_xiu": np.round(betas, 4),
        }
    ).set_index("ticker")

    return summary
