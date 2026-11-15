"""A-3: macro as-of with publication lags."""

import datetime as dt

import pytest

from alphaforge.evidence import find_one
from alphaforge.nodes.macro import inflation_as_of, macro_node, rates_as_of
from alphaforge.state import GraphState


def test_inflation_known_on_2024_03_05_is_january():
    inf = inflation_as_of(dt.date(2024, 3, 5))
    assert inf["cpi_yoy_ca"]["ref_date"] == dt.date(2024, 1, 1)
    assert inf["cpi_yoy_us"]["ref_date"] == dt.date(2024, 1, 1)
    assert inf["cpi_yoy_ca"]["value"] == pytest.approx(2.9)


def test_us_cpi_yoy_computed_from_index():
    # CPIAUCSL 2024-01 = 309.698, 2023-01 = 300.42 (macro_rates.csv)
    inf = inflation_as_of(dt.date(2024, 3, 5))
    assert inf["cpi_yoy_us"]["value"] == pytest.approx((309.698 / 300.42 - 1) * 100, abs=1e-3)


def test_lags_differ_between_countries():
    inf = inflation_as_of(dt.date(2024, 3, 16))
    assert inf["cpi_yoy_us"]["ref_date"] == dt.date(2024, 2, 1)  # US Feb CPI assumed out 15 March
    assert inf["cpi_yoy_ca"]["ref_date"] == dt.date(2024, 1, 1)  # Canada Feb CPI assumed out 20 March


def test_daily_series_use_previous_business_day():
    r = rates_as_of(dt.date(2024, 3, 5))  # a Tuesday
    assert r["yield_10y_ca"]["ref_date"] == dt.date(2024, 3, 4)
    assert r["yield_10y_us"]["ref_date"] == dt.date(2024, 3, 4)


def test_curve_slope_present_for_ca_and_us():
    r = rates_as_of(dt.date(2024, 3, 5))
    for c in ("ca", "us"):
        expected = r[f"yield_10y_{c}"]["value"] - r[f"yield_2y_{c}"]["value"]
        assert r[f"curve_slope_{c}"]["value"] == pytest.approx(expected)


def _state(as_of):
    return GraphState(as_of_date=as_of, persona="robert")


def test_node_writes_em_evidence():
    ev = macro_node(_state(dt.date(2024, 3, 5)))["evidence"]
    assert ev and all(k.startswith("EM") for k in ev)
    cpi = find_one(ev, metric="cpi_yoy_ca")
    assert cpi.date == dt.date(2024, 1, 1)
    assert cpi.date_kind == "observation"
    assert "published" in cpi.method
    assert find_one(ev, metric="curve_slope_us") is not None


def test_node_before_data_degrades_without_raising():
    ev = macro_node(_state(dt.date(2020, 1, 1)))["evidence"]
    assert find_one(ev, metric="policy_rate_ca") is None
    assert any("non disponible" in str(e.value) for e in ev.values())


def test_node_is_deterministic():
    a = macro_node(_state(dt.date(2024, 3, 5)))["evidence"]
    b = macro_node(_state(dt.date(2024, 3, 5)))["evidence"]
    assert {k: v.model_dump() for k, v in a.items()} == {k: v.model_dump() for k, v in b.items()}
