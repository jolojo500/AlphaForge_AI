"""A-5: screening engine."""

import datetime as dt
import json

import pytest

from alphaforge.nodes import screening
from alphaforge.nodes.screening import screening_node
from alphaforge.personas import PERSONAS
from alphaforge.state import GraphState, Profile

AS_OF = dt.date(2026, 11, 12)
FIELDS = ("objective", "horizon_years", "risk_tolerance", "risk_capacity", "constraints", "preferences", "budget_cad")


def _profile(persona, **override):
    fields = {k: PERSONAS[persona][k] for k in FIELDS} | override
    return Profile(persona=persona, **fields)


def _run(profile, holdings_dir, monkeypatch):
    monkeypatch.setattr(screening, "HOLDINGS_DIR", holdings_dir)
    return screening_node(GraphState(as_of_date=AS_OF, persona=profile.persona, profile=profile))


@pytest.fixture
def no_holdings(tmp_path):
    return tmp_path


@pytest.fixture
def esgv_dir(tmp_path):
    held = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA", "JPM", "JNJ"]  # PG left out on purpose
    data = {
        "ticker": "ESGV",
        "as_of": "2026-10-31",
        "source_url": "https://example.test/esgv",
        "retrieved_at": "2026-11-14",
        "holdings": [{"ticker": t, "name": t, "weight": 0.01} for t in held],
    }
    (tmp_path / "ESGV.json").write_text(json.dumps(data), encoding="utf-8")
    return tmp_path


def _excluded(out):
    return {e["ticker"] for e in out["exclusions"]}


def test_amira_keeps_all_31(no_holdings, monkeypatch):
    out = _run(_profile("amira"), no_holdings, monkeypatch)
    assert len(out["eligible_universe"]) == 31
    assert out["exclusions"] == []


def test_robert_excludes_only_crypto_with_reasons(no_holdings, monkeypatch):
    out = _run(_profile("robert"), no_holdings, monkeypatch)
    assert _excluded(out) == {"BTC-USD", "ETH-USD"}
    for e in out["exclusions"]:
        assert e["reason"]
        assert e["evidence_id"] in out["evidence"]


def test_mateo_without_holdings(no_holdings, monkeypatch):
    out = _run(_profile("mateo"), no_holdings, monkeypatch)
    assert {"BTC-USD", "ETH-USD", "ENB.TO", "CNQ.TO", "XOM"} <= _excluded(out)
    assert not {"ENB.TO", "CNQ.TO", "XOM"} & set(out["eligible_universe"])
    assert "RY.TO" in out["eligible_universe"]  # Canadian names are not excluded for absence
    notes = [str(e.value) for e in out["evidence"].values() if e.confidence == "assumption"]
    assert any("ESGV non disponible" in n for n in notes)
    assert any("canadiennes" in n for n in notes)


def test_mateo_with_esgv_holdings(esgv_dir, monkeypatch):
    out = _run(_profile("mateo"), esgv_dir, monkeypatch)
    pg = next(e for e in out["exclusions"] if e["ticker"] == "PG")
    ev = out["evidence"][pg["evidence_id"]]
    assert ev.url == "https://example.test/esgv"
    assert ev.date == dt.date(2026, 10, 31)
    assert "AAPL" in out["eligible_universe"]
    assert [e["ticker"] for e in out["exclusions"]].count("XOM") == 1  # one reason per ticker


def test_partial_esgv_list_does_not_exclude_absent_names(tmp_path, monkeypatch):
    data = {
        "ticker": "ESGV", "as_of": "2026-09-30", "source_url": "https://example.test/esgv",
        "complete": False, "total_holdings": 1220,
        "holdings": [{"ticker": t, "name": t, "weight": 0.01} for t in ("AAPL", "MSFT")],
    }
    (tmp_path / "ESGV.json").write_text(json.dumps(data), encoding="utf-8")
    out = _run(_profile("mateo"), tmp_path, monkeypatch)
    assert {"JNJ", "PG", "AAPL"} <= set(out["eligible_universe"])  # unknown, not excluded
    assert "XOM" not in out["eligible_universe"]  # still excluded by the energy rule
    notes = [str(e.value) for e in out["evidence"].values() if e.confidence == "assumption"]
    assert any("JNJ" in n and "principales positions" in n for n in notes)


def test_mateo_with_committed_holdings():
    out = screening_node(GraphState(as_of_date=AS_OF, persona="mateo", profile=_profile("mateo")))
    assert {"AAPL", "JNJ", "PG"} <= set(out["eligible_universe"])
    assert not {"XOM", "ENB.TO", "CNQ.TO", "BTC-USD", "ETH-USD"} & set(out["eligible_universe"])


def test_whatif_excluded_ticker(no_holdings, monkeypatch):
    out = _run(_profile("amira", excluded_tickers=["XIU.TO"]), no_holdings, monkeypatch)
    assert "XIU.TO" not in out["eligible_universe"]
    assert _excluded(out) == {"XIU.TO"}


def test_requested_ticker_excluded_is_flagged(no_holdings, monkeypatch):
    profile = _profile("robert", request_type="judge", requested_idea={"ticker": "BTC-USD", "weight": 0.2})
    out = _run(profile, no_holdings, monkeypatch)
    btc = next(e for e in out["exclusions"] if e["ticker"] == "BTC-USD")
    assert btc.get("requested") is True
    assert "BTC-USD" in out["trace"][0]["summary"]


def test_deterministic(no_holdings, monkeypatch):
    a = _run(_profile("mateo"), no_holdings, monkeypatch)
    b = _run(_profile("mateo"), no_holdings, monkeypatch)
    assert a["exclusions"] == b["exclusions"]
    assert list(a["evidence"]) == list(b["evidence"])
