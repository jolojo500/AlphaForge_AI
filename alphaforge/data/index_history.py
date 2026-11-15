"""Long index proxies for drawdown and stress episodes before 2021 (#176). Track A.

The price files start in 2021-11; `data/cache/index_history/index_monthly.csv` (committed,
see its README) holds monthly closes of the S&P 500, the S&P/TSX Composite and AGG from 1999.
A scenario is mapped to the proxies by its US-equity / Canadian-equity / bond shares; gold,
crypto and anything else is held flat (no proxy). Only rows dated <= as_of are ever read.
"""

from __future__ import annotations

import datetime as dt
import functools
from pathlib import Path

import pandas as pd

from alphaforge import config

INDEX_HISTORY_DIR = config.CACHE_DIR / "index_history"
INDEX_FILE = INDEX_HISTORY_DIR / "index_monthly.csv"
PROXIES = {"equity_us": "GSPC", "equity_ca": "GSPTSE", "bond": "AGG"}
PROXY_LABELS = {
    "GSPC": "S&P 500 (price index, USD)",
    "GSPTSE": "S&P/TSX Composite (price index, CAD)",
    "AGG": "AGG, U.S. aggregate bonds (adjusted close, USD; flat before 2003-09)",
}
# Stress episodes, month-end dates: dot-com bear market and the 2008 financial crisis.
EPISODES = {
    "stress_2000_02": (pd.Timestamp("2000-03-31"), pd.Timestamp("2002-09-30")),
    "stress_2008": (pd.Timestamp("2007-10-31"), pd.Timestamp("2009-02-28")),
}
MIN_MONTHS = 24
US_MARKETS = {"NYSE", "NASDAQ", "NYSE Arca", "Cboe BZX"}
SOURCE = "index_history/index_monthly.csv (Yahoo Finance, monthly closes)"
SOURCE_URL = "https://finance.yahoo.com/quote/%5EGSPC/history/"


@functools.cache
def _read(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p, index_col="date", parse_dates=["date"], encoding="utf-8")
    return df.sort_index()


def load_index_history(as_of: dt.date | str | None = None, path: Path | str | None = None) -> pd.DataFrame:
    """Monthly closes (one column per proxy) with every row dated <= `as_of`."""
    df = _read(str(path or INDEX_FILE))
    if df.empty or as_of is None:
        return df.copy()
    return df.loc[: pd.Timestamp(as_of)].copy()


def proxy_shares(weights: dict[str, float], info: pd.DataFrame) -> dict[str, float]:
    """Scenario weights -> {equity_us, equity_ca, bond, other} shares (sum to 1)."""
    out = {"equity_us": 0.0, "equity_ca": 0.0, "bond": 0.0, "other": 0.0}
    total = sum(float(w) for w in weights.values()) or 1.0
    for t, w in weights.items():
        share = float(w) / total
        if t not in info.index:
            out["other"] += share
            continue
        cls, market = info.at[t, "asset_class"], info.at[t, "market"]
        if cls in ("equity", "etf_equity"):
            out["equity_us" if market in US_MARKETS else "equity_ca"] += share
        elif cls == "etf_bond":
            out["bond"] += share
        else:
            out["other"] += share
    return {k: round(v, 6) for k, v in out.items()}


def proxy_value(history: pd.DataFrame, shares: dict[str, float]) -> pd.Series:
    """Growth of 1 unit of a proxy portfolio rebalanced monthly to `shares` ("other" is flat).

    A proxy with no data yet (AGG before 2003-09) contributes a zero return for that month.
    """
    if history.empty:
        return pd.Series(dtype=float)
    rets = history.pct_change(fill_method=None).iloc[1:]
    port = pd.Series(0.0, index=rets.index)
    for key, col in PROXIES.items():
        if col in rets.columns and shares.get(key, 0.0) > 0:
            port = port + rets[col].fillna(0.0) * shares[key]
    start = pd.Series([1.0], index=history.index[:1])
    return pd.concat([start, (1 + port).cumprod()])


def proxy_drawdown(history: pd.DataFrame, shares: dict[str, float]) -> float | None:
    """Largest peak-to-trough fall of the proxy portfolio over the whole history, as a negative ratio."""
    v = proxy_value(history, shares)
    if len(v) < MIN_MONTHS:
        return None
    return float((v / v.cummax() - 1).min())


def proxy_stress(history: pd.DataFrame, shares: dict[str, float], episode: str) -> dict[str, float] | None:
    """Total return and max drawdown of the proxy portfolio over a named episode, or None if not covered."""
    start, end = EPISODES[episode]
    if history.empty or history.index[-1] < end or history.index[0] > start:
        return None
    v = proxy_value(history.loc[start:end], shares)
    if len(v) < 2:
        return None
    return {"return": float(v.iloc[-1] - 1), "drawdown": float((v / v.cummax() - 1).min())}


def proxy_label(shares: dict[str, float]) -> str:
    parts = [f"{shares[k]:.0%} {PROXY_LABELS[c]}" for k, c in PROXIES.items() if shares.get(k, 0.0) > 0]
    if shares.get("other", 0.0) > 0:
        parts.append(f"{shares['other']:.0%} held flat (gold, crypto or other: no proxy)")
    return ", ".join(parts) or "no mapped share"
