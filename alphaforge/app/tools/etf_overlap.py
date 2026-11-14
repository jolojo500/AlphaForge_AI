"""ETF holdings overlap and look-through exposure for AlphaForge AI.

Pure functions operating on ``data/etf/fund_holdings.csv``. An ETF whose holdings
are not available is treated as an opaque single asset (weight 1.0 on itself).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def _holdings_path(data_dir: str | Path | None = None) -> Path:
    base = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    return base / "etf" / "fund_holdings.csv"


def load_fund_holdings(data_dir: str | Path | None = None) -> pd.DataFrame:
    path = _holdings_path(data_dir)
    if not path.exists():
        return pd.DataFrame(columns=["etf", "holding_ticker", "holding_name", "weight", "as_of_date", "source_url", "retrieved_date"])
    return pd.read_csv(path)


def _holdings_map(etf: str, data_dir: str | Path | None = None) -> dict[str, float]:
    df = load_fund_holdings(data_dir)
    if df.empty:
        return {}
    sub = df[df["etf"].astype(str).str.upper() == str(etf).upper()]
    m: dict[str, float] = {}
    for _, r in sub.iterrows():
        t = str(r["holding_ticker"]).upper()
        m[t] = m.get(t, 0.0) + float(r["weight"])
    if not m:
        # Treat an unknown ETF/asset as a single opaque position.
        m[str(etf).upper()] = 1.0
    return m


def overlap(etf_a: str, etf_b: str, data_dir: str | Path | None = None) -> float:
    """Overlap between two ETFs (or an ETF and a single stock) as the sum of
    the minimum weights of their common holdings."""
    a = _holdings_map(etf_a, data_dir)
    b = _holdings_map(etf_b, data_dir)
    common = set(a) & set(b)
    return float(sum(min(a[t], b[t]) for t in common))


def look_through(portfolio_weights: Any, data_dir: str | Path | None = None) -> dict[str, float]:
    """Expand ETF positions into their underlying holdings, returning effective
    single-stock (and residual) exposure."""
    if isinstance(portfolio_weights, pd.Series):
        pw = portfolio_weights.to_dict()
    elif isinstance(portfolio_weights, dict):
        pw = dict(portfolio_weights)
    else:
        pw = {k: v for k, v in portfolio_weights}

    result: dict[str, float] = {}
    for ticker, w in pw.items():
        w = float(w)
        if w == 0:
            continue
        holdings = _holdings_map(str(ticker), data_dir)
        # If the ticker has no expanded holdings (not in data), _holdings_map
        # returns {ticker: 1.0}, so it stays a direct position.
        # But only expand if it is actually an ETF present in holdings data;
        # otherwise keep as direct. Detect by checking whether holdings came
        # from data.
        df = load_fund_holdings(data_dir)
        is_etf = (not df.empty) and (str(ticker).upper() in set(df["etf"].astype(str).str.upper()))
        if is_etf:
            for h, hw in holdings.items():
                result[h] = result.get(h, 0.0) + w * float(hw)
        else:
            t = str(ticker).upper()
            result[t] = result.get(t, 0.0) + w
    return {k: round(v, 6) for k, v in result.items()}


__all__ = ["overlap", "look_through", "load_fund_holdings"]
