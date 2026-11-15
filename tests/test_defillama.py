"""Tests for DefiLlama crypto market context (Track A)."""

import datetime as dt
import json
import time
from unittest.mock import MagicMock

import httpx
import pytest

from alphaforge.data.defillama import (
    DefiLlamaClient,
)
from alphaforge.evidence import find_one
from alphaforge.graph import run
from alphaforge.nodes.macro import macro_node
from alphaforge.personas import PERSONAS
from alphaforge.state import GraphState


# --------------------------------------------------------------------------- Fixtures & Samples
@pytest.fixture
def sample_snapshot(tmp_path):
    snap_data = {
        "prices_current": {
            "coins": {
                "coingecko:bitcoin": {
                    "price": 74000.0,
                    "symbol": "BTC",
                    "timestamp": 1794759000,
                    "confidence": 0.99,
                },
                "coingecko:ethereum": {
                    "price": 2000.0,
                    "symbol": "ETH",
                    "timestamp": 1794759000,
                    "confidence": 0.99,
                },
            }
        },
        "chart": {
            "coins": {
                "coingecko:bitcoin": {
                    "symbol": "BTC",
                    "prices": [
                        {"timestamp": 1794268800, "price": 75000.0},  # 2026-11-10
                        {"timestamp": 1794355200, "price": 73500.0},  # 2026-11-11
                        {"timestamp": 1794441600, "price": 73974.39},  # 2026-11-12
                        {"timestamp": 1794528000, "price": 71000.0},  # 2026-11-13 (future)
                        {"timestamp": 1794614400, "price": 68000.0},  # 2026-11-14 (future)
                    ],
                },
                "coingecko:ethereum": {
                    "symbol": "ETH",
                    "prices": [
                        {"timestamp": 1794268800, "price": 2100.0},  # 2026-11-10
                        {"timestamp": 1794355200, "price": 2050.0},  # 2026-11-11
                        {"timestamp": 1794441600, "price": 2055.37},  # 2026-11-12
                        {"timestamp": 1794528000, "price": 2000.0},  # 2026-11-13 (future)
                        {"timestamp": 1794614400, "price": 1900.0},  # 2026-11-14 (future)
                    ],
                },
            }
        },
        "tvl_ethereum": [
            {"date": 1762905600, "tvl": 70000000000.0},  # ~365d prior
            {"date": 1791849600, "tvl": 47000000000.0},  # ~30d prior
            {"date": 1794441600, "tvl": 41093419802.0},  # 2026-11-12
            {"date": 1794614400, "tvl": 39000000000.0},  # 2026-11-14 (future)
        ],
        "stablecoins": [
            {
                "date": "1791849600",
                "totalCirculatingUSD": {"peggedUSD": 300000000000.0},
            },  # ~30d prior
            {
                "date": "1794441600",
                "totalCirculatingUSD": {"peggedUSD": 289051874291.0},
            },  # 2026-11-12
            {
                "date": "1794614400",
                "totalCirculatingUSD": {"peggedUSD": 287000000000.0},
            },  # 2026-11-14 (future)
        ],
    }
    p = tmp_path / "snapshot.json"
    p.write_text(json.dumps(snap_data), encoding="utf-8")
    return p


# --------------------------------------------------------------------------- 1. Endpoint Parsing
def test_parsing_endpoint_1_prices_current(sample_snapshot, tmp_path):
    client = DefiLlamaClient(
        snapshot_path=sample_snapshot, cache_dir=tmp_path / "cache", mode="cache"
    )
    res = client.get_prices_current("coingecko:bitcoin,coingecko:ethereum")
    assert res is not None
    coins = res.get("coins", {})
    assert "coingecko:bitcoin" in coins
    assert "coingecko:ethereum" in coins
    btc = coins["coingecko:bitcoin"]
    assert btc["price"] == 74000.0
    assert btc["symbol"] == "BTC"
    assert btc["confidence"] == 0.99


def test_parsing_endpoint_2_chart(sample_snapshot, tmp_path):
    client = DefiLlamaClient(
        snapshot_path=sample_snapshot, cache_dir=tmp_path / "cache", mode="cache"
    )
    res = client.get_chart("coingecko:bitcoin")
    assert res is not None
    coins = res.get("coins", {})
    assert "coingecko:bitcoin" in coins
    prices = coins["coingecko:bitcoin"]["prices"]
    assert len(prices) == 5
    assert prices[0]["price"] == 75000.0
    assert prices[0]["timestamp"] == 1794268800


def test_parsing_endpoint_3_historical_chain_tvl(sample_snapshot, tmp_path):
    client = DefiLlamaClient(
        snapshot_path=sample_snapshot, cache_dir=tmp_path / "cache", mode="cache"
    )
    tvl = client.get_historical_chain_tvl("Ethereum")
    assert tvl is not None
    assert len(tvl) == 4
    assert tvl[2]["tvl"] == 41093419802.0
    assert tvl[2]["date"] == 1794441600


def test_parsing_endpoint_4_stablecoins(sample_snapshot, tmp_path):
    client = DefiLlamaClient(
        snapshot_path=sample_snapshot, cache_dir=tmp_path / "cache", mode="cache"
    )
    stb = client.get_stablecoin_charts("all")
    assert stb is not None
    assert len(stb) == 3
    assert stb[1]["date"] == "1794441600"
    assert stb[1]["totalCirculatingUSD"]["peggedUSD"] == 289051874291.0


# --------------------------------------------------------------------------- 2. AS-OF Safety
def test_as_of_filtering_drops_future_points(sample_snapshot, tmp_path):
    client = DefiLlamaClient(
        snapshot_path=sample_snapshot, cache_dir=tmp_path / "cache", mode="cache"
    )
    as_of = dt.date(2026, 11, 12)
    ctx = client.get_crypto_context(as_of)

    assert ctx is not None
    # TVL check: point from 2026-11-14 must NOT be used
    assert ctx.eth_tvl_date == dt.date(2026, 11, 12)
    assert ctx.eth_tvl == 41093419802.0
    assert ctx.eth_tvl != 39000000000.0

    # Stablecoins check: point from 2026-11-14 must NOT be used
    assert ctx.stablecoin_date == dt.date(2026, 11, 12)
    assert ctx.stablecoin_supply == 289051874291.0
    assert ctx.stablecoin_supply != 287000000000.0

    # BTC & ETH prices: points from 2026-11-13 and 2026-11-14 must NOT be used
    assert ctx.btc_price_date == dt.date(2026, 11, 12)
    assert ctx.btc_price == pytest.approx(73974.39)
    assert ctx.eth_price_date == dt.date(2026, 11, 12)
    assert ctx.eth_price == pytest.approx(2055.37)


def test_as_of_in_past_does_not_use_current_prices(sample_snapshot, tmp_path):
    # Snapshot current prices has timestamp 1794759000 (after 2026-11-12)
    client = DefiLlamaClient(
        snapshot_path=sample_snapshot, cache_dir=tmp_path / "cache", mode="cache"
    )
    as_of = dt.date(2026, 11, 12)
    ctx = client.get_crypto_context(as_of)

    assert ctx is not None
    # If it had used current prices, btc_price would be 74000.0
    assert ctx.btc_price != 74000.0
    assert ctx.btc_price == pytest.approx(73974.39)


# --------------------------------------------------------------------------- 3. Cache TTL
def test_cache_ttl(tmp_path):
    cache_dir = tmp_path / "defillama_cache"
    cache_dir.mkdir()
    client = DefiLlamaClient(cache_dir=cache_dir, cache_ttl_hours=2.0, mode="cache")

    cache_file = cache_dir / "tvl_ethereum.json"
    cache_file.write_text(json.dumps([{"date": 1794441600, "tvl": 41093419802.0}]))

    # Within TTL (fresh)
    cached = client._read_cache("tvl_ethereum")
    assert cached == [{"date": 1794441600, "tvl": 41093419802.0}]

    # Expired: age > 2 hours
    old_time = time.time() - (3 * 3600)
    import os

    os.utime(cache_file, (old_time, old_time))
    expired = client._read_cache("tvl_ethereum")
    assert expired is None


# --------------------------------------------------------------------------- 4. Failure Cascade
def test_network_failure_falls_back_to_snapshot(sample_snapshot, tmp_path):
    mock_http = MagicMock()
    mock_http.get.side_effect = httpx.ConnectTimeout("Network timed out")

    client = DefiLlamaClient(
        snapshot_path=sample_snapshot,
        cache_dir=tmp_path / "cache",
        mode="live",
        http_client=mock_http,
    )
    ctx = client.get_crypto_context(dt.date(2026, 11, 12))
    assert ctx is not None
    assert ctx.eth_tvl == 41093419802.0
    assert ctx.stablecoin_supply == 289051874291.0


def test_failure_without_snapshot_returns_none(tmp_path):
    mock_http = MagicMock()
    mock_http.get.side_effect = httpx.ConnectTimeout("Network timed out")

    client = DefiLlamaClient(
        snapshot_path=tmp_path / "nonexistent.json",
        cache_dir=tmp_path / "cache",
        mode="live",
        http_client=mock_http,
    )
    ctx = client.get_crypto_context(dt.date(2026, 11, 12))
    assert ctx is None


def test_mode_off_returns_none(sample_snapshot, tmp_path):
    client = DefiLlamaClient(
        snapshot_path=sample_snapshot, cache_dir=tmp_path / "cache", mode="off"
    )
    assert client.get_crypto_context() is None
    assert client.get_prices_current() is None
    assert client.get_chart() is None
    assert client.get_historical_chain_tvl() is None
    assert client.get_stablecoin_charts() is None


# --------------------------------------------------------------------------- 5. Evidence & Personas
def test_evidence_appears_for_amira_and_not_mateo_robert():
    as_of = dt.date(2026, 11, 12)

    # Amira: crypto allowed in eligible_universe
    s_amira = GraphState(
        as_of_date=as_of,
        persona="amira",
        eligible_universe=["BTC-USD", "ETH-USD", "SPY"],
    )
    out_amira = macro_node(s_amira)
    ev_amira = out_amira["evidence"]

    assert any(e.source == "DefiLlama" for e in ev_amira.values())
    assert find_one(ev_amira, metric="eth_tvl") is not None
    assert find_one(ev_amira, metric="eth_tvl_change_30d") is not None
    assert find_one(ev_amira, metric="eth_tvl_change_365d") is not None
    assert find_one(ev_amira, metric="stablecoin_supply_usd") is not None
    assert find_one(ev_amira, metric="stablecoin_change_30d") is not None
    assert find_one(ev_amira, metric="btc_price_defillama") is not None
    assert find_one(ev_amira, metric="eth_price_defillama") is not None
    assert find_one(ev_amira, metric="btc_price_cross_check") is not None

    # Check cross-check item
    cross = find_one(ev_amira, metric="btc_price_cross_check")
    assert cross.source == "DefiLlama"
    assert cross.confidence == "fact"
    assert cross.date == as_of
    assert "relative gap" in cross.method
    assert isinstance(cross.value, dict)
    assert "provider_close" in cross.value
    assert "defillama_price" in cross.value

    # Mateo: no crypto
    s_mateo = GraphState(
        as_of_date=as_of,
        persona="mateo",
        eligible_universe=["SPY", "XIU.TO"],
    )
    out_mateo = macro_node(s_mateo)
    assert not any(e.source == "DefiLlama" for e in out_mateo["evidence"].values())

    # Robert: no crypto
    s_robert = GraphState(
        as_of_date=as_of,
        persona="robert",
        eligible_universe=["SPY", "XIU.TO"],
    )
    out_robert = macro_node(s_robert)
    assert not any(e.source == "DefiLlama" for e in out_robert["evidence"].values())


def test_existing_evidence_ids_unchanged_for_runs_without_crypto():
    as_of = dt.date(2026, 11, 12)

    s_mateo = GraphState(
        as_of_date=as_of,
        persona="mateo",
        eligible_universe=["SPY", "XIU.TO"],
    )
    ev_mateo = macro_node(s_mateo)["evidence"]
    mateo_keys = sorted(ev_mateo.keys(), key=lambda k: int(k[2:]))
    assert mateo_keys == [f"EM{i}" for i in range(1, 13)]

    s_amira = GraphState(
        as_of_date=as_of,
        persona="amira",
        eligible_universe=["BTC-USD", "ETH-USD", "SPY"],
    )
    ev_amira = macro_node(s_amira)["evidence"]
    # Existing macro metrics (EM1..EM12) must match Mateo exactly
    for k in mateo_keys:
        assert ev_amira[k].value == ev_mateo[k].value
        assert ev_amira[k].source == ev_mateo[k].source

    # DefiLlama evidence items start at EM13
    assert "EM13" in ev_amira
    assert ev_amira["EM13"].source == "DefiLlama"


# --------------------------------------------------------------------------- 6. E2E Offline Run
def test_e2e_offline_run_passes_verifier():
    s = run("amira", PERSONAS["amira"]["example_request"])

    assert s.verification is not None
    assert s.verification["passed"] is True
    assert not s.verification.get("errors")

    # Confirm DefiLlama evidence was produced
    defillama_items = [e for e in s.evidence.values() if e.source == "DefiLlama"]
    assert len(defillama_items) == 8

    # Confirm explanation cited crypto context
    qd_claims = [c["claim"] for c in s.explanation.get("quelles_donnees", [])]
    assert any("valeur totale bloquée sur Ethereum" in c for c in qd_claims)

    lim_claims = [c["claim"] for c in s.explanation.get("limites", [])]
    assert any("cours Bitcoin de DefiLlama" in c for c in lim_claims)


# --------------------------------------------------------------------------- 7. Real Network Test (live)
@pytest.mark.live
def test_live_defillama_network():
    """Live integration test against the real DefiLlama endpoints."""
    client = DefiLlamaClient(mode="live", timeout_s=10.0)

    # 1. prices current
    prices = client.get_prices_current("coingecko:bitcoin,coingecko:ethereum")
    assert prices and "coins" in prices
    assert "coingecko:bitcoin" in prices["coins"]

    # 2. chart
    start_ts = int(dt.datetime(2026, 11, 1, tzinfo=dt.UTC).timestamp())
    chart = client.get_chart("coingecko:bitcoin", start=start_ts, span=5, period="1d")
    assert chart and "coins" in chart

    # 3. tvl
    tvl = client.get_historical_chain_tvl("Ethereum")
    assert tvl and len(tvl) > 100

    # 4. stablecoins
    stb = client.get_stablecoin_charts("all")
    assert stb and len(stb) > 100

    ctx = client.get_crypto_context(dt.date(2026, 11, 12))
    assert ctx is not None
    assert ctx.eth_tvl is not None
    assert ctx.btc_price is not None
    assert ctx.stablecoin_supply is not None
