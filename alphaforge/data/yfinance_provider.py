"""DataProvider over yfinance (PRD 5.3, A-7, A-13). Track A.

The "refresh the dataset" story for the pitch: the demo runs on CsvProvider (frozen data,
identical numbers at every run, no rate limit on stage).

It inherits CsvProvider and only replaces where prices, FX and corporate actions come from.
Universe metadata (asset class, sector, market) and the macro series stay on the starter CSVs:
yfinance has neither in a consistent form. Frames have the same columns as CsvProvider, so the
calendar, FX and as-of logic of DataProvider apply unchanged.

Resilience guarantees (A-13):
- A single download for all tickers + FX with a hard timeout wall (AF_YF_TIMEOUT_S, default 20s).
- Local disk cache under AF_YF_CACHE_DIR (data/cache/yfinance/) with TTL from AF_YF_CACHE_HOURS (default 12h).
- On any failure, timeout, empty frame, or a ticker with too little history, fall back to the CSV
  data for the WHOLE dataset (never mix sources inside one run) and log a warning once.
- Cache warmed at server start in a background thread.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import threading
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from functools import cached_property
from pathlib import Path

import pandas as pd

from alphaforge import config
from alphaforge.data.csv_provider import CsvProvider
from alphaforge.data.provider import DateLike

logger = logging.getLogger(__name__)

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
PRICE_COLUMNS = [
    "date",
    "ticker",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "currency",
]


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


def extract_fx(raw: pd.DataFrame) -> pd.DataFrame:
    """Extract USD/CAD fx frame from single wide download."""
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["date", "usdcad", "cadusd"])
    if isinstance(raw.columns, pd.MultiIndex):
        if FX_TICKER in raw.columns.get_level_values(1):
            close = raw["Close"][FX_TICKER]
        elif FX_TICKER in raw.columns.get_level_values(0):
            close = raw[FX_TICKER]["Close"]
        else:
            return pd.DataFrame(columns=["date", "usdcad", "cadusd"])
    else:
        close = raw.get("Close")
        if close is None:
            return pd.DataFrame(columns=["date", "usdcad", "cadusd"])

    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    df = pd.DataFrame(
        {"date": _naive_days(close.index).to_numpy(), "usdcad": close.to_numpy()}
    )
    df = df.dropna().drop_duplicates("date", keep="last")
    df["cadusd"] = 1.0 / df["usdcad"]
    return df.sort_values("date", ignore_index=True)


def to_long(
    raw: pd.DataFrame, tickers: list[str], currency: dict[str, str]
) -> pd.DataFrame:
    """yf.download output (wide, any column layout) -> long frame with CsvProvider's columns."""
    if raw is None or raw.empty:
        return pd.DataFrame(columns=PRICE_COLUMNS)

    # Drop FX ticker if present in MultiIndex
    if isinstance(raw.columns, pd.MultiIndex):
        if FX_TICKER in raw.columns.get_level_values(1):
            raw = raw.drop(columns=[FX_TICKER], level=1, errors="ignore")
        elif FX_TICKER in raw.columns.get_level_values(0):
            raw = raw.drop(columns=[FX_TICKER], level=0, errors="ignore")

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
    _fallback_warned = False

    def __init__(
        self,
        root: Path | str | None = None,
        start: DateLike = START,
        end: DateLike | None = None,
        cache_dir: Path | str | None = None,
        cache_hours: float | None = None,
        timeout_s: float | None = None,
    ):
        super().__init__(root)
        self.start = pd.Timestamp(start)
        self.end = (
            pd.Timestamp(end) if end is not None else pd.Timestamp(dt.date.today())
        )
        base_cache = (
            Path(cache_dir)
            if cache_dir is not None
            else Path(os.getenv("AF_YF_CACHE_DIR", str(config.YF_CACHE_DIR)))
        )
        if cache_dir is None and (self.start != pd.Timestamp(START) or end is not None):
            self.cache_dir = base_cache / f"{self.start.date()}_{self.end.date()}"
        else:
            self.cache_dir = base_cache
        self.cache_hours = float(
            cache_hours
            if cache_hours is not None
            else os.getenv("AF_YF_CACHE_HOURS", str(config.YF_CACHE_HOURS))
        )
        self.timeout_s = float(
            timeout_s
            if timeout_s is not None
            else os.getenv("AF_YF_TIMEOUT_S", str(config.YF_TIMEOUT_S))
        )
        self._lock = threading.RLock()
        self._loaded: bool = False
        self._fallback: bool = False
        self._prices_data: pd.DataFrame | None = None
        self._fx_data: pd.DataFrame | None = None
        self.download_date: str | None = None
        self._data_as_of: dt.date = config.DEFAULT_AS_OF

    def _window(self) -> dict:
        # yfinance's `end` is exclusive
        return {
            "start": self.start.date().isoformat(),
            "end": (self.end + pd.Timedelta(days=1)).date().isoformat(),
        }

    def _try_load_cache(self) -> bool:
        meta_file = self.cache_dir / "metadata.json"
        prices_file = self.cache_dir / "prices.csv"
        fx_file = self.cache_dir / "fx.csv"

        if not (meta_file.exists() and prices_file.exists() and fx_file.exists()):
            return False

        try:
            with open(meta_file, encoding="utf-8") as f:
                meta = json.load(f)
            downloaded_at = dt.datetime.fromisoformat(meta["downloaded_at"])
            now = dt.datetime.now(dt.UTC)
            if downloaded_at.tzinfo is None:
                downloaded_at = downloaded_at.replace(tzinfo=dt.UTC)
            age_hours = (now - downloaded_at).total_seconds() / 3600.0
            if age_hours > self.cache_hours:
                return False

            prices_df = pd.read_csv(prices_file, parse_dates=["date"])
            fx_df = pd.read_csv(fx_file, parse_dates=["date"])
            if prices_df.empty or fx_df.empty:
                return False

            # Verify universe tickers
            u = self._universe
            tickers = set(u["ticker"])
            if not tickers.issubset(set(prices_df["ticker"])):
                return False

            self._prices_data = prices_df.sort_values(
                ["ticker", "date"], ignore_index=True
            )
            self._fx_data = fx_df.sort_values("date", ignore_index=True)
            self.fallback = False
            self.download_date = meta.get(
                "download_date", meta["downloaded_at"][:10]
            )
            as_of_val = meta.get("data_as_of")
            if as_of_val:
                self._data_as_of = dt.date.fromisoformat(str(as_of_val)[:10])
            else:
                self._data_as_of = prices_df["date"].max().date()
            return True
        except Exception as e:
            logger.debug("Failed to read cache from %s: %s", self.cache_dir, e)
            return False

    def _save_cache(self, prices_df: pd.DataFrame, fx_df: pd.DataFrame) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            prices_df.to_csv(self.cache_dir / "prices.csv", index=False)
            fx_df.to_csv(self.cache_dir / "fx.csv", index=False)
            now = dt.datetime.now(dt.UTC)
            meta = {
                "downloaded_at": now.isoformat(),
                "download_date": now.date().isoformat(),
                "data_as_of": str(prices_df["date"].max().date()),
                "cache_hours": self.cache_hours,
                "tickers_count": int(prices_df["ticker"].nunique()),
            }
            with open(self.cache_dir / "metadata.json", "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
        except Exception:
            logger.exception("Failed to write yfinance cache to %s", self.cache_dir)

    def _download_all(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        yf = _yf()
        u = self._universe
        tickers = sorted(u["ticker"])
        symbols = tickers + [FX_TICKER]
        window = self._window()

        def do_download():
            return yf.download(
                symbols,
                auto_adjust=False,
                actions=False,
                group_by="column",
                progress=False,
                threads=True,
                timeout=int(self.timeout_s),
                **window,
            )

        with ThreadPoolExecutor(max_workers=1) as executor:
            fut = executor.submit(do_download)
            raw = fut.result(timeout=self.timeout_s)

        if raw is None or raw.empty:
            raise ValueError("yfinance download returned empty frame")

        fx_df = extract_fx(raw)
        if fx_df.empty:
            raise ValueError(f"No FX data for {FX_TICKER}")

        currency_map = dict(zip(u["ticker"], u["currency"], strict=True))
        prices_df = to_long(raw, tickers, currency_map)
        if prices_df.empty:
            raise ValueError("No price records extracted from yfinance")

        present = set(prices_df["ticker"])
        missing = sorted(set(tickers) - present)
        if missing:
            # The threaded batch sometimes drops a symbol (yfinance's own cache reports
            # "database is locked"). Ask again for just those, one at a time, before giving up.
            def retry_missing():
                return yf.download(
                    missing,
                    auto_adjust=False,
                    actions=False,
                    group_by="column",
                    progress=False,
                    threads=False,
                    timeout=int(self.timeout_s),
                    **window,
                )

            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    again = executor.submit(retry_missing).result(timeout=self.timeout_s)
                if again is not None and not again.empty:
                    extra = to_long(again, missing, currency_map)
                    if not extra.empty:
                        prices_df = pd.concat([prices_df, extra], ignore_index=True)
            except Exception as exc:  # the check below reports what is still missing
                logger.warning("yfinance retry for %s failed: %s", missing, exc)
            missing = sorted(set(tickers) - set(prices_df["ticker"]))
        if missing:
            raise ValueError(f"Missing tickers in yfinance data: {missing}")

        counts = prices_df.groupby("ticker")["date"].count()
        max_count = counts.max()
        min_allowed = max(5, int(max_count * 0.5))
        short_tickers = counts[counts < min_allowed].index.tolist()
        if short_tickers:
            raise ValueError(f"Tickers with too little history: {short_tickers}")

        if len(fx_df) < min_allowed:
            raise ValueError(f"FX history too short: {len(fx_df)} rows")

        return prices_df, fx_df

    def _trigger_fallback(self, reason: str) -> None:
        self.fallback = True
        if not YFinanceProvider._fallback_warned:
            logger.warning(
                "yfinance download failed or invalid (%s); falling back to starter CSV dataset for whole run",
                reason,
            )
            YFinanceProvider._fallback_warned = True

        self._prices_data = pd.read_csv(
            self.root / "prices_daily.csv", parse_dates=["date"]
        ).sort_values(["ticker", "date"], ignore_index=True)
        self._fx_data = pd.read_csv(
            self.root / "fx_usdcad_daily.csv", parse_dates=["date"]
        ).sort_values("date", ignore_index=True)
        self._data_as_of = config.DEFAULT_AS_OF
        self.download_date = None

    def _load_or_download(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            _yf()
            if self._try_load_cache():
                self._loaded = True
                return
            try:
                prices_df, fx_df = self._download_all()
                self._save_cache(prices_df, fx_df)
                self._prices_data = prices_df
                self._fx_data = fx_df
                self.fallback = False
                self.download_date = dt.date.today().isoformat()
                self._data_as_of = prices_df["date"].max().date()
                self._loaded = True
            except RuntimeError as e:
                if "yfinance is not installed" in str(e):
                    raise
                self._trigger_fallback(str(e))
                self._loaded = True
            except Exception as e:
                self._trigger_fallback(str(e))
                self._loaded = True

    @property
    def fallback(self) -> bool:
        self._load_or_download()
        return self._fallback

    @fallback.setter
    def fallback(self, value: bool) -> None:
        self._fallback = value

    @property
    def data_as_of(self) -> dt.date:
        self._load_or_download()
        return self._data_as_of

    @property
    def default_as_of(self) -> dt.date:
        self._load_or_download()
        return self._data_as_of

    @property
    def evidence_source(self) -> str:
        self._load_or_download()
        if self._fallback or not self.download_date:
            return "prices_daily.csv + fx_usdcad_daily.csv"
        return f"Yahoo Finance via yfinance, téléchargé le {self.download_date}"

    def warm_cache(self) -> None:
        """Pre-load or download data to disk and memory."""
        self._load_or_download()

    @property
    def _prices(self) -> pd.DataFrame:
        self._load_or_download()
        return self._prices_data

    @property
    def _fx(self) -> pd.DataFrame:
        self._load_or_download()
        return self._fx_data

    def prices(
        self,
        tickers: Iterable[str] | None = None,
        start: DateLike | None = None,
        end: DateLike | None = None,
    ) -> pd.DataFrame:
        self._load_or_download()
        df = self._prices_data
        mask = pd.Series(True, index=df.index)
        if tickers is not None:
            mask &= df["ticker"].isin(list(tickers))
        if start is not None:
            mask &= df["date"] >= pd.Timestamp(start)
        if end is not None:
            mask &= df["date"] <= pd.Timestamp(end)
        return df[mask].reset_index(drop=True)

    def fx(self) -> pd.DataFrame:
        self._load_or_download()
        return self._fx_data.copy()

    def corporate_actions(self) -> pd.DataFrame:
        self._load_or_download()
        if self._fallback:
            df = pd.read_csv(
                self.root / "corporate_actions.csv", parse_dates=["ex_date"]
            )
            return df.sort_values(["ticker", "ex_date"], ignore_index=True)
        try:
            return self._corporate_actions.copy()
        except Exception:
            df = pd.read_csv(
                self.root / "corporate_actions.csv", parse_dates=["ex_date"]
            )
            return df.sort_values(["ticker", "ex_date"], ignore_index=True)

    @cached_property
    def _corporate_actions(self) -> pd.DataFrame:
        yf = _yf()
        u = self._universe.set_index("ticker")
        rows = []
        for t in sorted(u.index):
            try:
                actions = yf.Ticker(t).actions
            except Exception:
                continue
            if actions is None or actions.empty:
                continue
            days = _naive_days(actions.index)
            for day, (_, a) in zip(days, actions.iterrows(), strict=True):
                if not self.start <= day <= self.end:
                    continue
                if a.get("Dividends", 0):
                    rows.append(
                        (
                            day,
                            t,
                            "dividend",
                            float(a["Dividends"]),
                            f"{u.at[t, 'currency']} per share",
                        )
                    )
                if a.get("Stock Splits", 0):
                    rows.append(
                        (day, t, "split", float(a["Stock Splits"]), "ratio")
                    )
        df = pd.DataFrame(
            rows, columns=["ex_date", "ticker", "action", "value", "unit"]
        )
        return df.sort_values(["ticker", "ex_date"], ignore_index=True)
