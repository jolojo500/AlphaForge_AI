"""Persona acceptance tests (PRD 7), end to end through the real graph.

Offline by default: LLM nodes take their deterministic fallback (AF_LLM_OFFLINE=1 from
conftest), every other node is the real implementation on the starter data. The `live`
variant runs the same assertions with Bedrock.
"""

from __future__ import annotations

import pytest

from alphaforge.data.provider import get_provider
from alphaforge.evidence import find, numeric
from alphaforge.graph import run
from alphaforge.personas import PERSONAS
from alphaforge.state import SCENARIO_METRICS, SCENARIO_NAMES, GraphState
from alphaforge.whatif import rerun

CRYPTO = {"BTC-USD", "ETH-USD"}


def _scenarios(s: GraphState) -> dict:
    return {sc.name: sc for sc in s.scenarios}


def _metric(s: GraphState, scenario: str, metric: str) -> float:
    return numeric(s.evidence[_scenarios(s)[scenario].metrics[metric]])


def _weight(s: GraphState, scenario: str, tickers: set[str]) -> float:
    return sum(w for t, w in _scenarios(s)[scenario].weights.items() if t in tickers)


def _equity_tickers() -> set[str]:
    info = get_provider().asset_info()
    return set(info.index[info["asset_class"] == "equity"])


@pytest.fixture(scope="module")
def runs() -> dict[str, GraphState]:
    return {p: run(p, PERSONAS[p]["example_request"]) for p in ("amira", "mateo", "robert")}


def _common_contract(s: GraphState) -> None:
    assert [sc.name for sc in s.scenarios] == list(SCENARIO_NAMES)
    for sc in s.scenarios:
        assert sum(sc.weights.values()) == pytest.approx(1.0, abs=1e-6)
        assert min(sc.weights.values()) >= 0
        assert set(sc.metrics) >= set(SCENARIO_METRICS)
        assert all(eid in s.evidence for eid in sc.metrics.values())
    assert s.verification["passed"] is True, s.verification
    assert s.explanation["scenario_le_plus_coherent"] in SCENARIO_NAMES
    assert s.explanation["avertissement"]
    for ex in s.exclusions:
        assert ex["reason"] and ex["evidence_id"] in s.evidence
    assert {k[:2] for k in s.evidence} >= {"EQ", "EM", "EP"}


def test_amira_diversified_growth_with_capped_crypto(runs):
    s = runs["amira"]
    _common_contract(s)
    assert s.profile.request_type == "build"
    assert len(s.eligible_universe) == 31 and not s.exclusions
    # crypto allowed but capped
    assert _weight(s, "capped", CRYPTO) <= 0.10 + 1e-6
    assert _weight(s, "profile_baseline", CRYPTO) <= 0.10 + 1e-6
    # overlap flagged with a source
    overlap = find(s.evidence, metric="etf_overlap", tickers=["QQQ", "SPY"])
    assert overlap and overlap[0].url
    # three genuinely different scenarios
    vols = [_metric(s, n, "volatility_ann") for n in SCENARIO_NAMES]
    assert len({round(v, 3) for v in vols}) == 3


def test_mateo_esg_balanced(runs):
    s = runs["mateo"]
    _common_contract(s)
    excluded = {e["ticker"] for e in s.exclusions}
    assert CRYPTO | {"ENB.TO", "CNQ.TO", "XOM"} <= excluded
    for sc in s.scenarios:
        assert not (set(sc.weights) & excluded)
    equity = _equity_tickers()
    for name in ("capped", "profile_baseline"):
        assert _weight(s, name, equity) <= 0.70 + 1e-6
    assert _metric(s, "profile_baseline", "volatility_ann") <= min(
        _metric(s, n, "volatility_ann") for n in ("as_requested", "capped")
    )


def test_robert_tsla_is_challenged_not_refused(runs):
    s = runs["robert"]
    _common_contract(s)
    p = s.profile
    assert p.request_type == "judge"
    assert p.requested_idea == {"ticker": "TSLA", "weight": 0.25}
    assert p.conflicts and not any("_" in c for c in p.conflicts), "conflicts must be French text"
    assert CRYPTO <= {e["ticker"] for e in s.exclusions}

    assert _weight(s, "as_requested", {"TSLA"}) == pytest.approx(0.25)
    assert _weight(s, "capped", {"TSLA"}) <= 0.03 + 1e-6  # low capacity binds (#115)
    dd = {n: _metric(s, n, "max_drawdown") for n in SCENARIO_NAMES}
    assert dd["as_requested"] < dd["capped"] <= dd["profile_baseline"] + 1e-9
    stress = {n: _metric(s, n, "stress_2022") for n in SCENARIO_NAMES}
    assert stress["as_requested"] < stress["capped"]
    # a comparison, never a refusal: the requested scenario is shown, another is preferred
    assert s.explanation["scenario_le_plus_coherent"] != "as_requested"


def test_whatif_changes_the_answer_coherently(runs):
    base = runs["robert"]
    # Raising tolerance alone does not loosen anything: Robert's low capacity binds (#115).
    bolder = rerun(base, ("risk_tolerance", "high"))
    assert "profile" not in {t["node"] for t in bolder.trace}
    assert _weight(bolder, "capped", {"TSLA"}) == pytest.approx(_weight(base, "capped", {"TSLA"}))
    # With capacity raised too, the caps loosen to the high-risk single-stock cap.
    looser = rerun(bolder, ("risk_capacity", "high"))
    assert _weight(looser, "capped", {"TSLA"}) > _weight(base, "capped", {"TSLA"})
    assert _weight(looser, "capped", {"TSLA"}) <= 0.10 + 1e-6

    without = rerun(base, ("exclude_ticker", "AGG"))
    assert "AGG" not in without.eligible_universe
    assert all("AGG" not in sc.weights for sc in without.scenarios)
    assert without.verification["passed"] is True


def test_persona_runs_are_deterministic_offline(runs):
    again = run("robert", PERSONAS["robert"]["example_request"])
    first = runs["robert"]
    assert sorted(again.evidence) == sorted(first.evidence)
    for a, b in zip(again.scenarios, first.scenarios, strict=True):
        assert a.weights == pytest.approx(b.weights)


@pytest.mark.live
@pytest.mark.parametrize("persona", ["robert", "amira", "mateo"])
def test_live_persona_passes_verifier_first_time(persona):
    s = run(persona, PERSONAS[persona]["example_request"])
    _common_contract(s)
    assert s.retries.get("explain", 0) == 0, s.verification
    assert "gabarit" not in next(t["summary"] for t in s.trace if t["node"] == "explain")
