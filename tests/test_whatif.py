import datetime as dt

import pytest

from alphaforge import whatif
from alphaforge.graph import run
from alphaforge.personas import PERSONAS
from alphaforge.whatif import WhatIfError, apply_change, diff_scenarios, parse_change, rerun, rerun_inputs


@pytest.fixture
def first():
    return run("robert", PERSONAS["robert"]["example_request"])


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("horizon_years", "10", 10),
        ("budget_cad", 50000, 50000.0),
        ("risk_tolerance", "high", "high"),
        ("exclude_ticker", " XIU.TO ", "XIU.TO"),
        ("as_of_date", "2025-06-30", dt.date(2025, 6, 30)),
    ],
)
def test_parse_change_normalises(field, value, expected):
    assert parse_change(field, value).value == expected


@pytest.mark.parametrize(
    "field,value",
    [
        ("horizon_years", 0), ("horizon_years", "abc"), ("horizon_years", 99),
        ("budget_cad", -5), ("risk_tolerance", "reckless"), ("exclude_ticker", "NOPE"),
        ("as_of_date", "2030-01-01"), ("as_of_date", "2020-01-01"), ("as_of_date", "not a date"),
        ("persona", "amira"), ("weight", 0.1),
    ],
)
def test_parse_change_rejects_bad_values(field, value):
    with pytest.raises(WhatIfError):
        parse_change(field, value)


def test_apply_change_changes_exactly_one_thing_and_does_not_mutate(first):
    p = first.profile
    before = p.model_dump()
    q = apply_change(p, "horizon_years", 12)
    assert p.model_dump() == before
    diff = {k for k in q.model_dump() if q.model_dump()[k] != before[k]}
    assert diff == {"horizon_years"}
    r = apply_change(q, "exclude_ticker", "SPY")
    r = apply_change(r, "exclude_ticker", "SPY")
    assert r.excluded_tickers == ["SPY"]


def test_rerun_inputs_skip_agent_one_and_keep_request(first):
    inputs = rerun_inputs(first, "risk_tolerance", "high")
    assert inputs["profile"].risk_tolerance == "high"
    assert inputs["request_text"] == first.request_text and inputs["as_of_date"] == first.as_of_date
    assert rerun_inputs(first, "as_of_date", "2025-01-02")["as_of_date"] == dt.date(2025, 1, 2)


def test_rerun_requires_a_profile(first):
    with pytest.raises(WhatIfError):
        rerun_inputs(first.model_copy(update={"profile": None}), "horizon_years", 5)


def test_rerun_excludes_asset_and_skips_profile_node(first):
    new = rerun(first, "exclude_ticker", "XIU.TO")
    assert "profile" not in {t["node"] for t in new.trace}
    assert "XIU.TO" not in new.eligible_universe
    d = diff_scenarios(first, new)
    assert d["eligible_universe"] == {"added": [], "removed": ["XIU.TO"]}
    assert d["profile"]["excluded_tickers"] == {"old": [], "new": ["XIU.TO"]}


def test_diff_of_identical_runs_is_empty(first):
    d = diff_scenarios(first, first)
    assert d["profile"] == {} and d["eligible_universe"] == {"added": [], "removed": []}
    assert all(not s["weights"] for s in d["scenarios"].values())
    assert all(m["delta"] == 0 for s in d["scenarios"].values() for m in s["metrics"].values())
    assert d["most_coherent"]["changed"] is False


def test_diff_reports_weights_metrics_and_best_change(first):
    new = first.model_copy(deep=True)
    sc = new.scenarios[0]
    sc.weights = {**sc.weights, "SPY": sc.weights.get("SPY", 0) + 0.1}
    eid = sc.metrics["volatility_ann"]
    new.evidence[eid] = new.evidence[eid].model_copy(update={"value": {"metric": "volatility_ann", "value": 0.5}})
    new.explanation = {**new.explanation, "scenario_le_plus_coherent": "as_requested"}
    d = diff_scenarios(first, new)
    s0 = d["scenarios"][sc.name]
    assert s0["weights"]["SPY"]["delta"] == pytest.approx(0.1)
    vol = s0["metrics"]["volatility_ann"]
    assert vol["new"] == 0.5 and vol["delta"] == pytest.approx(0.5 - vol["old"])
    assert d["most_coherent"] == {"old": "capped", "new": "as_requested", "changed": True}


def test_fields_constant_matches_parser():
    assert set(whatif.FIELDS) == {"horizon_years", "budget_cad", "risk_tolerance", "exclude_ticker", "as_of_date"}
