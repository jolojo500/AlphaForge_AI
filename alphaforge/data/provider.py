"""Data provider interface and the as-of-safe helpers built on it (PRD 5.3). Track A.

Providers only load raw data. Calendar alignment, FX conversion and as-of filtering are
concrete methods of the base class, so they behave the same whatever the source
(starter CSVs now, yfinance later).
"""

from __future__ import annotations

import datetime as dt
import functools
import os
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Literal

import pandas as pd

Calendar = Literal["common", "union"]
DateLike = dt.date | str | pd.Timestamp


class DataProvider(ABC):
    """Every frame returned uses pandas Timestamps in its `date` (or `ex_date`) column."""

    name: str = "abstract"
    fallback: bool = False

    @property
    def evidence_source(self) -> str:
        return "prices_daily.csv + fx_usdcad_daily.csv"

    @property
    def default_as_of(self) -> dt.date:
        from alphaforge import config

        return config.DEFAULT_AS_OF

    @property
    def data_as_of(self) -> dt.date:
        from alphaforge import config

        return config.DEFAULT_AS_OF

    # --- raw access, implemented by each provider ---------------------------------------

    @abstractmethod
    def universe(self, include_custom: Iterable[str] | None = None) -> pd.DataFrame:
        """One row per asset: asset_id, ticker, name, asset_class, market, currency, sector."""

    @abstractmethod
    def prices(
        self,
        tickers: Iterable[str] | None = None,
        start: DateLike | None = None,
        end: DateLike | None = None,
    ) -> pd.DataFrame:
        """Long frame: date, ticker, open, high, low, close, adj_close, volume, currency.

        `start` and `end` are inclusive.
        """

    @abstractmethod
    def fx(self) -> pd.DataFrame:
        """date, usdcad, cadusd. Bank of Canada publication days only (gaps on CA holidays)."""

    @abstractmethod
    def macro(self) -> pd.DataFrame:
        """Long frame: date, series_id, value, unit, frequency, label, source."""

    @abstractmethod
    def corporate_actions(self) -> pd.DataFrame:
        """ex_date, ticker, action, value, unit."""

    # --- shared, as-of-safe helpers -----------------------------------------------------

    def asset_info(self, include_custom: Iterable[str] | None = None) -> pd.DataFrame:
        """The universe indexed by ticker."""
        return self.universe(include_custom=include_custom).set_index("ticker")

    def trading_calendar(
        self, as_of: DateLike, start: DateLike | None = None, calendar: Calendar = "common"
    ) -> pd.DatetimeIndex:
        """Equity trading days up to `as_of` (crypto never defines the calendar).

        common: days on which both the TSX (CAD listings) and the US exchanges traded.
                Returns between two consecutive days are then true multi-day returns,
                with no artificial zero return from a closed market.
        union:  days on which either traded. A closed market carries its last price.
        """
        info = self.asset_info()
        equities = info.index[info["asset_class"] != "crypto"]
        px = self.prices(equities, start=start, end=as_of)
        px["market_ccy"] = px["ticker"].map(info["currency"])
        per_market = [set(g["date"]) for _, g in px.groupby("market_ccy")]
        if not per_market:
            return pd.DatetimeIndex([], name="date")
        days = set.intersection(*per_market) if calendar == "common" else set.union(*per_market)
        return pd.DatetimeIndex(sorted(days), name="date")

    def usdcad_on(self, dates: pd.DatetimeIndex) -> pd.Series:
        """USD/CAD for each date, forward-filled from the last published rate (never ahead)."""
        fx = self.fx().set_index("date")["usdcad"].sort_index()
        full = fx.reindex(fx.index.union(dates)).ffill()
        return full.reindex(dates)

    def prices_cad(
        self,
        tickers: Iterable[str],
        as_of: DateLike,
        start: DateLike | None = None,
        calendar: Calendar = "common",
        field: str = "adj_close",
    ) -> pd.DataFrame:
        """Wide frame (index date, one column per ticker, sorted) of `field` in CAD.

        - only data dated <= as_of (and >= start if given)
        - aligned on the equity trading calendar, so crypto weekends are dropped
        - USD prices converted with the forward-filled USD/CAD rate of the same day
        - `adj_close` is already split and dividend adjusted: no corporate action is
          re-applied (the CNQ.TO pseudo-split of 2022-08-22 is already in it)
        """
        tickers = sorted(set(tickers))
        info = self.asset_info(include_custom=tickers)
        unknown = [t for t in tickers if t not in info.index]
        if unknown:
            raise ValueError(f"unknown tickers: {unknown}")

        as_of = pd.Timestamp(as_of)
        cal = self.trading_calendar(as_of, start, calendar)
        raw = self.prices(tickers, start=start, end=as_of)
        wide = raw.pivot(index="date", columns="ticker", values=field)
        wide = wide.reindex(index=cal, columns=tickers).ffill()

        usd = [t for t in tickers if info.at[t, "currency"] == "USD"]
        if usd:
            wide[usd] = wide[usd].mul(self.usdcad_on(cal), axis=0)
        wide.columns.name = None
        return wide


def get_provider(name: str | None = None) -> DataProvider:
    """The configured provider (env AF_DATA_PROVIDER, default csv), one instance per name."""
    return _provider((name or os.getenv("AF_DATA_PROVIDER", "csv")).strip().lower())


@functools.cache
def _provider(name: str) -> DataProvider:
    if name == "csv":
        from alphaforge.data.csv_provider import CsvProvider

        return CsvProvider()
    if name == "yfinance":
        from alphaforge.data.yfinance_provider import YFinanceProvider

        return YFinanceProvider()
    raise ValueError(f"unknown data provider {name!r}; available: csv, yfinance")


def clear_provider_cache() -> None:
    """Clear the cached singleton provider instance (useful in tests)."""
    _provider.cache_clear()
