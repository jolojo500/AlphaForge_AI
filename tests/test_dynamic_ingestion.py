"""Dynamic asset ingestion (#188): candidates, the off-by-default switch, timeouts, and the
same screening / guardrail / quant rules on an ingested asset. No network: a fake yfinance
module is injected in sys.modules, the DB is a temporary file."""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
import types

import numpy as np
import pandas as pd
import pytest

from alphaforge import config
from alphaforge.data import dynamic_ingestion as di
from alphaforge.data import market_db
from alphaforge.data.market_db import get_custom_assets_df, get_custom_prices_df, save_custom_asset
from alphaforge.data.provider import get_provider
from alphaforge.guardrails import check_guardrails
from alphaforge.nodes.profile import _regex_extract, _resolve_ticker
from alphaforge.nodes.quant import (
    max_drawdown,
    quant_node,
    rolling_returns_stats,
    stress_2022,
    stress_2022_note,
    value,
)
from alphaforge.nodes.scenarios import scenario_metrics
from alphaforge.nodes.screening import screening_node
from alphaforge.state import GraphState, Profile, Scenario

AS_OF = dt.date(2026, 11, 12)


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """An empty market.db and an empty cache mirror of its own for the test; no S3 bucket."""
    monkeypatch.setattr(config, "MARKET_DB_PATH", tmp_path / "market.db", raising=False)
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "S3_BUCKET", None)
    monkeypatch.delenv("AF_S3_BUCKET", raising=False)
    monkeypatch.setattr(market_db, "_s3_client_override", None)
    from alphaforge.data.market_db import init_market_db

    init_market_db()
    return tmp_path / "market.db"


class _FakeS3:
    """Records put_object calls like the stub of tests/test_trace_store.py; can be made to fail."""

    def __init__(self, fail=False):
        self.objects: dict[str, bytes] = {}
        self.fail = fail

    def put_object(self, Bucket, Key, Body, ContentType):
        if self.fail:
            raise RuntimeError("S3 unavailable")
        assert ContentType == "application/json"
        self.objects[f"{Bucket}/{Key}"] = Body


def _fake_yf(monkeypatch, *, quote_type="EQUITY", name="Palantir Technologies", sector="Technology",
             exchange="NMS", currency="USD", start="2021-11-15", delay=0.0, raise_on=None):
    """A yfinance stand-in; records every call so tests can assert there was none."""
    calls: list[str] = []
    mod = types.ModuleType("yfinance")

    class _Ticker:
        def __init__(self, symbol):
            calls.append(f"Ticker:{symbol}")
            self.symbol = symbol

        @property
        def info(self):
            if raise_on == "info":
                raise RuntimeError("boom")
            d = {"quoteType": quote_type, "shortName": name, "exchange": exchange, "currency": currency}
            if sector is not None:
                d["sector"] = sector
            return d

    def _download(symbol, start=None, end=None, progress=False):
        calls.append(f"download:{symbol}")
        if delay:
            time.sleep(delay)
        if raise_on == "download":
            raise RuntimeError("network down")
        idx = pd.bdate_range(start, "2026-11-12")
        px = 10.0 + np.arange(len(idx)) * 0.01
        return pd.DataFrame(
            {"Open": px, "High": px, "Low": px, "Close": px, "Adj Close": px, "Volume": 1000.0}, index=idx
        ).rename_axis("Date")

    mod.Ticker = _Ticker
    mod.download = _download
    monkeypatch.setitem(sys.modules, "yfinance", mod)
    return calls


# --- 1. candidates ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Je veux un portefeuille équilibré et responsable, orienté ESG, dans mon CELI et mon REER.",
        "Mettre 20 % en FNB ETF en USD et CAD, le reste en CELIAPP",
        "I want to build a balanced ESG portfolio with a 10-year horizon.",
        "Un IPO avec un bon HHI et un PEA en EUR",
        "ticker ESG",  # marked, but a finance acronym
    ],
)
def test_acronyms_are_never_candidates(text):
    assert di.resolve_candidate_symbol(text) is None
    assert _regex_extract(text).ticker is None


@pytest.mark.parametrize(
    "text, want",
    [
        ("Je veux mettre 10 % dans l'action PLTR", "PLTR"),
        ("le titre pltr est-il une bonne idée ?", "PLTR"),
        ("acheter $COIN pour 5 %", "COIN"),
        ("shares of RBLX", "RBLX"),
        ("l'ETF ARKK", "ARKK"),
        ("le FNB HXT.TO", "HXT.TO"),
        ("symbole : MSTR", "MSTR"),
        ("un peu de dogecoin", "DOGE-USD"),
        ("l'action Palantir", "PLTR"),
        ("du DOGE à 5 %", "DOGE-USD"),
    ],
)
def test_marked_tokens_and_aliases_are_candidates(text, want):
    assert di.resolve_candidate_symbol(text) == want


def test_short_aliases_need_capitals_or_a_marker():
    assert di.resolve_candidate_symbol("placer l'argent au sol et le point sur ada") is None
    assert di.resolve_candidate_symbol("l'action SOL") == "SOL-USD"


def test_universe_ticker_is_never_overridden():
    assert di.resolve_candidate_symbol("l'action NVDA et le titre SHOP") == "NVDA"
    assert di.resolve_candidate_symbol("le titre SHOP") == "SHOP.TO"
    assert _regex_extract("Mettre 10 % dans l'action NVDA").ticker == "NVDA"
    assert _regex_extract("Mettre 10 % en bitcoin, pas d'ESG").ticker == "BTC-USD"


# --- 2. off by default, timeout, failures -------------------------------------------------


def test_off_by_default_no_network_and_asset_stays_outside(tmp_db, monkeypatch):
    monkeypatch.delenv("AF_DYNAMIC_INGESTION", raising=False)
    calls = _fake_yf(monkeypatch)
    assert di.ingestion_enabled() is False
    assert di.ensure_requested_asset("Mettre 10 % dans l'action PLTR") is None
    assert di.ensure_ticker_in_db("PLTR") is None
    assert _resolve_ticker("PLTR") is None
    assert _regex_extract("Mettre 10 % dans l'action PLTR").ticker is None
    assert calls == []
    assert get_custom_assets_df().empty


def test_off_hides_previously_ingested_assets(tmp_db, monkeypatch):
    monkeypatch.setenv("AF_DYNAMIC_INGESTION", "on")
    _fake_yf(monkeypatch)
    assert di.ensure_ticker_in_db("PLTR") == "PLTR"
    monkeypatch.setenv("AF_DYNAMIC_INGESTION", "off")
    assert di.ensure_ticker_in_db("PLTR") is None
    assert get_custom_assets_df().empty
    assert "PLTR" not in set(get_provider().universe(include_custom=["PLTR"])["ticker"])


def test_on_downloads_once_and_persists_fields(tmp_db, monkeypatch):
    monkeypatch.setenv("AF_DYNAMIC_INGESTION", "on")
    calls = _fake_yf(monkeypatch)
    assert di.ensure_requested_asset("Mettre 10 % dans l'action PLTR") == "PLTR"
    assert calls == ["Ticker:PLTR", "download:PLTR"]
    df = get_custom_assets_df(["PLTR"]).set_index("ticker")
    assert df.at["PLTR", "asset_class"] == "equity"
    assert df.at["PLTR", "market"] == "NASDAQ"
    assert df.at["PLTR", "currency"] == "USD"
    assert df.at["PLTR", "sector"] == "Technology"
    assert df.at["PLTR", "asset_id"] == "DYN_PLTR"
    assert str(df.at["PLTR", "retrieved_at"]).startswith("20")
    # second call: served from the DB, no network
    assert di.ensure_requested_asset("l'action PLTR") == "PLTR"
    assert calls == ["Ticker:PLTR", "download:PLTR"]
    assert _resolve_ticker("PLTR") == "PLTR"


@pytest.mark.parametrize(
    "kwargs, want_class, want_sector",
    [
        ({"quote_type": "CRYPTOCURRENCY"}, "crypto", "Crypto asset"),
        ({"quote_type": "ETF", "name": "Vanguard Total Bond Market ETF"}, "etf_bond", "Inconnu"),
        ({"quote_type": "ETF", "name": "ARK Innovation ETF"}, "etf_equity", "Inconnu"),
        ({"quote_type": "EQUITY", "sector": None}, "equity", "Inconnu"),
    ],
)
def test_asset_class_and_sector_inference(tmp_db, monkeypatch, kwargs, want_class, want_sector):
    monkeypatch.setenv("AF_DYNAMIC_INGESTION", "on")
    _fake_yf(monkeypatch, **kwargs)
    sym = "ZZZ-USD" if want_class == "crypto" else "ZZZ"
    assert di.fetch_and_persist_asset(sym) == sym
    row = get_custom_assets_df([sym]).iloc[0]
    assert row["asset_class"] == want_class
    assert row["sector"] == want_sector


def test_timeout_and_errors_leave_the_asset_outside(tmp_db, monkeypatch):
    monkeypatch.setenv("AF_DYNAMIC_INGESTION", "on")
    monkeypatch.setenv("AF_YF_TIMEOUT_S", "0.2")
    _fake_yf(monkeypatch, delay=2.0)
    t0 = time.monotonic()
    assert di.fetch_and_persist_asset("SLOW") is None
    assert time.monotonic() - t0 < 1.5
    assert get_custom_assets_df().empty
    monkeypatch.setenv("AF_YF_TIMEOUT_S", "20")
    _fake_yf(monkeypatch, raise_on="info")
    assert di.fetch_and_persist_asset("BAD1") is None
    _fake_yf(monkeypatch, raise_on="download")
    assert di.fetch_and_persist_asset("BAD2") is None
    monkeypatch.setitem(sys.modules, "yfinance", None)
    assert di.fetch_and_persist_asset("BAD3") is None
    assert di.ensure_requested_asset("l'action BAD3") is None
    assert _regex_extract("10 % dans l'action BAD3").ticker is None
    assert get_custom_assets_df().empty


def test_stop_tokens_are_never_downloaded(tmp_db, monkeypatch):
    monkeypatch.setenv("AF_DYNAMIC_INGESTION", "on")
    calls = _fake_yf(monkeypatch)
    assert di.ensure_ticker_in_db("ESG") is None
    assert _resolve_ticker("ESG") is None
    assert _resolve_ticker("equity") is None
    assert calls == []


# --- 3. same rules on an ingested asset ---------------------------------------------------


def _bdays(start, end="2026-11-12"):
    return pd.bdate_range(start, end)


def _save(ticker, asset_class, sector, start, **extra):
    idx = _bdays(start)
    px = 10.0 + np.arange(len(idx)) * 0.01
    rows = [
        {"date": d.strftime("%Y-%m-%d"), "ticker": ticker, "open": p, "high": p, "low": p, "close": p,
         "adj_close": p, "volume": 1000.0, "currency": extra.get("currency", "USD")}
        for d, p in zip(idx, px, strict=True)
    ]
    save_custom_asset(
        {"ticker": ticker, "name": extra.get("name", ticker), "asset_class": asset_class,
         "market": extra.get("market", "NASDAQ"), "currency": extra.get("currency", "USD"),
         "sector": sector, "source": "yfinance", "retrieved_at": "2026-11-12 10:00:00"},
        rows,
    )


def test_spot_crypto_ingested_is_excluded_in_a_tfsa_and_labelled(tmp_db, monkeypatch):
    monkeypatch.setenv("AF_DYNAMIC_INGESTION", "on")
    _save("DOGE-USD", "crypto", "Crypto asset", "2021-11-15", market="Crypto (24/7)")
    profile = Profile(
        persona="amira", objective="growth", horizon_years=15, risk_tolerance="high",
        risk_capacity="high", account_type="tfsa", requested_idea={"ticker": "DOGE-USD", "weight": 0.1},
    )
    out = screening_node(GraphState(as_of_date=AS_OF, persona="amira", profile=profile))
    ex = {e["ticker"]: e for e in out["exclusions"]}
    assert ex["DOGE-USD"]["rule"] == "account_eligibility" and ex["DOGE-USD"]["requested"] is True
    assert "DOGE-USD" not in out["eligible_universe"]
    notes = [e for e in out["evidence"].values() if "DOGE-USD" in str(e.value) and "Yahoo Finance" in str(e.value)]
    assert notes and all(e.confidence == "assumption" for e in notes)
    assert "2026-11-12" in notes[0].source and "hors univers" in notes[0].source


def test_ingested_asset_evidence_cites_the_download_and_short_history(tmp_db, monkeypatch):
    monkeypatch.setenv("AF_DYNAMIC_INGESTION", "on")
    _save("BAI", "etf_equity", "Inconnu", "2024-01-02", name="Short history ETF")
    profile = Profile(
        persona="robert", objective="capital_preservation", horizon_years=4,
        risk_tolerance="low_moderate", risk_capacity="low", requested_idea={"ticker": "BAI", "weight": 0.1},
    )
    state = GraphState(as_of_date=AS_OF, persona="robert", profile=profile, eligible_universe=["RY.TO", "SPY", "BAI"])
    ev = quant_node(state)["evidence"]  # the branch crashed here: "single positional indexer is out-of-bounds"
    vol = [e for e in ev.values() if isinstance(e.value, dict) and e.value.get("metric") == "volatility_ann"
           and e.value.get("ticker") == "BAI"]
    assert vol and vol[0].confidence == "assumption" and "Yahoo Finance" in vol[0].source
    assert not any(isinstance(e.value, dict) and e.value.get("metric") == "stress_2022"
                   and e.value.get("ticker") == "BAI" for e in ev.values())
    texts = [str(e.value) for e in ev.values() if e.confidence == "assumption"]
    assert any("historique insuffisant pour la période 2022" in t and "BAI" in t for t in texts)
    assert any("téléchargées depuis Yahoo Finance le 2026-11-12" in t and "BAI" in t for t in texts)
    spy_vol = [e for e in ev.values() if isinstance(e.value, dict) and e.value.get("metric") == "volatility_ann"
               and e.value.get("ticker") == "SPY"]
    assert spy_vol[0].confidence == "fact"


def test_guardrail_sector_check_is_not_a_pass_when_the_sector_is_unknown(tmp_db, monkeypatch):
    monkeypatch.setenv("AF_DYNAMIC_INGESTION", "on")
    _save("BAI", "etf_equity", "Inconnu", "2024-01-02")
    profile = Profile(
        persona="robert", objective="capital_preservation", horizon_years=4, risk_tolerance="low_moderate",
        risk_capacity="low", sector_cap=0.3,
    )
    sc = Scenario(name="as_requested", weights={"BAI": 0.2, "SPY": 0.8})
    entries = [g for g in check_guardrails(profile, [sc], {}) if g["limit"] == "sector_cap"]
    assert entries and entries[0]["status"] == "unknown"
    assert "non vérifiée" in entries[0]["message_fr"] and "BAI" in entries[0]["message_fr"]
    ok = Scenario(name="capped", weights={"SPY": 1.0})
    assert [g for g in check_guardrails(profile, [ok], {}) if g["limit"] == "sector_cap"][0]["status"] != "unknown"


# --- 7. S3 write-through and reload, 8. no profile table ----------------------------------


def _doc(ticker, start="2024-01-02"):
    idx = _bdays(start)
    return {
        "asset": {"ticker": ticker, "name": ticker, "asset_class": "equity", "market": "NASDAQ",
                  "currency": "USD", "sector": "Technology", "source": "yfinance",
                  "retrieved_at": "2026-11-12 10:00:00"},
        "prices": [
            {"date": d.strftime("%Y-%m-%d"), "ticker": ticker, "open": 1.0, "high": 1.0, "low": 1.0,
             "close": 1.0 + i, "adj_close": 1.0 + i, "volume": 10.0, "currency": "USD"}
            for i, d in enumerate(idx)
        ],
    }


def test_ingested_asset_is_written_through_to_s3_and_mirrored_locally(tmp_db, monkeypatch, tmp_path):
    monkeypatch.setenv("AF_DYNAMIC_INGESTION", "on")
    monkeypatch.setattr(config, "S3_BUCKET", "test-bucket")
    fake = _FakeS3()
    monkeypatch.setattr(market_db, "_s3_client_override", fake)
    doc = _doc("PLTR")
    save_custom_asset(doc["asset"], doc["prices"])
    key = "test-bucket/cache/ingested/PLTR.json"
    assert key in fake.objects
    stored = json.loads(fake.objects[key].decode("utf-8"))
    assert stored["asset"]["ticker"] == "PLTR" and stored["asset"]["sector"] == "Technology"
    assert len(stored["prices"]) == len(doc["prices"]) and stored["prices"][0]["date"] == "2024-01-02"
    local = tmp_path / "cache" / "ingested" / "PLTR.json"
    assert local.is_file() and json.loads(local.read_text(encoding="utf-8")) == stored
    # the download path (fake yfinance) goes through the same write-through
    _fake_yf(monkeypatch)
    assert di.fetch_and_persist_asset("COIN") == "COIN"
    assert "test-bucket/cache/ingested/COIN.json" in fake.objects


def test_s3_failure_never_breaks_the_local_cache(tmp_db, monkeypatch):
    monkeypatch.setenv("AF_DYNAMIC_INGESTION", "on")
    monkeypatch.setattr(config, "S3_BUCKET", "test-bucket")
    monkeypatch.setattr(market_db, "_s3_client_override", _FakeS3(fail=True))
    doc = _doc("PLTR")
    save_custom_asset(doc["asset"], doc["prices"])
    assert market_db.has_custom_asset("PLTR")


def test_no_bucket_means_no_s3_call(tmp_db, monkeypatch):
    monkeypatch.setenv("AF_DYNAMIC_INGESTION", "on")
    monkeypatch.setattr(market_db, "_s3_client_override", _FakeS3())
    doc = _doc("PLTR")
    save_custom_asset(doc["asset"], doc["prices"])
    assert market_db._s3_client_override.objects == {}


def test_pulled_cache_documents_are_reloaded_into_a_fresh_sqlite(tmp_db, monkeypatch, tmp_path):
    """After a redeploy pull_caches restores cache/ingested/*.json; the first access loads them."""
    monkeypatch.setenv("AF_DYNAMIC_INGESTION", "on")
    d = tmp_path / "cache" / "ingested"
    d.mkdir(parents=True)
    (d / "BAI.json").write_text(json.dumps(_doc("BAI")), encoding="utf-8")
    (d / "broken.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(market_db, "_cache_loaded_for", set())
    assert market_db.has_custom_asset("BAI")  # lazy reload on first access
    assert get_custom_assets_df(["BAI"]).iloc[0]["sector"] == "Technology"
    assert len(get_custom_prices_df(["BAI"])) == len(_doc("BAI")["prices"])
    assert market_db.load_ingested_from_cache() == []  # already there: nothing loaded twice
    assert di.ensure_ticker_in_db("BAI") == "BAI"  # served locally, no download


def test_sqlite_holds_no_user_profiles(tmp_db):
    import sqlite3

    assert not hasattr(market_db, "save_user_profile_db") and not hasattr(market_db, "get_user_profile_db")
    with sqlite3.connect(tmp_db) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "user_profiles" not in tables
    from alphaforge import users

    assert "market_db" not in users.__dict__ and not hasattr(users, "get_user_profile_db")


# --- 5. short history in quant and scenario_metrics ---------------------------------------


def _short_history_frame():
    idx = _bdays("2021-01-04", "2025-06-30")
    rng = np.random.default_rng(0)
    a = 100 * np.cumprod(1 + rng.normal(0, 0.01, len(idx)))
    b = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.01, len(idx))), index=idx)
    b[idx < pd.Timestamp("2024-01-02")] = np.nan  # listed in 2024
    return pd.DataFrame({"A": a, "B": b.to_numpy()}, index=idx)


def test_short_history_functions_return_none_instead_of_crashing():
    prices = _short_history_frame()
    assert stress_2022(prices, "A") is not None
    assert stress_2022(prices, "B") is None
    assert stress_2022(prices, {"A": 0.5, "B": 0.5}) is None
    assert stress_2022(prices, pd.Series({"A": 0.5, "B": 0.5})) is None
    note = stress_2022_note(prices, "B", "B")
    assert note and "historique insuffisant pour la période 2022" in note
    assert stress_2022_note(prices, "A", "A") is None
    v = value(prices, "B")
    assert not v.empty and v.index[0] == pd.Timestamp("2024-01-02") and v.iloc[0] == 1.0
    assert np.isfinite(max_drawdown(prices, "B"))
    stats = rolling_returns_stats(prices, "B", window_years=1)
    assert stats is None or stats["windows_count"] > 0
    assert rolling_returns_stats(prices, "B", window_years=3) is None
    empty = prices.loc["2022-01-01":"2022-12-31"]
    assert value(empty, "B").empty and stress_2022(empty, "B") is None


def test_scenario_metrics_with_a_2024_listing_registers_no_stress_and_does_not_raise():
    prices = _short_history_frame().rename(columns={"A": "RY.TO", "B": "NVDA"})
    info = get_provider().asset_info()
    values = scenario_metrics(pd.Series({"RY.TO": 0.5, "NVDA": 0.5}), prices, info, as_of=dt.date(2025, 6, 30))
    assert values["stress_2022"] is None
    assert np.isfinite(values["volatility_ann"]) and np.isfinite(values["max_drawdown"])
