"""DataProvider over the starter CSVs (PRD 5.3). Track A. Default provider for the demo."""

from __future__ import annotations

from collections.abc import Iterable
from functools import cached_property
from pathlib import Path

import pandas as pd

from alphaforge import config
from alphaforge.data.market_db import get_custom_assets_df, get_custom_prices_df
from alphaforge.data.provider import DataProvider, DateLike


class CsvProvider(DataProvider):
    """Reads `Datathon2026/alphaforge_starter/` once and keeps the frames in memory.

    Every public method returns a copy, so callers can modify what they get.
    """

    name = "csv"

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root is not None else config.STARTER_DIR

    # --- cached raw frames --------------------------------------------------------------

    @cached_property
    def _universe(self) -> pd.DataFrame:
        return pd.read_csv(self.root / "assets_universe.csv")

    @cached_property
    def _prices(self) -> pd.DataFrame:
        df = pd.read_csv(self.root / "prices_daily.csv", parse_dates=["date"])
        return df.sort_values(["ticker", "date"], ignore_index=True)

    @cached_property
    def _fx(self) -> pd.DataFrame:
        df = pd.read_csv(self.root / "fx_usdcad_daily.csv", parse_dates=["date"])
        return df.sort_values("date", ignore_index=True)

    @cached_property
    def _macro(self) -> pd.DataFrame:
        df = pd.read_csv(self.root / "macro_rates.csv", parse_dates=["date"])
        return df.sort_values(["series_id", "date"], ignore_index=True)

    @cached_property
    def _corporate_actions(self) -> pd.DataFrame:
        df = pd.read_csv(self.root / "corporate_actions.csv", parse_dates=["ex_date"])
        return df.sort_values(["ticker", "ex_date"], ignore_index=True)

    # --- DataProvider -------------------------------------------------------------------

    def universe(self, include_custom: Iterable[str] | None = None) -> pd.DataFrame:
        base = self._universe.copy()
        if include_custom:
            custom = get_custom_assets_df(tickers=list(include_custom))
            if not custom.empty:
                custom_new = custom[~custom["ticker"].isin(base["ticker"])]
                if not custom_new.empty:
                    base = pd.concat([base, custom_new], ignore_index=True)
        return base

    def prices(
        self,
        tickers: Iterable[str] | None = None,
        start: DateLike | None = None,
        end: DateLike | None = None,
    ) -> pd.DataFrame:
        df = self._prices
        if tickers is not None:
            t_list = list(tickers)
            custom_tickers = [t for t in t_list if t not in set(self._universe["ticker"])]
            if custom_tickers:
                custom_df = get_custom_prices_df(tickers=custom_tickers)
                if not custom_df.empty:
                    df = pd.concat([df, custom_df], ignore_index=True)
        else:
            custom_df = get_custom_prices_df()
            if not custom_df.empty:
                df = pd.concat([df, custom_df], ignore_index=True)

        mask = pd.Series(True, index=df.index)
        if tickers is not None:
            mask &= df["ticker"].isin(list(tickers))
        if start is not None:
            mask &= df["date"] >= pd.Timestamp(start)
        if end is not None:
            mask &= df["date"] <= pd.Timestamp(end)
        return df[mask].reset_index(drop=True)

    def fx(self) -> pd.DataFrame:
        return self._fx.copy()

    def macro(self) -> pd.DataFrame:
        return self._macro.copy()

    def corporate_actions(self) -> pd.DataFrame:
        return self._corporate_actions.copy()
