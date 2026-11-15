"""A-6: scenario builder."""

import datetime as dt

import pytest

from alphaforge.data.provider import get_provider
from alphaforge.evidence import numeric
from alphaforge.nodes.scenarios import scenarios_node
from alphaforge.personas import PERSONAS
from alphaforge.state import SCENARIO_METRICS, SCENARIO_NAMES, Evidence, GraphState, Profile

AS_OF = dt.date(2026, 11, 12)
FIELDS = ("objective", "horizon_years", "risk_tolerance", "risk_capacity", "constraints", "preferences", "budget_cad")
TOL = 1e-6


def _profile(persona, **override):
    fields = {k: PERSONAS[persona][k] for k in FIELDS} | override
    return Profile(persona=persona, **fields)


def _eligible(profile):
    # Same rules as screening, so this test does not depend on the screening node.
    u = get_provider().universe()
    if "no_crypto" in profile.constraints:
        u = u[u["asset_class"] != "crypto"]
    if "esg_only" in profile.constraints:
        u = u[u["sector"] != "Energy"]
    return sorted(u["ticker"])


def _run(profile, **state_kw):
    state = GraphState(
        as_of_date=AS_OF, persona=profile.persona, profile=profile,
        eligible_universe=_eligible(profile), **state_kw,
    )
    return scenarios_node(state)


def _by_name(out):
    return {s.name: s for s in out["scenarios"]}


def _metric(out, name, metric):
    return numeric(out["evidence"][_by_name(out)[name].metrics[metric]])


def _share(weights, classes):
    info = get_provider().asset_info()
    return sum(w for t, w in weights.items() if info.at[t, "asset_class"] in classes)


ROBERT_TSLA = _profile("robert", request_type="judge", requested_idea={"ticker": "TSLA", "weight": 0.25})


def test_robert_tsla_drawdown_order():
    out = _run(ROBERT_TSLA)
    dd = [abs(_metric(out, n, "max_drawdown")) for n in SCENARIO_NAMES]
    assert dd[0] > dd[1] >= dd[2]


def test_robert_tsla_weights():
    sc = _by_name(_run(ROBERT_TSLA))
    assert sc["as_requested"].weights["TSLA"] == pytest.approx(0.25, abs=TOL)
    assert sc["capped"].weights["TSLA"] == pytest.approx(0.05, abs=TOL)
    assert "TSLA" not in sc["profile_baseline"].weights or sc["profile_baseline"].weights["TSLA"] <= 0.05 + TOL


@pytest.mark.parametrize("persona", sorted(PERSONAS))
def test_weights_are_valid_and_metrics_complete(persona):
    profile = _profile(persona)
    out = _run(profile)
    allowed = set(_eligible(profile))
    assert [s.name for s in out["scenarios"]] == list(SCENARIO_NAMES)
    for s in out["scenarios"]:
        assert sum(s.weights.values()) == pytest.approx(1.0, abs=TOL)
        assert all(w >= 0 for w in s.weights.values())
        assert set(s.weights) <= allowed
        assert set(s.metrics) == set(SCENARIO_METRICS)
        assert all(eid in out["evidence"] for eid in s.metrics.values())
        assert s.notes


def test_amira_crypto_capped_and_equity_floor():
    sc = _by_name(_run(_profile("amira")))
    for name in ("capped", "profile_baseline"):
        assert _share(sc[name].weights, {"crypto"}) <= 0.10 + TOL
    assert _share(sc["profile_baseline"].weights, {"equity", "etf_equity"}) >= 0.80 - TOL


def test_mateo_no_crypto_and_equity_cap():
    sc = _by_name(_run(_profile("mateo")))
    for name in ("capped", "profile_baseline"):
        assert _share(sc[name].weights, {"crypto"}) == 0
        assert _share(sc[name].weights, {"equity", "etf_equity"}) <= 0.70 + TOL


def test_excluded_requested_ticker_only_in_as_requested():
    profile = _profile("robert", request_type="judge", requested_idea={"ticker": "BTC-USD", "weight": 0.2})
    out = _run(profile)
    sc = _by_name(out)
    assert sc["as_requested"].weights["BTC-USD"] == pytest.approx(0.2, abs=TOL)
    assert "BTC-USD" not in sc["capped"].weights
    assert "BTC-USD" not in sc["profile_baseline"].weights
    assert any("BTC-USD" in str(e.value) and e.confidence == "assumption" for e in out["evidence"].values())


def test_retry_with_blocking_objection_changes_weights():
    first = _by_name(_run(ROBERT_TSLA))["profile_baseline"].weights
    top = max(first, key=first.get)
    cited = Evidence(
        id="EQ1", value={"metric": "volatility_ann", "ticker": top, "value": 0.3},
        source="test", date=AS_OF, method="test",
    )
    out = _run(
        ROBERT_TSLA,
        evidence={"EQ1": cited},
        objections=[{"scenario": "profile_baseline", "objection": "x", "evidence": ["EQ1"], "severity": "blocking"}],
        retries={"red_team": 1},
    )
    second = _by_name(out)["profile_baseline"].weights
    assert second != first
    assert top not in second


def test_deterministic():
    a = [s.model_dump() for s in _run(ROBERT_TSLA)["scenarios"]]
    b = [s.model_dump() for s in _run(ROBERT_TSLA)["scenarios"]]
    assert a == b
