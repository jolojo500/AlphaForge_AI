"""A-6: scenario builder."""

import datetime as dt

import pytest

from alphaforge.data.provider import get_provider
from alphaforge.evidence import numeric
from alphaforge.nodes.scenarios import scenarios_node
from alphaforge.personas import PERSONAS
from alphaforge.state import SCENARIO_METRICS, SCENARIO_NAMES, Evidence, GraphState, Profile

AS_OF = dt.date(2026, 11, 12)
FIELDS = (
    "objective",
    "horizon_years",
    "risk_tolerance",
    "risk_capacity",
    "constraints",
    "preferences",
    "budget_cad",
    "account_type",
)
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
    assert sc["capped"].weights["TSLA"] == pytest.approx(0.03, abs=TOL)  # capacity low binds (#115)
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


def test_capacity_binds_when_lower_than_tolerance():
    from alphaforge.nodes.scenarios import caps_for
    from alphaforge.state import Profile

    def prof(tol, cap):
        return Profile(persona="custom", objective="growth", horizon_years=10,
                       risk_tolerance=tol, risk_capacity=cap)

    assert caps_for(prof("high", "low"))["crypto_total"] == 0.0
    assert caps_for(prof("high", "low"))["single_stock"] == pytest.approx(0.03)
    assert caps_for(prof("low_moderate", "low"))["equity_max"] == pytest.approx(0.25)  # Robert
    assert caps_for(prof("moderate", "high"))["single_stock"] == pytest.approx(0.07)  # tolerance binds


def _obj(text, eid):
    return [{"scenario": "capped", "objection": text, "evidence": [eid], "severity": "blocking"}]


def test_overlap_objection_caps_only_the_cited_etfs_and_keeps_the_idea_at_the_profile_cap():
    ov = Evidence(id="EQ1", value={"metric": "etf_overlap", "tickers": ["AGG", "XBB.TO"], "value": 0.4},
                  source="test", date=AS_OF, method="test")
    out = _run(ROBERT_TSLA, evidence={"EQ1": ov},
               objections=_obj("Chevauchement entre deux fonds obligataires.", "EQ1"),
               retries={"red_team": 1})
    capped = _by_name(out)["capped"].weights
    assert capped["TSLA"] == pytest.approx(0.03, abs=TOL)  # idea untouched (#116)
    assert capped.get("AGG", 0) <= 0.125 + TOL and capped.get("XBB.TO", 0) <= 0.125 + TOL
    # lines not cited keep the normal ETF cap
    assert max(capped.values()) <= 0.25 + TOL


def test_concentration_objection_reduces_the_cited_line_by_20_percent():
    c = Evidence(id="EQ1", value={"metric": "volatility_ann", "ticker": "ZST.TO", "value": 0.01},
                 source="test", date=AS_OF, method="test")
    out = _run(ROBERT_TSLA, evidence={"EQ1": c},
               objections=_obj("Forte sensibilité aux taux.", "EQ1"), retries={"red_team": 1})
    assert _by_name(out)["profile_baseline"].weights.get("ZST.TO", 0) <= 0.20 + TOL


def test_requested_idea_is_never_dropped_by_an_objection():
    c = Evidence(id="EQ1", value={"metric": "volatility_ann", "ticker": "TSLA", "value": 0.6},
                 source="test", date=AS_OF, method="test")
    out = _run(ROBERT_TSLA, evidence={"EQ1": c},
               objections=_obj("TSLA est trop volatile.", "EQ1"), retries={"red_team": 1})
    assert _by_name(out)["capped"].weights["TSLA"] == pytest.approx(0.03, abs=TOL)


def test_issue_163_as_requested_built_from_question_and_three_questions_differ():
    """Verify #163: as_requested is built from requested_allocation/requested_idea.
    Three different questions produce different as_requested scenarios.
    """
    p_build = Profile(
        persona="mateo", objective="growth", horizon_years=25,
        risk_tolerance="high", risk_capacity="high", request_type="build"
    )
    out_build = _run(p_build)
    w_build = _by_name(out_build)["as_requested"].weights

    p_crypto = Profile(
        persona="mateo", objective="growth", horizon_years=25,
        risk_tolerance="high", risk_capacity="high", request_type="build",
        requested_allocation={"crypto": 0.50}
    )
    out_crypto = _run(p_crypto)
    w_crypto = _by_name(out_crypto)["as_requested"].weights
    crypto_total = w_crypto.get("BTC-USD", 0.0) + w_crypto.get("ETH-USD", 0.0)
    assert crypto_total == pytest.approx(0.50, abs=1e-3)

    p_btc = Profile(
        persona="mateo", objective="growth", horizon_years=25,
        risk_tolerance="high", risk_capacity="high", request_type="build",
        requested_allocation={"BTC-USD": 0.15}
    )
    out_btc = _run(p_btc)
    w_btc = _by_name(out_btc)["as_requested"].weights
    assert w_btc.get("BTC-USD", 0.0) == pytest.approx(0.15, abs=1e-3)

    assert w_build != w_crypto
    assert w_crypto != w_btc
    assert w_build != w_btc


def test_issue_163_missing_asset_generates_gap_evidence():
    """Verify #163: missing requested asset blocks run with clear text."""
    p_bad = Profile(
        persona="mateo", objective="growth", horizon_years=25,
        risk_tolerance="high", risk_capacity="high", request_type="build",
        requested_allocation={"UNKNOWN_TICKER_XYZ": 0.25}
    )
    out = _run(p_bad)
    ev_values = [str(e.value) for e in out["evidence"].values()]
    assert any("Je n'ai pas pu traduire votre demande en portefeuille" in v for v in ev_values)


def test_issue_164_holdings_never_rescaled_and_order_limits():
    """Verify #164: declared BTC 30%, SOL 40%, budget 100 000 $ ->
    BTC move never above 30 000 $, SOL never appears in trades.
    """
    p = Profile(
        persona="mateo", objective="growth", horizon_years=25,
        risk_tolerance="high", risk_capacity="high", request_type="build",
        budget_cad=100000.0,
        current_holdings={"BTC-USD": 0.30, "SOL": 0.40},
    )
    out = _run(p)
    sc_by_name = _by_name(out)
    assert "current" in sc_by_name
    curr_sc = sc_by_name["current"]

    assert curr_sc.weights.get("BTC-USD") == pytest.approx(0.30, abs=1e-4)
    assert "SOL" not in curr_sc.weights

    capped_sc = sc_by_name["capped"]
    assert capped_sc.trades is not None
    tickers_in_trades = {t["ticker"] for t in capped_sc.trades}
    assert "SOL" not in tickers_in_trades

    for trade in capped_sc.trades:
        if trade["ticker"] == "BTC-USD":
            assert abs(trade.get("amount_cad", 0.0)) <= 30000.0 + 1e-2


def test_issue_172_minimum_line_size_and_max_lines():
    """Verify #172: capped and profile_baseline have at most 12 lines,
    no line under 2%, and sum to 1.
    """
    p = Profile(
        persona="mateo", objective="growth", horizon_years=25,
        risk_tolerance="high", risk_capacity="high", request_type="build",
        preferences=["likes_crypto", "prefers_cad"]
    )
    out = _run(p)
    sc_by_name = _by_name(out)

    for sc_name in ("capped", "profile_baseline"):
        sc = sc_by_name[sc_name]
        lines = {t: w for t, w in sc.weights.items() if w > 1e-4}
        assert len(lines) <= 12
        assert all(w >= 0.02 - 1e-6 for w in lines.values())
        assert sum(lines.values()) == pytest.approx(1.0, abs=TOL)


def test_issue_177_high_risk_baseline_recalibration():
    """Verify #177: high-risk growth baseline targets >= 90% equities
    and holds 0% in ultra-short bond ZST.TO.
    """
    p = Profile(
        persona="mateo", objective="growth", horizon_years=25,
        risk_tolerance="high", risk_capacity="high", request_type="build"
    )
    out = _run(p)
    base_sc = _by_name(out)["profile_baseline"]

    assert base_sc.weights.get("ZST.TO", 0.0) == pytest.approx(0.0, abs=1e-6)

    info = get_provider().asset_info()
    eq_share = sum(w for t, w in base_sc.weights.items() if info.at[t, "asset_class"] in ("equity", "etf_equity"))
    assert eq_share >= 0.90 - TOL


def test_issue_174_all_in_cost_evidence():
    """Verify #174: all-in cost and fx conversion cost evidence present."""
    p = Profile(
        persona="mateo", objective="growth", horizon_years=25,
        risk_tolerance="high", risk_capacity="high", request_type="build"
    )
    out = _run(p)
    ev = out["evidence"]

    aic_entries = [e for e in ev.values() if isinstance(e.value, dict) and e.value.get("metric") == "all_in_cost"]
    assert len(aic_entries) >= 3
    for e in aic_entries:
        assert "components" in e.value
        assert "fee_drag" in e.value["components"]
        assert "fx_conversion_cost" in e.value["components"]
        assert "tax_drag" in e.value["components"]
        assert e.value["unit"] == "ratio"



# --- integration fixes after the review of #183, #184 and #185 ------------------------------


def test_single_ticker_allocation_is_treated_as_the_idea():
    """Agent 1 fills both requested_idea and requested_allocation for "25 % dans TSLA": the
    scenarios must be the idea ones (rest on the baseline, idea pinned at the cap), not an
    equal-weight allocation across the universe."""
    both = _profile(
        "robert", request_type="judge",
        requested_idea={"ticker": "TSLA", "weight": 0.25}, requested_allocation={"TSLA": 0.25},
    )
    with_both = _by_name(_run(both))
    idea_only = _by_name(_run(ROBERT_TSLA))
    for name in SCENARIO_NAMES:
        assert with_both[name].weights == pytest.approx(idea_only[name].weights, abs=1e-6)
    assert with_both["capped"].weights["TSLA"] == pytest.approx(0.03, abs=TOL)


def test_dollar_holdings_are_shares_of_the_budget():
    from alphaforge.nodes.scenarios import resolve_current

    info = get_provider().asset_info()
    p = _profile("mateo", budget_cad=100_000, current_holdings={"BTC-USD": 30_000, "SOL": 40_000})
    cur = resolve_current(p, info)
    assert cur["analysed"]["BTC-USD"] == pytest.approx(0.30, abs=1e-6)
    assert cur["unanalysed"]["SOL"] == pytest.approx(0.40, abs=1e-6)
    assert cur["cash"] == pytest.approx(0.30, abs=1e-6)
    # weights whose total is slightly over 1 are rounding, not percentages
    p2 = _profile("mateo", current_holdings={"XIU.TO": 0.34, "XBB.TO": 0.33, "RY.TO": 0.34})
    cur2 = resolve_current(p2, info)
    assert sum(cur2["analysed"].values()) == pytest.approx(1.0, abs=1e-6) and cur2["cash"] == 0


def test_pinned_bond_idea_stays_feasible_under_the_growth_floor():
    p = _profile(
        "amira", objective="growth", risk_tolerance="high", risk_capacity="high",
        request_type="judge", requested_idea={"ticker": "XBB.TO", "weight": 0.15},
    )
    capped = _by_name(_run(p))["capped"].weights
    assert capped["XBB.TO"] == pytest.approx(0.15, abs=TOL)
    assert _share(capped, {"equity", "etf_equity"}) >= 0.85 - 1e-3
    assert sum(capped.values()) == pytest.approx(1.0, abs=1e-6)


# --- #173, #176 and the #186 follow-ups (items 7 and 8) ------------------------------------


def _scenario_evidence(out, metric, scenario):
    return [
        e for e in out["evidence"].values()
        if isinstance(e.value, dict) and e.value.get("metric") == metric and e.value.get("scenario") == scenario
    ]


def test_issue_173_hhi_looks_through_etfs_and_reads_as_effective_sectors():
    out = _run(_profile("amira"))
    for name in SCENARIO_NAMES:
        hhi_ev = out["evidence"][_by_name(out)[name].metrics["sector_concentration_hhi"]]
        assert hhi_ev.value["look_through"] is True
        assert 0 < numeric(hhi_ev) < 1
        assert hhi_ev.value["effective_sectors"] == pytest.approx(1 / numeric(hhi_ev), rel=1e-3)
        assert "secteurs effectifs" in hhi_ev.value["label"]
        assert "looking through ETF holdings" in hhi_ev.method
        assumption = out["evidence"][hhi_ev.value["assumption"]]
        assert assumption.confidence == "assumption"
        assert "répartie également entre les 11 secteurs GICS" in assumption.value
        assert f"({hhi_ev.value['other_sector_share']:.1%})" in assumption.value
        (top_name,) = _scenario_evidence(out, "top_name_exposure", name)
        assert top_name.value["name"] and numeric(top_name) > 0
        (canada,) = _scenario_evidence(out, "canada_exposure", name)
        assert 0 <= numeric(canada) <= 1
    notes = " ".join(_by_name(out)["capped"].notes)
    assert "secteurs effectifs" in notes and "transparence des FNB" in notes


def test_issue_176_long_proxy_companions_and_survivorship_next_to_returns():
    out = _run(_profile("amira", horizon_years=20))
    surv = [
        e for e in out["evidence"].values()
        if e.confidence == "assumption" and isinstance(e.value, str) and "survivant" in e.value
    ]
    assert len(surv) == 1
    surv_id = surv[0].id
    for name in SCENARIO_NAMES:
        sc = _by_name(out)[name]
        for metric in ("max_drawdown_long_proxy", "stress_2000_02_proxy", "stress_2008_proxy"):
            (ev,) = _scenario_evidence(out, metric, name)
            assert ev.confidence == "fact" and numeric(ev) < 0
            assert ev.value["survivorship_note"] == surv_id
            assert "rows <= 2026-11-12 only" in ev.method
            assert ev.date <= AS_OF
        (worst,) = _scenario_evidence(out, "rolling_1y_worst", name)
        assert worst.value["survivorship_note"] == surv_id  # cited beside the historical returns
        assert sc.historical_outcomes["survivorship_evidence"] == surv_id
        lp = sc.historical_outcomes["long_proxy"]
        assert lp["stress_2008_proxy"] < 0 and lp["window"].startswith("1999-01-31")
        assert lp["max_drawdown_long_proxy"] <= lp["stress_2008_proxy_drawdown"]
        notes = " ".join(sc.notes)
        assert f"Biais du survivant : {surv_id}" in notes
        assert "épisode 2008" in notes and "épisode 2000-02" in notes


def test_issue_176_proxies_are_as_of_safe():
    p = _profile("amira")
    state = GraphState(
        as_of_date=dt.date(2024, 6, 28), persona="amira", profile=p, eligible_universe=_eligible(p)
    )
    out = scenarios_node(state)
    for metric in ("max_drawdown_long_proxy", "stress_2000_02_proxy", "stress_2008_proxy"):
        for ev in _scenario_evidence(out, metric, "capped"):
            assert ev.date <= dt.date(2024, 6, 28)
            assert ev.value["window"].endswith("2024-06-30") or ev.value["window"].endswith("2024-05-31")


def test_issue_186_item_7_fx_cost_amortised_over_the_horizon():
    out = _run(_profile("mateo", horizon_years=10))
    for name in SCENARIO_NAMES:
        (ev,) = _scenario_evidence(out, "all_in_cost", name)
        c = ev.value["components"]
        assert c["horizon_years"] == 10.0
        assert c["fx_annualised"] == pytest.approx(c["fx_conversion_cost"] / 10, abs=1e-4)
        assert numeric(ev) == pytest.approx(c["fee_drag"] + c["fx_annualised"] + c["tax_drag"], abs=2e-4)
        assert "amortised over the profile horizon" in ev.method and "FX cost / 10 years" in ev.method


def test_issue_186_item_8_capital_preservation_states_that_the_line_rule_is_skipped():
    robert = _run(_profile("robert"))
    note = next(
        e for e in robert["evidence"].values()
        if isinstance(e.value, str) and e.value.startswith("Lignes des scénarios plafonné")
    )
    assert "préservation du capital" in note.value and "rule skipped for capital_preservation" in note.method
    mateo = _run(_profile("mateo"))
    note_m = next(
        e for e in mateo["evidence"].values()
        if isinstance(e.value, str) and e.value.startswith("Lignes des scénarios plafonné")
    )
    assert "préservation du capital" not in note_m.value
