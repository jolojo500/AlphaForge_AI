import datetime as dt

import pytest

from alphaforge.holdings import (
    build_as_requested_from_current,
    calculate_trades_and_turnover,
    parse_holdings,
    resolve_holdings,
)
from alphaforge.nodes.scenarios import scenarios_node
from alphaforge.state import GraphState, Profile


def test_parse_holdings_dict():
    raw = {"XIU.TO": 50000, "ZST.TO": 50000}
    parsed = parse_holdings(raw)
    assert parsed == {"XIU.TO": 50000.0, "ZST.TO": 50000.0}


def test_parse_holdings_csv():
    csv_text = """
    # My portfolio
    XIU.TO, 60%
    ZST.TO, 40%
    """
    parsed = parse_holdings(csv_text)
    assert parsed == {"XIU.TO": 60.0, "ZST.TO": 40.0}

    # Delimiters with tabs and semicolons and currency signs
    csv_text2 = "AAPL; $50,000\nMSFT\t$30,000\nVCN.TO 20000"
    parsed2 = parse_holdings(csv_text2)
    assert parsed2 == {"AAPL": 50000.0, "MSFT": 30000.0, "VCN.TO": 20000.0}


def test_resolve_holdings_proxies_and_not_analysed():
    universe = {"XIU.TO", "SPY", "QQQ", "ZST.TO", "RY.TO", "TSLA"}
    holdings = {
        "XIU.TO": 40.0,     # direct in universe
        "VCN.TO": 20.0,     # proxy -> XIU.TO
        "CASH": 20.0,       # proxy -> ZST.TO
        "UNKNOWN_CO": 20.0, # not analysed
    }
    mapped_w, proxies, not_analysed, unanalysed_share = resolve_holdings(holdings, universe)

    assert proxies["VCN.TO"] == "XIU.TO"
    assert proxies["CASH"] == "ZST.TO"
    assert not_analysed == ["UNKNOWN_CO"]
    assert unanalysed_share == pytest.approx(0.20)
    # Analyzed portion is 80 (40+20 XIU.TO, 20 ZST.TO).
    # XIU.TO is 60/80 = 75%, ZST.TO is 20/80 = 25%.
    assert mapped_w["XIU.TO"] == pytest.approx(0.75, abs=1e-4)
    assert mapped_w["ZST.TO"] == pytest.approx(0.25, abs=1e-4)
    assert sum(mapped_w.values()) == pytest.approx(1.0, abs=1e-5)


def test_build_as_requested_from_cash():
    # Case 1: Funded entirely from cash
    current = {"XIU.TO": 0.50, "ZST.TO": 0.50}
    # User requests 25% TSLA
    as_req = build_as_requested_from_current(current, "TSLA", 0.25, cash_ticker="ZST.TO")

    assert as_req["TSLA"] == pytest.approx(0.25)
    assert as_req["ZST.TO"] == pytest.approx(0.25)
    assert as_req["XIU.TO"] == pytest.approx(0.50)
    assert sum(as_req.values()) == pytest.approx(1.0)


def test_build_as_requested_partial_cash():
    # Case 2: Partial cash (10% cash, wants 25% TSLA)
    current = {"XIU.TO": 0.90, "ZST.TO": 0.10}
    as_req = build_as_requested_from_current(current, "TSLA", 0.25, cash_ticker="ZST.TO")

    assert as_req["TSLA"] == pytest.approx(0.25)
    assert "ZST.TO" not in as_req  # cash fully used
    # 0.15 was funded from XIU.TO (0.90 - 0.15 = 0.75)
    assert as_req["XIU.TO"] == pytest.approx(0.75)
    assert sum(as_req.values()) == pytest.approx(1.0)


def test_build_as_requested_pro_rata_no_cash():
    # Case 3: No cash (60% XIU.TO, 40% SPY)
    current = {"XIU.TO": 0.60, "SPY": 0.40}
    as_req = build_as_requested_from_current(current, "TSLA", 0.25, cash_ticker="ZST.TO")

    assert as_req["TSLA"] == pytest.approx(0.25)
    # Remaining 75% funded pro rata: 0.60 * 0.75 = 0.45, 0.40 * 0.75 = 0.30
    assert as_req["XIU.TO"] == pytest.approx(0.45)
    assert as_req["SPY"] == pytest.approx(0.30)
    assert sum(as_req.values()) == pytest.approx(1.0)


def test_calculate_trades_and_turnover():
    curr = {"XIU.TO": 0.50, "ZST.TO": 0.50}
    target = {"XIU.TO": 0.50, "ZST.TO": 0.25, "TSLA": 0.25}

    trades, turnover = calculate_trades_and_turnover(curr, target, budget_cad=100_000.0)

    assert turnover == pytest.approx(0.25)  # 25% turnover
    assert len(trades) == 2
    tsla_trade = next(t for t in trades if t["ticker"] == "TSLA")
    zst_trade = next(t for t in trades if t["ticker"] == "ZST.TO")

    assert tsla_trade["action"] == "Achat"
    assert tsla_trade["change"] == pytest.approx(0.25)
    assert tsla_trade["amount_cad"] == pytest.approx(25000.0)

    assert zst_trade["action"] == "Vente"
    assert zst_trade["change"] == pytest.approx(-0.25)
    assert zst_trade["amount_cad"] == pytest.approx(-25000.0)


def test_scenarios_node_with_current_holdings():
    # Judge request for Robert with current holdings
    profile = Profile(
        persona="robert",
        objective="capital_preservation",
        horizon_years=4,
        risk_tolerance="low_moderate",
        risk_capacity="low",
        request_type="judge",
        requested_idea={"ticker": "TSLA", "weight": 0.25},
        current_holdings={"XIU.TO": 50000.0, "ZST.TO": 50000.0},
        budget_cad=100_000.0,
    )
    state = GraphState(
        as_of_date=dt.date(2026, 11, 15),
        persona="robert",
        profile=profile,
        eligible_universe=["XIU.TO", "ZST.TO", "XBB.TO", "RY.TO", "TSLA"],
    )

    out = scenarios_node(state)
    scenarios = out["scenarios"]

    # 4 scenarios: as_requested, capped, profile_baseline, current
    names = [s.name for s in scenarios]
    assert names == ["as_requested", "capped", "profile_baseline", "current"]

    # as_requested has TSLA at 25% funded from ZST.TO
    as_req = next(s for s in scenarios if s.name == "as_requested")
    assert as_req.weights["TSLA"] == pytest.approx(0.25, abs=1e-3)
    assert as_req.weights["XIU.TO"] == pytest.approx(0.50, abs=1e-3)
    assert as_req.weights["ZST.TO"] == pytest.approx(0.25, abs=1e-3)

    # All standard scenarios have turnover and trades
    for s in scenarios[:3]:
        assert s.turnover is not None
        assert s.trades is not None

    # Fourth scenario "current" has the 6 metrics
    current_sc = next(s for s in scenarios if s.name == "current")
    assert "volatility_ann" in current_sc.metrics
    assert "max_drawdown" in current_sc.metrics
    assert "stress_2022" in current_sc.metrics
    assert "top_weight" in current_sc.metrics
    assert "sector_concentration_hhi" in current_sc.metrics
    assert "us_exposure" in current_sc.metrics
