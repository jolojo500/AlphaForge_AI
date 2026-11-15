"""A-7: YFinanceProvider. Offline tests use a fake yfinance module; the live test needs network."""

import datetime as dt
import sys
import types

import numpy as np
import pandas as pd
import pytest

from alphaforge.data.csv_provider import CsvProvider
from alphaforge.data.provider import get_provider
from alphaforge.data.yfinance_provider import YFinanceProvider, to_long

DAYS = pd.bdate_range("2026-11-02", "2026-11-12")
FIELDS = ["Adj Close", "Close", "High", "Low", "Open", "Volume"]


def _fake_download(tickers, **kwargs):
    """Mimic yf.download(group_by="column"): columns MultiIndex (Price, Ticker)."""
    tickers = [tickers] if isinstance(tickers, str) else list(tickers)
    cols = pd.MultiIndex.from_product([FIELDS, tickers], names=["Price", "Ticker"])
    data = np.tile(np.arange(len(DAYS), dtype=float)[:, None] + 100.0, (1, len(cols)))
    if tickers == ["CAD=X"]:
        data[:] = 1.40
    return pd.DataFrame(data, index=pd.DatetimeIndex(DAYS, name="Date"), columns=cols)


class _FakeTicker:
    def __init__(self, ticker):
        idx = pd.DatetimeIndex([DAYS[3]], tz="America/New_York")
        self.actions = pd.DataFrame({"Dividends": [0.5 if ticker == "SPY" else 0.0], "Stock Splits": [0.0]}, index=idx)


@pytest.fixture
def fake_yf(monkeypatch):
    mod = types.ModuleType("yfinance")
    mod.download = _fake_download
    mod.Ticker = _FakeTicker
    monkeypatch.setitem(sys.modules, "yfinance", mod)
    return mod


def test_prices_have_the_same_shape_as_csv(fake_yf):
    yp = YFinanceProvider(end="2026-11-12")
    got = yp.prices(["SPY", "RY.TO"])
    want = CsvProvider().prices(["SPY", "RY.TO"])
    assert list(got.columns) == list(want.columns)
    assert set(got["ticker"]) == {"SPY", "RY.TO"}
    assert got.loc[got["ticker"] == "RY.TO", "currency"].eq("CAD").all()
    assert pd.api.types.is_datetime64_any_dtype(got["date"])
    assert len(got) == 2 * len(DAYS)


def test_fx_and_prices_cad_work_end_to_end(fake_yf):
    yp = YFinanceProvider(end="2026-11-12")
    fx = yp.fx()
    assert list(fx.columns) == ["date", "usdcad", "cadusd"]
    assert fx["usdcad"].eq(1.40).all()
    w = yp.prices_cad(["SPY", "RY.TO", "BTC-USD"], "2026-11-12")
    assert not w.isna().any().any()
    assert w["SPY"].iloc[0] == pytest.approx(100.0 * 1.40)  # USD converted with CAD=X
    assert w["RY.TO"].iloc[0] == pytest.approx(100.0)  # CAD untouched


def test_universe_and_macro_come_from_the_starter_csvs(fake_yf):
    yp = YFinanceProvider(end="2026-11-12")
    assert yp.universe().equals(CsvProvider().universe())
    assert yp.macro().equals(CsvProvider().macro())


def test_corporate_actions_from_ticker_actions(fake_yf):
    ca = YFinanceProvider(end="2026-11-12").corporate_actions()
    assert list(ca.columns) == ["ex_date", "ticker", "action", "value", "unit"]
    spy = ca[ca["ticker"] == "SPY"]
    assert spy["action"].tolist() == ["dividend"] and spy["value"].tolist() == [0.5]
    assert spy["ex_date"].iloc[0] == DAYS[3]  # timezone dropped


def test_to_long_accepts_flat_and_ticker_first_layouts():
    flat = _fake_download("SPY").droplevel("Ticker", axis=1)
    assert set(to_long(flat, ["SPY"], {"SPY": "USD"})["ticker"]) == {"SPY"}
    ticker_first = _fake_download(["SPY", "QQQ"]).swaplevel(0, 1, axis=1)
    long = to_long(ticker_first, ["QQQ", "SPY"], {"SPY": "USD", "QQQ": "USD"})
    assert set(long["ticker"]) == {"SPY", "QQQ"} and long["adj_close"].notna().all()


def test_missing_yfinance_gives_a_clear_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "yfinance", None)
    with pytest.raises(RuntimeError, match="yfinance"):
        YFinanceProvider(end="2026-11-12").prices(["SPY"])


def test_get_provider_selects_yfinance(fake_yf):
    assert get_provider("yfinance").name == "yfinance"  # nothing downloaded until used


@pytest.mark.live
def test_live_spy_month_matches_csv():
    pytest.importorskip("yfinance")
    start, end = dt.date(2026, 10, 1), dt.date(2026, 10, 30)
    live = YFinanceProvider(start=start, end=end).prices(["SPY"]).set_index("date")["close"]
    csv = CsvProvider().prices(["SPY"], start=start, end=end).set_index("date")["close"]
    both = pd.concat([live, csv], axis=1, keys=["live", "csv"]).dropna()
    assert len(both) >= 15
    assert ((both["live"] / both["csv"] - 1).abs() < 0.005).all()
