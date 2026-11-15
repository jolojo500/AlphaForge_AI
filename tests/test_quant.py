"""A-2: quant metrics."""

import datetime as dt
import math

import pandas as pd
import pytest

from alphaforge.data.holdings import holdings_weights
from alphaforge.data.provider import get_provider
from alphaforge.evidence import find, find_one, numeric
from alphaforge.nodes.quant import (
    concentration,
    correlation,
    max_drawdown,
    quant_node,
    returns,
    stress_2022,
    volatility,
)
from alphaforge.state import GraphState, Profile

AS_OF = dt.date(2026, 11, 12)
IDX = pd.bdate_range("2024-01-01", periods=5)
# B is A divided by 2: identical returns.
TOY = pd.DataFrame(
    {"A": [100.0, 110.0, 99.0, 105.0, 120.0], "B": [50.0, 55.0, 49.5, 52.5, 60.0]}, index=IDX
)


def _state(as_of=dt.date(2026, 11, 12), tickers=("RY.TO", "SPY", "TSLA"), idea=None):
    profile = Profile(
        persona="robert",
        objective="capital_preservation",
        horizon_years=4,
        risk_tolerance="low_moderate",
        risk_capacity="low",
        requested_idea=idea,
    )
    return GraphState(
        as_of_date=as_of, persona="robert", profile=profile, eligible_universe=list(tickers)
    )


# --- functions on toy data ----------------------------------------------------------------


def test_max_drawdown_toy():
    assert max_drawdown(TOY, "A") == pytest.approx(99 / 110 - 1)


def test_weights_dict_matches_single_ticker_when_returns_are_identical():
    w = {"A": 0.5, "B": 0.5}
    assert returns(TOY, w).tolist() == pytest.approx(returns(TOY, "A").tolist())
    assert volatility(TOY, w) == pytest.approx(volatility(TOY, "A"))
    assert max_drawdown(TOY, w) == pytest.approx(max_drawdown(TOY, "A"))


def test_correlation_of_identical_returns_is_one():
    assert correlation(TOY, "A", "B") == pytest.approx(1.0)


def test_concentration_on_real_universe():
    info = get_provider().asset_info()
    banks = concentration({"RY.TO": 0.5, "TD.TO": 0.5}, info)
    assert banks["sector_hhi"] == 1.0 and banks["effective_sectors"] == 1.0
    assert banks["us_exposure"] == 0.0 and banks["canada_exposure"] == 1.0
    assert banks["top_weight"] == 0.5 and banks["top_name"] == "RY.TO"
    mixed = concentration({"SPY": 0.5, "RY.TO": 0.5}, info, as_of=AS_OF)
    assert mixed["sector_hhi"] < 0.5  # SPY is spread over its holdings, not one "sector"
    assert mixed["us_exposure"] == pytest.approx(0.5)
    assert mixed["canada_exposure"] == pytest.approx(0.5)
    assert concentration("BTC-USD", info)["us_exposure"] == 0.0


# --- #173: look-through of ETF holdings -----------------------------------------------------


def test_sector_hhi_looks_through_etf_holdings():
    info = get_provider().asset_info()
    spy = concentration({"SPY": 1.0}, info, as_of=AS_OF)
    assert 0 < spy["sector_hhi"] < 1.0  # no longer "its own sector"
    assert spy["effective_sectors"] == pytest.approx(1 / spy["sector_hhi"])
    assert spy["other_sector_share"] > 0  # holdings outside the universe are "Autres"
    # SPY and ESGV overlap almost fully: splitting between them barely changes the HHI,
    # whereas the old sector-label HHI would have halved (0.5 for two "sectors").
    split = concentration({"SPY": 0.5, "ESGV": 0.5}, info, as_of=AS_OF)
    assert abs(split["sector_hhi"] - spy["sector_hhi"]) < 0.05
    assert split["sector_hhi"] > 0.3


def test_country_and_single_name_exposure_look_through():
    info = get_provider().asset_info()
    xiu = concentration({"XIU.TO": 1.0}, info, as_of=AS_OF)
    assert xiu["canada_exposure"] == pytest.approx(1.0) and xiu["us_exposure"] == 0.0
    assert xiu["top_name"] == "RY.TO" and 0 < xiu["top_name_exposure"] < 0.2
    spy_w, qqq_w = holdings_weights("SPY", as_of=AS_OF)["AAPL"], holdings_weights("QQQ", as_of=AS_OF)["AAPL"]
    c = concentration({"AAPL": 0.05, "SPY": 0.5, "QQQ": 0.45}, info, as_of=AS_OF)
    assert c["top_name"] == "AAPL"
    assert c["top_name_exposure"] == pytest.approx(0.05 + 0.5 * spy_w + 0.45 * qqq_w)
    assert c["top_weight"] == pytest.approx(0.5)  # the UI metric keeps its meaning: largest line


# --- real data ----------------------------------------------------------------------------


def test_spy_2022_stress_matches_hand_computation():
    # Hand-computed from the raw CSVs: SPY adj_close x forward-filled USD/CAD, 2022-01-04..12-30.
    prices = get_provider().prices_cad(["SPY"], "2026-11-12")
    s = stress_2022(prices, "SPY")
    assert s["drawdown"] == pytest.approx(-0.2165, abs=0.005)
    assert s["return"] == pytest.approx(-0.1327, abs=0.005)


def test_stress_is_none_when_2022_not_covered():
    prices = get_provider().prices_cad(["SPY"], "2022-06-30")
    assert stress_2022(prices, "SPY") is None


# --- node ---------------------------------------------------------------------------------


def test_node_writes_eq_evidence():
    ev = quant_node(_state())["evidence"]
    assert ev and all(k.startswith("EQ") for k in ev)
    tsla = numeric(find_one(ev, metric="volatility_ann", ticker="TSLA"))
    spy = numeric(find_one(ev, metric="volatility_ann", ticker="SPY"))
    assert tsla > spy > 0
    assert find_one(ev, metric="max_drawdown", ticker="SPY") is not None
    assert find_one(ev, metric="stress_2022", ticker="SPY") is not None
    assert any(e.confidence == "assumption" and "survivant" in str(e.value) for e in ev.values())


def test_node_is_deterministic():
    a = quant_node(_state())["evidence"]
    b = quant_node(_state())["evidence"]
    assert {k: v.model_dump() for k, v in a.items()} == {k: v.model_dump() for k, v in b.items()}


def test_as_of_changes_the_window():
    late = quant_node(_state())["evidence"]
    early = quant_node(_state(as_of=dt.date(2024, 12, 31)))["evidence"]
    v_late = find_one(late, metric="volatility_ann", ticker="SPY")
    v_early = find_one(early, metric="volatility_ann", ticker="SPY")
    assert numeric(v_late) != numeric(v_early)
    assert v_early.date <= dt.date(2024, 12, 31)


def test_short_history_degrades_without_raising():
    ev = quant_node(_state(as_of=dt.date(2021, 12, 15)))["evidence"]
    assert not find(ev, metric="volatility_ann")
    assert any("trop court" in str(e.value) for e in ev.values())


def test_requested_ticker_is_analysed_and_correlated():
    s = _state(tickers=("RY.TO", "SPY"), idea={"ticker": "TSLA", "weight": 0.25})
    ev = quant_node(s)["evidence"]
    assert find_one(ev, metric="volatility_ann", ticker="TSLA") is not None
    corr = find_one(ev, metric="correlation", tickers=["SPY", "TSLA"])
    assert corr is not None and not math.isnan(numeric(corr))
    traded_value = find_one(ev, metric="avg_daily_traded_value_20d_cad", ticker="TSLA")
    assert traded_value is not None and numeric(traded_value) > 0
    assert traded_value.value["observations"] <= 20


def test_usd_exposure_and_effective_sectors():
    from alphaforge.nodes.quant import effective_sectors, usd_exposure

    info = get_provider().asset_info()
    assert usd_exposure({"RY.TO": 0.5, "TD.TO": 0.5}, info) == 0.0
    assert usd_exposure({"SPY": 0.6, "RY.TO": 0.4}, info) == pytest.approx(0.6)
    assert usd_exposure({"BTC-USD": 0.3, "XIU.TO": 0.7}, info) == pytest.approx(0.3)

    eff = effective_sectors({"RY.TO": 0.5, "TD.TO": 0.5}, info)
    assert eff == pytest.approx(1.0)
    eff_two = effective_sectors({"SPY": 0.5, "RY.TO": 0.5}, info, as_of=AS_OF)
    assert eff_two > 2.0  # look-through: more than the two universe labels

