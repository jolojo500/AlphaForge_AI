"""Tests for alphaforge.app.tools.etf_overlap."""

from __future__ import annotations

import pytest

from alphaforge.app.tools.etf_overlap import overlap, look_through, load_fund_holdings


def test_holdings_load():
    df = load_fund_holdings()
    assert not df.empty
    assert {"etf", "holding_ticker", "holding_name", "weight", "as_of_date", "source_url", "retrieved_date"}.issubset(df.columns)
    assert "XIU.TO" in set(df["etf"])


def test_overlap_same_etf_positive():
    val = overlap("XIU.TO", "XIU.TO")
    assert 0 < val <= 1.0


def test_overlap_disjoint_low():
    # A single stock vs a different single stock -> 0
    assert overlap("AAPL", "MSFT") == 0.0


def test_overlap_stock_in_etf():
    # AAPL is a holding of SPY
    val = overlap("AAPL", "SPY")
    assert val > 0


def test_look_through_direct_only():
    pw = {"AAPL": 0.5, "MSFT": 0.5}
    eff = look_through(pw)
    assert eff["AAPL"] == 0.5
    assert eff["MSFT"] == 0.5


def test_look_through_expands_etf():
    pw = {"SPY": 0.4, "AAPL": 0.6}
    eff = look_through(pw)
    assert "AAPL" in eff
    # SPY expanded into underlying holdings (e.g. MSFT/NVDA)
    assert any(k not in ("AAPL",) for k in eff.keys())
    assert eff["AAPL"] >= 0.6


def test_look_through_no_nan():
    pw = {"XIU.TO": 1.0}
    eff = look_through(pw)
    assert all(isinstance(v, (int, float)) for v in eff.values())
    assert sum(eff.values()) > 0
