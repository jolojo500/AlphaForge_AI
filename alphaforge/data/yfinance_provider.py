"""DataProvider over yfinance (PRD 5.3, A-7). Track A.

The "refresh the dataset" story for the pitch: the demo runs on CsvProvider (frozen data,
identical numbers at every run, no rate limit on stage).

It inherits CsvProvider and only replaces where prices, FX and corporate actions come from.
Universe metadata (asset class, sector, market) and the macro series stay on the starter CSVs:
yfinance has neither in a consistent form. Frames have the same columns as CsvProvider, so the
calendar, FX and as-of logic of DataProvider apply unchanged.

Differences from the starter data, worth stating when it is used:
- FX is Yahoo's CAD=X close (every weekday), not the Bank of Canada daily rate.
- Adjusted closes are adjusted as of the download date, so history shifts slightly after
  each new dividend.

yfinance is imported lazily: the package works without it installed (it is not a project
dependency yet, see issue A-7).
"""

from __future__ import annotations

import datetime as dt
from functools import cached_property
from pathlib import Path

import pandas as pd

from alphaforge.data.csv_provider import CsvProvider
from alphaforge.data.provider import DateLike

START = "2021-11-12"  # same first day as the starter dataset
FX_TICKER = "CAD=X"  # USD/CAD on Yahoo Finance
PRICE_FIELDS = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adj_close",
    "Volume": "volume",
}
PRICE_COLUMNS = ["date", "ticker", "open", "high", "low", "close", "adj_close", "volume", "currency"]


def _yf():
    try:
        import yfinance
    except ImportError as e:
        raise RuntimeError(
            "yfinance is not installed; add it to the environment to use AF_DATA_PROVIDER=yfinance"
        ) from e
    return yfinance


def _naive_days(index) -> pd.Series:
    d = pd.to_datetime(pd.Series(index))
    if d.dt.tz is not None:
        d = d.dt.tz_localize(None)
    return d.dt.normalize()


def to_long(raw: pd.DataFrame, tickers: list[str], currency: dict[str, str]) -> pd.DataFrame:
    """yf.download output (wide, any column layout) -> long frame with CsvProvider's columns."""
    if raw is None or raw.empty:
        return pd.DataFrame(columns=PRICE_COLUMNS)
    if not isinstance(raw.columns, pd.MultiIndex):  # single ticker, flat columns
        raw = pd.concat({tickers[0]: raw}, axis=1)
    if set(PRICE_FIELDS) & set(raw.columns.get_level_values(1)):  # (ticker, field) layout
        raw = raw.swaplevel(0, 1, axis=1)
    long = raw.stack(level=1, future_stack=True)
    long.index = long.index.set_names(["date", "ticker"])
    long = long.reset_index().rename(columns=PRICE_FIELDS)
    for col in PRICE_FIELDS.values():
        if col not in long:
            long[col] = float("nan")
    long = long.dropna(subset=["adj_close"])
    long["date"] = _naive_days(long["date"]).to_numpy()
    long["currency"] = long["ticker"].map(currency)
    return long[PRICE_COLUMNS].sort_values(["ticker", "date"], ignore_index=True)


class YFinanceProvider(CsvProvider):
    name = "yfinance"

    def __init__(
        self,
        root: Path | str | None = None,
        start: DateLike = START,
        end: DateLike | None = None,
    ):
        super().__init__(root)
        self.start = pd.Timestamp(start)
        self.end = pd.Timestamp(end) if end is not None else pd.Timestamp(dt.date.today())

    def _window(self) -> dict:
        # yfinance's `end` is exclusive
        return {
            "start": self.start.date().isoformat(),
            "end": (self.end + pd.Timedelta(days=1)).date().isoformat(),
        }

    @cached_property
    def _prices(self) -> pd.DataFrame:
        u = self._universe
        tickers = sorted(u["ticker"])
        raw = _yf().download(
            tickers, auto_adjust=False, actions=False, group_by="column",
            progress=False, threads=True, **self._window(),
        )
        return to_long(raw, tickers, dict(zip(u["ticker"], u["currency"], strict=True)))

    @cached_property
    def _fx(self) -> pd.DataFrame:
        raw = _yf().download(FX_TICKER, auto_adjust=False, progress=False, **self._window())
        if raw is None or raw.empty:
            return pd.DataFrame(columns=["date", "usdcad", "cadusd"])
        close = raw["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        df = pd.DataFrame({"date": _naive_days(close.index).to_numpy(), "usdcad": close.to_numpy()})
        df = df.dropna().drop_duplicates("date", keep="last")
        df["cadusd"] = 1.0 / df["usdcad"]
        return df.sort_values("date", ignore_index=True)

    @cached_property
    def _corporate_actions(self) -> pd.DataFrame:
        yf = _yf()
        u = self._universe.set_index("ticker")
        rows = []
        for t in sorted(u.index):
            actions = yf.Ticker(t).actions
            if actions is None or actions.empty:
                continue
            days = _naive_days(actions.index)
            for day, (_, a) in zip(days, actions.iterrows(), strict=True):
                if not self.start <= day <= self.end:
                    continue
                if a.get("Dividends", 0):
                    rows.append((day, t, "dividend", float(a["Dividends"]), f"{u.at[t, 'currency']} per share"))
                if a.get("Stock Splits", 0):
                    rows.append((day, t, "split", float(a["Stock Splits"]), "ratio"))
        df = pd.DataFrame(rows, columns=["ex_date", "ticker", "action", "value", "unit"])
        return df.sort_values(["ticker", "ex_date"], ignore_index=True)
