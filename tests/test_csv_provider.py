"""A-1: DataProvider and CsvProvider."""

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from alphaforge.data.csv_provider import CsvProvider
from alphaforge.data.provider import get_provider

AS_OF = dt.date(2024, 12, 31)


@pytest.fixture(scope="module")
def prov():
    return CsvProvider()


def test_universe_has_31_unique_assets(prov):
    u = prov.universe()
    assert len(u) == 31
    assert u["ticker"].is_unique


def test_prices_filters_tickers_and_inclusive_dates(prov):
    df = prov.prices(["SPY", "RY.TO"], start="2023-01-03", end="2023-12-29")
    assert set(df["ticker"]) == {"SPY", "RY.TO"}
    assert df["date"].min() == pd.Timestamp("2023-01-03")
    assert df["date"].max() == pd.Timestamp("2023-12-29")


def test_prices_cad_has_nothing_after_as_of(prov):
    w = prov.prices_cad(["SPY", "RY.TO", "BTC-USD"], AS_OF)
    assert w.index.max() <= pd.Timestamp(AS_OF)
    assert list(w.columns) == ["BTC-USD", "RY.TO", "SPY"]
    assert not w.isna().any().any()


def test_as_of_on_a_weekend_stops_at_last_trading_day(prov):
    w = prov.prices_cad(["SPY"], dt.date(2024, 12, 29))  # Sunday
    assert w.index.max() == pd.Timestamp("2024-12-27")


def test_usd_asset_on_canadian_holiday_uses_previous_fx(prov):
    # 2024-11-11, Remembrance Day: NYSE and TSX trade, the Bank of Canada publishes no rate.
    day = pd.Timestamp("2024-11-11")
    fx = prov.fx().set_index("date")["usdcad"]
    assert day not in fx.index
    previous_rate = fx[fx.index < day].iloc[-1]

    raw = prov.prices(["SPY"], start=day, end=day)["adj_close"].iloc[0]
    w = prov.prices_cad(["SPY"], AS_OF)
    assert w.loc[day, "SPY"] == pytest.approx(raw * previous_rate)


def test_cad_asset_is_not_converted(prov):
    w = prov.prices_cad(["RY.TO"], AS_OF)
    raw = prov.prices(["RY.TO"], end=AS_OF).set_index("date")["adj_close"]
    assert np.allclose(w["RY.TO"], raw.reindex(w.index))


def test_crypto_aligned_on_equity_calendar(prov):
    w = prov.prices_cad(["SPY", "BTC-USD"], AS_OF)
    assert w["BTC-USD"].notna().sum() == w["SPY"].notna().sum() == len(w)
    assert (w.index.day_of_week < 5).all()


def test_union_calendar_is_a_superset_and_filled(prov):
    common = prov.trading_calendar(AS_OF)
    union = prov.trading_calendar(AS_OF, calendar="union")
    assert len(union) > len(common)
    assert common.isin(union).all()
    w = prov.prices_cad(["SPY", "RY.TO"], AS_OF, calendar="union")
    assert not w.isna().any().any()


def test_start_bounds_the_window(prov):
    w = prov.prices_cad(["SPY"], AS_OF, start="2022-01-01")
    assert w.index.min() >= pd.Timestamp("2022-01-01")


def test_unknown_ticker_raises(prov):
    with pytest.raises(ValueError, match="NOPE"):
        prov.prices_cad(["NOPE"], AS_OF)


def test_callers_cannot_mutate_the_cache(prov):
    df = prov.prices(["SPY"])
    df["adj_close"] = 0.0
    assert prov.prices(["SPY"])["adj_close"].iloc[0] != 0.0


def test_get_provider_defaults_to_csv(monkeypatch):
    monkeypatch.delenv("AF_DATA_PROVIDER", raising=False)
    assert get_provider().name == "csv"
    assert get_provider() is get_provider()
    with pytest.raises(ValueError):
        get_provider("nope")
