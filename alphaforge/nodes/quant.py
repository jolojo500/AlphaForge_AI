"""Quant (PRD 5.3). Track A: risk statistics computed from prices, never from the model.

Every function takes a wide CAD price frame (from DataProvider.prices_cad) and a target:
either one ticker, or a weights dict {ticker: weight} for a portfolio rebalanced daily
to those weights. The scenario builder reuses the same functions on its portfolios.
"""

from __future__ import annotations

import datetime as dt
import math
from itertools import combinations

import numpy as np
import pandas as pd

from alphaforge.data.holdings import holdings_date, holdings_weights, is_complete, load_holdings
from alphaforge.data.provider import get_provider
from alphaforge.evidence import EvidenceRegistry
from alphaforge.state import GraphState
from alphaforge.tracing import traced

Target = str | dict[str, float]

STRESS_START = pd.Timestamp("2022-01-03")
STRESS_END = pd.Timestamp("2022-12-30")
MIN_OBS = 60  # below this many daily returns, statistics are not reported
NOTABLE_CORR = 0.8  # pairs at or above this |correlation| are written as evidence
US_MARKETS = {"NYSE", "NASDAQ", "NYSE Arca", "Cboe BZX"}
SOURCE = "prices_daily.csv + fx_usdcad_daily.csv"
CALENDAR = "common TSX/US trading days, crypto weekends dropped"


# --- statistics ---------------------------------------------------------------------------


def returns(prices: pd.DataFrame, target: Target) -> pd.Series:
    """Daily simple returns of a ticker, or of a portfolio rebalanced daily to `target`."""
    if isinstance(target, str):
        return prices[target].pct_change(fill_method=None).dropna()
    w = pd.Series(target, dtype=float)
    r = prices[list(w.index)].pct_change(fill_method=None).dropna()
    return r.mul(w, axis=1).sum(axis=1)


def value(prices: pd.DataFrame, target: Target) -> pd.Series:
    """Growth of 1 CAD invested on the first date of `prices`."""
    r = returns(prices, target)
    if r.empty:
        return pd.Series(dtype=float)
    start = pd.Series([1.0], index=prices.index[:1])
    return pd.concat([start, (1 + r).cumprod()])


def periods_per_year(index: pd.DatetimeIndex) -> float:
    """Observed trading days per year, used to annualise (about 246 on the common calendar)."""
    if len(index) < 2:
        return float("nan")
    years = (index[-1] - index[0]).days / 365.25
    return (len(index) - 1) / years


def volatility(prices: pd.DataFrame, target: Target) -> float:
    """Annualised standard deviation of daily log returns."""
    r = returns(prices, target)
    if len(r) < 2:
        return float("nan")
    return float(np.log1p(r).std(ddof=1) * math.sqrt(periods_per_year(prices.index)))


def max_drawdown(prices: pd.DataFrame, target: Target) -> float:
    """Largest peak-to-trough fall, as a negative ratio (-0.25 = -25%)."""
    v = value(prices, target)
    if v.empty:
        return float("nan")
    return float((v / v.cummax() - 1).min())


def correlation(prices: pd.DataFrame, a: Target, b: Target) -> float:
    """Correlation of daily returns between two tickers or portfolios."""
    return float(returns(prices, a).corr(returns(prices, b)))


def concentration(target: Target, info: pd.DataFrame) -> dict[str, float]:
    """Sector HHI, US-listed exposure and top weight. `info` is DataProvider.asset_info().

    HHI uses the universe's sector labels (an ETF counts as its own sector; look-through
    comes with the ETF holdings in A-4). US exposure = weight in US-listed assets; crypto
    has no country and is not counted.
    """
    w = pd.Series({target: 1.0} if isinstance(target, str) else target, dtype=float)
    w = w / w.sum()
    sectors = w.groupby(info.loc[w.index, "sector"]).sum()
    us = info.loc[w.index, "market"].isin(US_MARKETS).to_numpy()
    return {
        "sector_hhi": float((sectors**2).sum()),
        "us_exposure": float(w[us].sum()),
        "top_weight": float(w.max()),
    }


def etf_overlap(
    a: str, b: str, holdings_dir=None, as_of: dt.date | str | None = None
) -> float | None:
    """Share of the portfolio two ETFs have in common: sum over shared names of min(w_a, w_b).

    None if either ETF has no cached holdings. With a partial (top-N) list the result is a
    lower bound, since unlisted names cannot be matched.
    """
    wa = holdings_weights(a, holdings_dir, as_of=as_of)
    wb = holdings_weights(b, holdings_dir, as_of=as_of)
    if not wa or not wb:
        return None
    return float(sum(min(wa[t], wb[t]) for t in wa.keys() & wb.keys()))


def _holdings_label(
    etf: str, holdings_dir=None, as_of: dt.date | str | None = None
) -> str:
    doc = load_holdings(etf, holdings_dir=holdings_dir, as_of=as_of) or {}
    n = len(doc.get("holdings", []))
    scope = "full list" if doc.get("complete", True) else f"top {n} of {doc.get('total_holdings', '?')}"
    return f"{etf} {doc.get('source_name', '?')}, as of {doc.get('as_of', '?')} ({scope})"


def stress_2022(prices: pd.DataFrame, target: Target) -> dict[str, float] | None:
    """Total return and max drawdown over 2022 (rate-hike episode), or None if not covered."""
    if prices.empty or prices.index[-1] < STRESS_END:
        return None
    window = prices.loc[STRESS_START:STRESS_END]
    if len(window) < MIN_OBS:
        return None
    v = value(window, target)
    return {"return": float(v.iloc[-1] - 1), "drawdown": float((v / v.cummax() - 1).min())}


# --- node ---------------------------------------------------------------------------------


def _r4(x: float) -> float:
    return round(float(x), 4)


@traced("quant")
def quant_node(state: GraphState) -> dict:
    reg = EvidenceRegistry("EQ")
    as_of = state.as_of_date
    provider = get_provider()
    info = provider.asset_info()

    tickers = set(state.eligible_universe)
    idea = state.profile.requested_idea if state.profile else None
    focus = idea.get("ticker") if idea else None
    if focus in info.index:
        tickers.add(focus)  # the requested ticker is analysed even if screening excluded it
    tickers = sorted(tickers)

    reg.add(
        "Univers limité aux 31 actifs fournis, tous encore cotés aujourd'hui : biais du "
        "survivant, les statistiques historiques peuvent paraître meilleures que la réalité.",
        source="assets_universe.csv",
        date=as_of,
        method="known limitation of the starter dataset",
        confidence="assumption",
    )
    if not tickers:
        return {"evidence": reg.items(), "summary": "Aucun actif à analyser."}

    prices = provider.prices_cad(tickers, as_of)
    if len(prices) < MIN_OBS + 1:
        reg.add(
            f"Historique trop court au {as_of} ({len(prices)} jours de cotation) : "
            "statistiques de risque non calculées.",
            source=SOURCE,
            date=as_of,
            method=f"minimum {MIN_OBS} daily returns required",
            confidence="assumption",
        )
        return {"evidence": reg.items(), "summary": "Historique insuffisant pour les statistiques."}

    start, end = prices.index[0].date(), prices.index[-1].date()
    window = f"{start}..{end}"
    ppy = periods_per_year(prices.index)

    def add(metric: str, key: str, subject, val: float, method: str) -> None:
        reg.add(
            {"metric": metric, key: subject, "value": _r4(val), "unit": "ratio"},
            source=SOURCE,
            date=end,
            method=method,
        )

    for t in tickers:
        add(
            "volatility_ann", "ticker", t, volatility(prices, t),
            f"annualised std of daily log returns, CAD, {CALENDAR}, {window}, {ppy:.0f} obs/year",
        )
        add(
            "max_drawdown", "ticker", t, max_drawdown(prices, t),
            f"largest peak-to-trough fall of the CAD price, {CALENDAR}, {window}",
        )
        stress = stress_2022(prices, t)
        if stress:
            add(
                "stress_2022", "ticker", t, stress["return"],
                "total return in CAD, 2022-01-03..2022-12-30 (2022 rate-hike episode)",
            )
            add(
                "stress_2022_drawdown", "ticker", t, stress["drawdown"],
                "max drawdown in CAD within 2022-01-03..2022-12-30",
            )

    corr = prices.pct_change(fill_method=None).dropna().corr()
    for a, b in combinations(tickers, 2):
        c = corr.at[a, b]
        if pd.isna(c):
            continue
        if focus in (a, b) or abs(c) >= NOTABLE_CORR:
            add(
                "correlation", "tickers", [a, b], c,
                f"correlation of daily CAD returns, {CALENDAR}, {window}",
            )

    etfs = [t for t in tickers if holdings_weights(t, as_of=as_of)]
    stale = False
    for a, b in combinations(etfs, 2):
        overlap = etf_overlap(a, b, as_of=as_of)
        if overlap is None or overlap <= 0:
            continue
        dates = [d for d in (holdings_date(a, as_of=as_of), holdings_date(b, as_of=as_of)) if d]
        stale = stale or any(d > as_of for d in dates)
        both_complete = is_complete(a, as_of=as_of) and is_complete(b, as_of=as_of)
        method_str = (
            "sum over shared holdings of min(weight in A, weight in B); "
            f"{_holdings_label(a, as_of=as_of)}; {_holdings_label(b, as_of=as_of)}"
        )
        if not both_complete:
            method_str += "; a top-N list gives a lower bound"
        reg.add(
            {"metric": "etf_overlap", "tickers": [a, b], "value": _r4(overlap), "unit": "ratio"},
            source=f"ETF holdings: {a} + {b}",
            date=min(dates) if dates else as_of,
            url=(load_holdings(a, as_of=as_of) or {}).get("source_url"),
            method=method_str,
        )
    if stale:
        reg.add(
            f"Les compositions de FNB utilisées sont postérieures à la date d'analyse ({as_of}) : "
            "le chevauchement réel à cette date pouvait être différent.",
            source="data/cache/holdings",
            date=as_of,
            method="holdings are a single recent snapshot, not point-in-time",
            confidence="assumption",
        )

    return {
        "evidence": reg.items(),
        "summary": f"Statistiques de risque calculées pour {len(tickers)} actifs ({start} au {end}).",
    }
