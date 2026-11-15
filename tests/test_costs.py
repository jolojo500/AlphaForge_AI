"""Unit tests for fund fees, FX conversion costs and currency risk rules (Issue #119)."""

import datetime as dt

import pytest

from alphaforge.costs import (
    CAPITAL_PRESERVATION_FOREIGN_BOND_CAP,
    ETF_MER_SOURCES,
    ETF_MERS,
    FOREIGN_BOND_URL,
    FX_SPREAD_URL,
    RETAIL_FX_SPREAD,
    calculate_fee_drag,
    capital_preservation_foreign_bond_evidence,
    fx_conversion_evidence,
)
from alphaforge.data.provider import get_provider
from alphaforge.nodes.scenarios import caps_for, scenarios_node
from alphaforge.state import GraphState, Profile


def test_etf_mers_are_all_sourced():
    assert len(ETF_MERS) == 9
    assert set(ETF_MERS.keys()) == set(ETF_MER_SOURCES.keys())
    for ticker, mer in ETF_MERS.items():
        assert 0.0 < mer < 0.01  # MER between 0.03% and 0.40%
        info = ETF_MER_SOURCES[ticker]
        assert info["url"].startswith("https://")
        assert info["issuer"]
        assert info["mer_pct"]


def test_fee_drag_calculation():
    # 50% XIU.TO (0.18%) + 50% SPY (0.0945%) = 0.1373%
    w = {"XIU.TO": 0.5, "SPY": 0.5}
    fee = calculate_fee_drag(w)
    expected = 0.5 * 0.0018 + 0.5 * 0.000945
    assert fee == pytest.approx(round(expected, 4), abs=1e-4)

    # Equities have zero MER
    w_stocks = {"RY.TO": 0.5, "AAPL": 0.5}
    assert calculate_fee_drag(w_stocks) == 0.0


def test_fx_conversion_cost_assumption():
    assert RETAIL_FX_SPREAD == 0.015
    ev = fx_conversion_evidence(dt.date(2026, 11, 12), 0.40, "capped")
    assert ev["confidence"] == "assumption"
    assert ev["url"] == FX_SPREAD_URL
    assert ev["value"]["assumption"] == "fx_conversion_cost"
    assert ev["value"]["retail_spread"] == 0.015
    assert ev["value"]["estimated_fx_drag"] == round(0.40 * 0.015, 4)
    assert "Norbert" in ev["value"]["norberts_gambit"]


def test_capital_preservation_foreign_bond_cap_in_caps_for():
    # Robert is capital_preservation -> foreign_fixed_income_unhedged cap = 0.0
    p_robert = Profile(
        persona="robert",
        objective="capital_preservation",
        horizon_years=4,
        risk_tolerance="low_moderate",
        risk_capacity="low",
    )
    caps_r = caps_for(p_robert)
    assert caps_r.get("foreign_fixed_income_unhedged") == CAPITAL_PRESERVATION_FOREIGN_BOND_CAP
    assert caps_r["foreign_fixed_income_unhedged"] == 0.0

    # Amira is growth -> no foreign fixed income cap
    p_amira = Profile(
        persona="amira",
        objective="growth",
        horizon_years=15,
        risk_tolerance="high",
        risk_capacity="high",
    )
    caps_a = caps_for(p_amira)
    assert "foreign_fixed_income_unhedged" not in caps_a


def test_capital_preservation_evidence():
    ev = capital_preservation_foreign_bond_evidence(dt.date(2026, 11, 12))
    assert ev["confidence"] == "assumption"
    assert ev["url"] == FOREIGN_BOND_URL
    assert ev["value"]["cap"] == 0.0
    assert "AGG" in ev["value"]["reason"]


def test_scenarios_node_includes_fee_drag_and_assumptions():
    prov = get_provider()
    eligible = [t for t in prov.universe()["ticker"] if t not in {"BTC-USD", "ETH-USD"}]
    p = Profile(
        persona="robert",
        objective="capital_preservation",
        horizon_years=4,
        risk_tolerance="low_moderate",
        risk_capacity="low",
        request_type="judge",
        requested_idea={"ticker": "TSLA", "weight": 0.25},
    )
    state = GraphState(
        as_of_date=dt.date(2026, 11, 12),
        persona="robert",
        profile=p,
        eligible_universe=eligible,
    )
    res = scenarios_node(state)
    scenarios = res["scenarios"]
    ev = res["evidence"]

    assert len(scenarios) == 3
    for sc in scenarios:
        assert "fee_drag" in sc.metrics
        eid = sc.metrics["fee_drag"]
        assert eid in ev
        assert ev[eid].confidence == "assumption"
        assert ev[eid].value["metric"] == "fee_drag"
        # Foreign bonds AGG and TLT should be 0.0 in capped and profile_baseline
        if sc.name in ("capped", "profile_baseline"):
            assert sc.weights.get("AGG", 0.0) == 0.0
            assert sc.weights.get("TLT", 0.0) == 0.0

    # Sourced ETF MER entries exist
    etf_mer_entries = [e for e in ev.values() if isinstance(e.value, dict) and e.value.get("metric") == "etf_mer"]
    assert len(etf_mer_entries) == 9

    # Sourced FX conversion entries exist
    fx_entries = [e for e in ev.values() if isinstance(e.value, dict) and e.value.get("assumption") == "fx_conversion_cost"]
    assert len(fx_entries) == 3

    # Foreign bond cap entry exists for capital preservation
    bond_cap_entries = [e for e in ev.values() if isinstance(e.value, dict) and e.value.get("rule") == "foreign_fixed_income_cap"]
    assert len(bond_cap_entries) == 1
