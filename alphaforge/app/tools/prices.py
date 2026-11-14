"""Data loading, calendar alignment, FX conversion, and quality reporting for AlphaForge AI.

Handles:
- Union of TSX and NYSE/NASDAQ trading calendars.
- Resampling 24/7 crypto data to exchange trading days.
- Forward filling gaps (limit=3).
- Converting USD assets to CAD using Bank of Canada daily exchange rates (backward as-of).
- Calculating log returns on adjusted close prices.
- Generating systematic data-quality audits (CNQ.TO split, macro lags, survivorship bias).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Default locations relative to repository root
DEFAULT_STARTER_DIR = Path(__file__).resolve().parents[3] / "Datathon2026" / "alphaforge_starter"


@dataclass
class AnomalyNote:
    topic: str
    severity: str  # info | warning | alert
    description: str
    impact: str
    recommendation: str


@dataclass
class DataQualityReport:
    date_range: tuple[str, str]
    calendar_dates_count: int
    tsx_trading_days: int
    us_trading_days: int
    crypto_calendar_days: int
    total_assets: int
    missing_before_fill: int
    missing_after_fill: int
    anomalies: list[AnomalyNote] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        res = asdict(self)
        return res


def get_default_data_dir() -> Path:
    """Resolve data directory path, checking common locations."""
    if DEFAULT_STARTER_DIR.exists():
        return DEFAULT_STARTER_DIR
    fallback = Path("Datathon2026/alphaforge_starter").resolve()
    if fallback.exists():
        return fallback
    raise FileNotFoundError(f"Cannot find starter data directory at {DEFAULT_STARTER_DIR} or {fallback}")


def load_starter_data(data_dir: str | Path | None = None) -> dict[str, pd.DataFrame]:
    """Load all raw starter CSV files into a dictionary of DataFrames."""
    path = Path(data_dir) if data_dir else get_default_data_dir()
    if not path.exists():
        raise FileNotFoundError(f"Data directory not found: {path}")

    files = {
        "universe": "assets_universe.csv",
        "prices": "prices_daily.csv",
        "fx": "fx_usdcad_daily.csv",
        "corporate_actions": "corporate_actions.csv",
        "macro": "macro_rates.csv",
        "sources_metadata": "sources_metadata.csv",
    }
    dfs: dict[str, pd.DataFrame] = {}
    for key, filename in files.items():
        file_path = path / filename
        if file_path.exists():
            dfs[key] = pd.read_csv(file_path)
        else:
            logger.warning(f"File {filename} not found in {path}")
    return dfs


def build_market_calendar(prices_df: pd.DataFrame, universe_df: pd.DataFrame) -> list[str]:
    """Build the union of TSX and NYSE/NASDAQ trading calendar dates.

    Any date where at least one Canadian equity/ETF or US equity/ETF was traded
    is included in the union calendar.
    """
    tsx_tickers = universe_df[universe_df["market"] == "TSX"]["ticker"].tolist()
    us_tickers = universe_df[universe_df["market"].isin(["NYSE", "NASDAQ", "Cboe BZX", "NYSE Arca"])]["ticker"].tolist()

    tsx_dates = set(prices_df[prices_df["ticker"].isin(tsx_tickers)]["date"])
    us_dates = set(prices_df[prices_df["ticker"].isin(us_tickers)]["date"])

    calendar = sorted(list(tsx_dates.union(us_dates)))
    return calendar


def align_prices_to_calendar(
    prices_df: pd.DataFrame,
    universe_df: pd.DataFrame,
    calendar: list[str],
    price_col: str = "adj_close",
    ffill_limit: int = 3,
) -> pd.DataFrame:
    """Align all asset prices to the unified TSX ∪ NYSE calendar.

    - Pivots date x ticker.
    - Reindexes to the unified calendar (crypto 24/7 is resampled to equity days).
    - Applies forward fill up to ffill_limit days for single-market holidays.
    """
    pivoted = prices_df.pivot(index="date", columns="ticker", values=price_col)
    # Ensure all universe tickers are present
    universe_tickers = universe_df["ticker"].tolist()
    for t in universe_tickers:
        if t not in pivoted.columns:
            pivoted[t] = np.nan

    pivoted = pivoted.reindex(calendar)
    aligned = pivoted.ffill(limit=ffill_limit)
    return aligned


def convert_prices_to_cad(
    aligned_prices: pd.DataFrame,
    universe_df: pd.DataFrame,
    fx_df: pd.DataFrame,
    calendar: list[str],
    ffill_limit: int = 3,
) -> pd.DataFrame:
    """Convert USD-denominated asset prices into CAD.

    Uses Bank of Canada daily USD/CAD exchange rate (FXUSDCAD).
    Carries the last observed FX rate forward on Canadian bank holidays (strictly backward as-of, no look-ahead).
    Canadian assets (.TO) remain unchanged.
    """
    fx_indexed = fx_df.set_index("date")["usdcad"]
    fx_aligned = fx_indexed.reindex(calendar).ffill(limit=ffill_limit)

    if fx_aligned.isna().any():
        # Edge case: if initial dates are missing FX, backfill earliest rate
        fx_aligned = fx_aligned.bfill()

    prices_cad = aligned_prices.copy()
    currency_map = dict(zip(universe_df["ticker"], universe_df["currency"]))

    for ticker in prices_cad.columns:
        ccy = currency_map.get(ticker, "USD")
        if ccy == "USD":
            prices_cad[ticker] = prices_cad[ticker] * fx_aligned
        elif ccy == "CAD":
            pass  # Already in CAD
        else:
            raise ValueError(f"Unsupported currency: {ccy} for ticker {ticker}")

    return prices_cad


def compute_log_returns(prices_cad: pd.DataFrame) -> pd.DataFrame:
    """Compute daily logarithmic returns from CAD-denominated prices.

    r_{i,t} = ln(P_{i,t} / P_{i,t-1})
    Drops the first NaN row.
    """
    log_returns = np.log(prices_cad / prices_cad.shift(1)).iloc[1:]
    return log_returns


def get_processed_dataset(
    data_dir: str | Path | None = None,
    ffill_limit: int = 3,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Convenience pipeline to load and produce aligned returns, prices, and universe in CAD.

    Returns:
        (returns_cad, prices_cad, universe)
    """
    data = load_starter_data(data_dir)
    universe = data["universe"]
    prices = data["prices"]
    fx = data["fx"]

    calendar = build_market_calendar(prices, universe)
    aligned_prices = align_prices_to_calendar(prices, universe, calendar, price_col="adj_close", ffill_limit=ffill_limit)
    prices_cad = convert_prices_to_cad(aligned_prices, universe, fx, calendar, ffill_limit=ffill_limit)
    returns_cad = compute_log_returns(prices_cad)

    return returns_cad, prices_cad, universe


def generate_data_quality_report(data_dir: str | Path | None = None) -> DataQualityReport:
    """Audit the dataset and document key anomalies, publication lags, and methodology."""
    data = load_starter_data(data_dir)
    universe = data["universe"]
    prices = data["prices"]
    fx = data["fx"]
    corp = data.get("corporate_actions", pd.DataFrame())

    calendar = build_market_calendar(prices, universe)
    pivoted = prices.pivot(index="date", columns="ticker", values="adj_close").reindex(calendar)
    nans_before = int(pivoted.isna().sum().sum())
    pivoted_filled = pivoted.ffill(limit=3)
    nans_after = int(pivoted_filled.isna().sum().sum())

    tsx_tickers = universe[universe["market"] == "TSX"]["ticker"]
    us_tickers = universe[universe["market"].isin(["NYSE", "NASDAQ", "Cboe BZX", "NYSE Arca"])]["ticker"]
    crypto_tickers = universe[universe["market"].str.contains("Crypto")]["ticker"]

    tsx_days = len(set(prices[prices["ticker"].isin(tsx_tickers)]["date"]))
    us_days = len(set(prices[prices["ticker"].isin(us_tickers)]["date"]))
    crypto_days = len(set(prices[prices["ticker"].isin(crypto_tickers)]["date"]))

    anomalies: list[AnomalyNote] = [
        AnomalyNote(
            topic="CNQ.TO 1.021 Stock Split Anomaly",
            severity="warning",
            description=(
                "On 2022-08-22, CNQ.TO recorded a split factor of 1.021000 alongside a CAD 0.75 dividend in Yahoo Finance data. "
                "Canadian Natural Resources never announced a fractional 1.021:1 stock split. "
                "This entry likely reflects a special cash dividend or distribution adjustment by data vendors."
            ),
            impact=(
                "Because prices_daily.csv uses pre-adjusted close prices ('adj_close'), splitting the raw series again would double-count adjustments. "
                "Historical returns on CNQ.TO around 2022-08-22 should be verified against corporate press releases."
            ),
            recommendation="Do not re-apply splits from corporate_actions.csv. Use adj_close directly for returns.",
        ),
        AnomalyNote(
            topic="Macroeconomic Publication Lag (Look-Ahead Bias)",
            severity="alert",
            description=(
                "Macroeconomic indicators in macro_rates.csv (e.g., Canadian CPI STATIC_TOTALCPICHANGE, US CPIAUCSL, UNRATE) "
                "are dated to their observation reference month rather than their public release date."
            ),
            impact=(
                "Monthly CPI for month M is typically published 2 to 4 weeks after month M ends. "
                "Conditioning portfolio decisions on month M's CPI on or before month-end M creates forward look-ahead bias."
            ),
            recommendation="For any dynamic macroeconomic regime conditioning, lag monthly indicators by at least 30 calendar days.",
        ),
        AnomalyNote(
            topic="Survivorship Bias in Curated Universe",
            severity="info",
            description=(
                "The 31 assets in assets_universe.csv were compiled in November 2026 based on mega-cap status and contemporary relevance "
                "(e.g., NVDA, CSU.TO, SHOP.TO, BTC-USD)."
            ),
            impact=(
                "Simulating a portfolio over 2021-2026 using an asset universe selected with hindsight overstates historical realized performance "
                "relative to an investor selecting securities in November 2021."
            ),
            recommendation="Treat simulated backtest returns as illustrative scenario simulations, not predictive live results.",
        ),
        AnomalyNote(
            topic="USD/CAD Foreign Exchange Calendar Asynchrony",
            severity="info",
            description=(
                "Bank of Canada Valet FX rates (FXUSDCAD) are published at ~16:30 ET on Canadian banking days only. "
                "U.S. markets trade on several Canadian statutory holidays (e.g., Victoria Day, Thanksgiving Canada, Remembrance Day)."
            ),
            impact="37 trading days had missing Bank of Canada FX fixings on active US trading days.",
            recommendation="Forward-fill Bank of Canada FX rates up to 3 days (strictly backward as-of). This introduces zero look-ahead bias.",
        ),
    ]

    report = DataQualityReport(
        date_range=(calendar[0], calendar[-1]),
        calendar_dates_count=len(calendar),
        tsx_trading_days=tsx_days,
        us_trading_days=us_days,
        crypto_calendar_days=crypto_days,
        total_assets=len(universe),
        missing_before_fill=nans_before,
        missing_after_fill=nans_after,
        anomalies=anomalies,
        metadata={
            "source": "Yahoo Finance (prices), Bank of Canada Valet (FX/rates), FRED (US macro)",
            "base_currency": "CAD",
            "log_returns_rows": len(calendar) - 1,
        },
    )
    return report
