"""#176: long index proxies for drawdown and stress episodes (2000-02, 2008)."""

import datetime as dt

import pandas as pd
import pytest

from alphaforge.data.index_history import (
    EPISODES,
    INDEX_FILE,
    load_index_history,
    proxy_drawdown,
    proxy_label,
    proxy_shares,
    proxy_stress,
    proxy_value,
)
from alphaforge.data.provider import get_provider

AS_OF = dt.date(2026, 11, 12)
US_EQUITY = {"equity_us": 1.0, "equity_ca": 0.0, "bond": 0.0, "other": 0.0}


def test_committed_csv_is_read_and_as_of_safe():
    assert INDEX_FILE.exists()
    full = load_index_history()
    assert list(full.columns) == ["GSPC", "GSPTSE", "AGG"]
    assert full.index[0] == pd.Timestamp("1999-01-31")
    early = load_index_history(dt.date(2009, 3, 15))
    assert early.index[-1] == pd.Timestamp("2009-02-28")  # nothing after the as-of date
    assert len(early) < len(full)
    assert load_index_history(dt.date(1990, 1, 1)).empty


def test_bond_gap_before_2003_is_documented_and_held_flat():
    hist = load_index_history(AS_OF)
    assert hist["AGG"].first_valid_index() == pd.Timestamp("2003-09-30")
    bonds = {"equity_us": 0.0, "equity_ca": 0.0, "bond": 1.0, "other": 0.0}
    v = proxy_value(hist.loc[:"2003-08-31"], bonds)
    assert (v == 1.0).all()  # no data: the bond sleeve neither gains nor loses
    assert "flat before 2003-09" in proxy_label(bonds)


def test_2008_stress_matches_hand_computation_on_sp500():
    # S&P 500 month-end closes: 1549.38 (2007-10-31) -> 735.09 (2009-02-28)
    hist = load_index_history(AS_OF)
    s = proxy_stress(hist, US_EQUITY, "stress_2008")
    assert s["return"] == pytest.approx(735.09 / 1549.38 - 1, abs=1e-4)
    assert s["drawdown"] == pytest.approx(s["return"], abs=1e-6)  # the trough is the end of the episode
    dotcom = proxy_stress(hist, US_EQUITY, "stress_2000_02")
    assert dotcom["return"] == pytest.approx(815.28 / 1498.58 - 1, abs=1e-4)
    assert proxy_drawdown(hist, US_EQUITY) <= s["drawdown"]  # the 2008 fall is within the long drawdown


def test_stress_is_none_when_the_episode_is_not_covered():
    hist = load_index_history(dt.date(2008, 6, 30))
    assert proxy_stress(hist, US_EQUITY, "stress_2008") is None
    assert proxy_stress(hist, US_EQUITY, "stress_2000_02") is not None
    assert set(EPISODES) == {"stress_2000_02", "stress_2008"}


def test_proxy_shares_map_scenario_weights():
    info = get_provider().asset_info()
    shares = proxy_shares({"SPY": 0.4, "RY.TO": 0.2, "XBB.TO": 0.3, "GLD": 0.1}, info)
    assert shares == {"equity_us": 0.4, "equity_ca": 0.2, "bond": 0.3, "other": 0.1}
    mixed = proxy_shares({"SPY": 0.5, "XBB.TO": 0.5}, info)
    hist = load_index_history(AS_OF)
    assert proxy_drawdown(hist, mixed) > proxy_drawdown(hist, US_EQUITY)  # bonds soften the fall


def test_loader_reads_a_tiny_fixture_without_network(tmp_path):
    fixture = tmp_path / "idx.csv"
    fixture.write_text(
        "date,GSPC,GSPTSE,AGG\n2020-01-31,100,200,\n2020-02-29,90,180,\n2020-03-31,80,160,50\n",
        encoding="utf-8",
    )
    hist = load_index_history(dt.date(2020, 2, 29), path=fixture)
    assert len(hist) == 2
    v = proxy_value(hist, US_EQUITY)
    assert v.iloc[-1] == pytest.approx(0.9)
