"""Unit tests for the What-if engine (C-4)."""

import datetime as dt

import pytest

from alphaforge.graph import run
from alphaforge.personas import PERSONAS
from alphaforge.whatif import apply_change, diff_scenarios, rerun


def test_apply_change_fields():
    state = run("robert", PERSONAS["robert"]["example_request"])
    prof = state.profile
    assert prof is not None

    # Horizon years
    p1 = apply_change(prof, "horizon_years", 8)
    assert p1.horizon_years == 8

    # Budget CAD
    p2 = apply_change(prof, "budget_cad", 50000.0)
    assert p2.budget_cad == 50000.0

    # Risk tolerance
    p3 = apply_change(prof, "risk_tolerance", "high")
    assert p3.risk_tolerance == "high"

    # Exclude ticker
    p4 = apply_change(prof, "exclude_ticker", "AAPL")
    assert "AAPL" in p4.excluded_tickers

    # as_of_date returns profile unchanged
    p5 = apply_change(prof, "as_of_date", "2024-01-01")
    assert p5 == prof

    with pytest.raises(ValueError):
        apply_change(prof, "unknown_field", "val")


def test_whatif_robert_tolerance_loosens_caps():
    # Robert initial run (tolerance low_moderate -> capped at 5%)
    initial_state = run("robert", PERSONAS["robert"]["example_request"])
    capped_init = next(s for s in initial_state.scenarios if s.name == "capped")
    assert capped_init.weights["TSLA"] == pytest.approx(0.05)

    # Rerun with risk_tolerance -> high
    new_state = rerun(initial_state, {"field": "risk_tolerance", "value": "high"})
    assert new_state.profile.risk_tolerance == "high"

    # Profile node was skipped (enters at screening)
    assert "profile" not in {t["node"] for t in new_state.trace}

    # Caps loosen: TSLA in capped increases to 10%
    capped_new = next(s for s in new_state.scenarios if s.name == "capped")
    assert capped_new.weights["TSLA"] == pytest.approx(0.10)
    assert sum(capped_new.weights.values()) == pytest.approx(1.0)


def test_whatif_exclude_ticker_disappears():
    initial_state = run("robert", PERSONAS["robert"]["example_request"])
    assert "TSLA" in initial_state.eligible_universe

    # Exclude TSLA
    new_state = rerun(initial_state, {"field": "exclude_ticker", "value": "TSLA"})
    assert "TSLA" in new_state.profile.excluded_tickers
    assert "TSLA" not in new_state.eligible_universe
    assert any(e["ticker"] == "TSLA" for e in new_state.exclusions)

    # TSLA disappears from all three scenarios
    for sc in new_state.scenarios:
        assert "TSLA" not in sc.weights
        assert sum(sc.weights.values()) == pytest.approx(1.0)


def test_whatif_as_of_date_rerun():
    initial_state = run("mateo", PERSONAS["mateo"]["example_request"])
    new_date = dt.date(2023, 6, 1)
    new_state = rerun(initial_state, ("as_of_date", new_date))
    assert new_state.as_of_date == new_date


def test_diff_scenarios():
    initial_state = run("robert", PERSONAS["robert"]["example_request"])
    new_state = rerun(initial_state, {"field": "risk_tolerance", "value": "high"})

    diff = diff_scenarios(initial_state, new_state)
    assert "scenarios" in diff
    assert "capped" in diff["scenarios"]

    capped_weights_diff = diff["scenarios"]["capped"]["weights"]
    assert "TSLA" in capped_weights_diff
    assert capped_weights_diff["TSLA"]["old"] == pytest.approx(0.05)
    assert capped_weights_diff["TSLA"]["new"] == pytest.approx(0.10)
    assert capped_weights_diff["TSLA"]["delta"] == pytest.approx(0.05)

    assert len(diff["summary"]) > 0
    assert any("TSLA" in line for line in diff["summary"])
