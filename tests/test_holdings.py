"""A-4: ETF holdings cache and overlap."""

import datetime as dt
import json

import pytest

from alphaforge.data.holdings import (
    holdings_date,
    holdings_weights,
    is_held,
    load_holdings,
    look_through,
)
from alphaforge.evidence import find_one, numeric
from alphaforge.nodes.quant import etf_overlap, quant_node
from alphaforge.state import GraphState

ETFS = ("ESGV", "SPY", "QQQ", "XIU.TO")


@pytest.mark.parametrize("etf", ETFS)
def test_cached_files_are_well_formed(etf):
    doc = load_holdings(etf)
    assert doc is not None and doc["ticker"] == etf
    assert doc["source_url"].startswith("https://")
    assert holdings_date(etf) is not None
    weights = holdings_weights(etf)
    assert len(weights) >= 25
    assert all(0 < w <= 1 for w in weights.values())
    assert sum(weights.values()) <= 1.0001


def test_full_lists_for_spy_and_xiu():
    assert load_holdings("SPY")["complete"] and len(holdings_weights("SPY")) >= 400
    xiu = holdings_weights("XIU.TO")
    assert load_holdings("XIU.TO")["complete"] and len(xiu) >= 55
    assert all(t.endswith(".TO") for t in xiu)  # universe convention
    assert {"RY.TO", "SHOP.TO", "ENB.TO"} <= xiu.keys()


def test_is_held_respects_partial_lists():
    assert is_held("ESGV", "AAPL") is True
    # ESGV is cached as its top 25 only: absence proves nothing.
    assert is_held("ESGV", "JNJ") is None
    assert is_held("ESGV", "XOM") is None
    # SPY is complete: absence is a real "no".
    assert is_held("SPY", "XOM") is True
    assert is_held("SPY", "RY.TO") is False
    assert is_held("NOPE", "AAPL") is None


def test_is_held_false_on_a_complete_fixture(tmp_path):
    doc = {"ticker": "ESGV", "as_of": "2026-10-31", "source_url": "https://example.test",
           "complete": True, "holdings": [{"ticker": "AAPL", "name": "Apple", "weight": 0.1}]}
    (tmp_path / "ESGV.json").write_text(json.dumps(doc), encoding="utf-8")
    assert is_held("ESGV", "XOM", tmp_path) is False


def test_spy_qqq_overlap_is_large_and_symmetric():
    o = etf_overlap("SPY", "QQQ")
    assert o == pytest.approx(etf_overlap("QQQ", "SPY"))
    assert 0.3 < o < 1.0
    assert etf_overlap("SPY", "XIU.TO") == 0.0  # no shared listings
    assert etf_overlap("SPY", "NOPE") is None


def test_look_through_adds_direct_and_indirect_exposure():
    qqq_nvda = holdings_weights("QQQ")["NVDA"]
    lt = look_through({"NVDA": 0.10, "QQQ": 0.50, "RY.TO": 0.40})
    assert lt["NVDA"] == pytest.approx(0.10 + 0.50 * qqq_nvda)
    assert lt["RY.TO"] == pytest.approx(0.40)  # not an ETF: unchanged
    assert lt["QQQ:other"] > 0  # unpublished part of the partial QQQ list
    assert sum(lt.values()) == pytest.approx(1.0)


def test_quant_node_writes_overlap_evidence():
    state = GraphState(as_of_date=dt.date(2026, 11, 12), persona="amira",
                       eligible_universe=["QQQ", "RY.TO", "SPY"])
    ev = quant_node(state)["evidence"]
    overlap = find_one(ev, metric="etf_overlap", tickers=["QQQ", "SPY"])
    assert overlap is not None
    assert numeric(overlap) == pytest.approx(round(etf_overlap("SPY", "QQQ"), 4))
    assert overlap.url and overlap.url.startswith("https://")
    assert "as of" in overlap.method


def test_quant_node_flags_holdings_newer_than_as_of():
    state = GraphState(as_of_date=dt.date(2024, 12, 31), persona="amira",
                       eligible_universe=["QQQ", "SPY"])
    ev = quant_node(state)["evidence"]
    assert any("postérieures" in str(e.value) for e in ev.values())
