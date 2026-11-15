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


def test_full_lists_for_all_etfs():
    for etf in ("SPY", "XIU.TO", "QQQ", "ESGV"):
        doc = load_holdings(etf)
        assert doc is not None and doc["complete"] is True
    assert len(holdings_weights("SPY")) >= 400
    assert len(holdings_weights("XIU.TO")) >= 55
    assert len(holdings_weights("QQQ")) >= 95
    assert len(holdings_weights("ESGV")) >= 1000
    xiu = holdings_weights("XIU.TO")
    assert all(t.endswith(".TO") for t in xiu)  # universe convention
    assert {"RY.TO", "SHOP.TO", "ENB.TO"} <= xiu.keys()


def test_is_held_respects_partial_lists(tmp_path):
    # A partial list fixture: absence proves nothing (returns None)
    partial_doc = {
        "ticker": "PARTIAL", "as_of": "2026-10-31", "source_url": "https://example.test",
        "complete": False, "holdings": [{"ticker": "AAPL", "name": "Apple", "weight": 0.1}],
    }
    (tmp_path / "PARTIAL.json").write_text(json.dumps(partial_doc), encoding="utf-8")
    assert is_held("PARTIAL", "AAPL", tmp_path) is True
    assert is_held("PARTIAL", "JNJ", tmp_path) is None
    assert is_held("PARTIAL", "XOM", tmp_path) is None

    # Committed ESGV and SPY are complete: absence is a real "False"
    assert is_held("ESGV", "AAPL") is True
    assert is_held("ESGV", "JNJ") is False
    assert is_held("ESGV", "XOM") is False
    assert is_held("SPY", "XOM") is True
    assert is_held("SPY", "RY.TO") is False
    assert is_held("NOPE", "AAPL") is None


def test_dated_snapshots_picked_at_or_before_as_of():
    # QQQ has dated snapshots 2026-03-31 and 2026-06-30
    h_early = load_holdings("QQQ", as_of=dt.date(2026, 5, 1))
    assert h_early is not None and h_early["as_of"] == "2026-03-31"

    h_later = load_holdings("QQQ", as_of=dt.date(2026, 11, 12))
    assert h_later is not None and h_later["as_of"] == "2026-06-30"

    # Future snapshot fallback when as_of is earlier than all snapshots
    h_future = load_holdings("QQQ", as_of=dt.date(2020, 1, 1))
    assert h_future is not None and h_future["as_of"] == "2026-03-31"


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
