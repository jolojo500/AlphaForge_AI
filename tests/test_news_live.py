"""Tests for live news mode, secrets resolution, rate limit & timeout handling (PRD §5.5, B-9)."""
from __future__ import annotations

import datetime as dt
import os
from unittest.mock import MagicMock

import httpx
import pytest

from alphaforge import config
from alphaforge.nodes import events as ev
from alphaforge.secrets import get_secret, get_ssm_parameter
from alphaforge.state import GraphState, Profile
from alphaforge.tools import news as news_tool
from alphaforge.tools import search as search_tool
from alphaforge.tools.news import NewsItem

AS_OF = dt.date(2026, 11, 12)


def dummy_item(headline: str = "Tesla battery event", ticker: str = "TSLA") -> NewsItem:
    return NewsItem(
        ticker=ticker,
        headline=headline,
        source="Reuters",
        provider="finnhub",
        url=f"https://news.test/{ticker}-1",
        published_at=dt.datetime(2026, 11, 1, 10, 0, tzinfo=dt.UTC),
    )


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    return tmp_path


# --------------------------------------------------------------------------- Secrets resolution
def test_secrets_resolution_env_priority(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "env-finnhub-key")
    get_ssm_parameter.cache_clear()
    assert get_secret("FINNHUB_API_KEY") == "env-finnhub-key"


def test_secrets_resolution_from_ssm(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    get_ssm_parameter.cache_clear()

    mock_boto = MagicMock()
    mock_ssm = MagicMock()
    mock_boto.client.return_value = mock_ssm
    mock_ssm.get_parameter.return_value = {"Parameter": {"Value": "ssm-secret-finnhub"}}

    monkeypatch.setattr("boto3.client", mock_boto.client)

    val = get_secret("FINNHUB_API_KEY", "/alphaforge/finnhub_api_key")
    assert val == "ssm-secret-finnhub"
    assert os.getenv("FINNHUB_API_KEY") == "ssm-secret-finnhub"
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    get_ssm_parameter.cache_clear()


def test_secrets_resolution_ssm_failure_is_graceful(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    get_ssm_parameter.cache_clear()

    mock_boto = MagicMock()
    mock_boto.client.side_effect = RuntimeError("SSM unavailable")
    monkeypatch.setattr("boto3.client", mock_boto.client)

    val = get_secret("TAVILY_API_KEY", "/alphaforge/tavily_api_key")
    assert val is None


# --------------------------------------------------------------------------- Rate limit & Timeout
def test_finnhub_rate_limit_429_fallback(tmp_cache, monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "dummy-key")
    news_tool.write_cache("finnhub", "TSLA", [dummy_item("Tesla Q3 Record")])

    req = httpx.Request("GET", "https://finnhub.io/api/v1/company-news")
    resp_429 = httpx.Response(429, request=req)

    def mock_get(*args, **kwargs):
        raise httpx.HTTPStatusError("Too Many Requests", request=req, response=resp_429)

    monkeypatch.setattr(news_tool.httpx, "get", mock_get)

    warnings: list[str] = []
    items = news_tool.fetch_company_news("TSLA", dt.date(2026, 1, 1), AS_OF, mode="live", warnings=warnings)
    assert len(items) == 1
    assert items[0].headline == "Tesla Q3 Record"
    assert any("429" in w and "repli sur le cache" in w for w in warnings)


def test_finnhub_timeout_fallback(tmp_cache, monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "dummy-key")
    news_tool.write_cache("finnhub", "TSLA", [dummy_item("Tesla Delivery Beat")])

    def mock_timeout(*args, **kwargs):
        raise httpx.TimeoutException("Connection timed out")

    monkeypatch.setattr(news_tool.httpx, "get", mock_timeout)

    warnings: list[str] = []
    items = news_tool.fetch_company_news("TSLA", dt.date(2026, 1, 1), AS_OF, mode="live", warnings=warnings)
    assert len(items) == 1
    assert items[0].headline == "Tesla Delivery Beat"
    assert any("timeout" in w or "délai" in w for w in warnings)


def test_tavily_rate_limit_429_fallback(tmp_cache, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "dummy-key")
    search_key = search_tool.query_key("Enbridge ESG controversy")
    search_tool.write_cache("search", search_key, [dummy_item("Enbridge Pipeline Review", ticker="")])

    req = httpx.Request("POST", "https://api.tavily.com/search")
    resp_429 = httpx.Response(429, request=req)

    def mock_post(*args, **kwargs):
        raise httpx.HTTPStatusError("Too Many Requests", request=req, response=resp_429)

    monkeypatch.setattr(search_tool.httpx, "post", mock_post)

    warnings: list[str] = []
    items = search_tool.web_search("Enbridge ESG controversy", mode="live", warnings=warnings)
    assert len(items) == 1
    assert any("429" in w and "repli sur le cache" in w for w in warnings)


def test_tavily_timeout_fallback(tmp_cache, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "dummy-key")
    search_key = search_tool.query_key("Exxon lawsuit")
    search_tool.write_cache("search", search_key, [dummy_item("Exxon Court Decision", ticker="")])

    def mock_timeout(*args, **kwargs):
        raise httpx.TimeoutException("Read timed out")

    monkeypatch.setattr(search_tool.httpx, "post", mock_timeout)

    warnings: list[str] = []
    items = search_tool.web_search("Exxon lawsuit", mode="live", warnings=warnings)
    assert len(items) == 1
    assert any("timeout" in w or "délai" in w for w in warnings)


# --------------------------------------------------------------------------- Warning evidence entry
def test_events_node_records_warning_evidence_on_rate_limit(tmp_cache, monkeypatch):
    monkeypatch.setattr(config, "NEWS_MODE", "live")
    monkeypatch.setenv("FINNHUB_API_KEY", "dummy-key")
    news_tool.write_cache("finnhub", "TSLA", [dummy_item("Tesla Autopilot Probe")])

    req = httpx.Request("GET", "https://finnhub.io/api/v1/company-news")
    resp_429 = httpx.Response(429, request=req)

    def mock_get(*args, **kwargs):
        raise httpx.HTTPStatusError("Rate limit exceeded", request=req, response=resp_429)

    monkeypatch.setattr(news_tool.httpx, "get", mock_get)

    state = GraphState(
        run_id="test-run",
        persona="robert",
        user_request="Je veux évaluer 25% TSLA",
        as_of_date=AS_OF,
        eligible_universe=["TSLA", "SPY"],
        profile=Profile(
            persona="robert",
            objective="tester",
            risk_tolerance="moderate",
            risk_capacity="moderate",
            horizon_years=5,
            requested_idea={"ticker": "TSLA", "weight": 0.25},
            request_type="judge",
        ),
    )

    out = ev.events_node(state)
    assert "evidence" in out
    evidence = out["evidence"]

    # Verify that a warning evidence entry was recorded
    warnings_in_ev = [
        e for e in evidence.values()
        if isinstance(e.value, dict) and e.value.get("metric") == "news_warning"
    ]
    assert len(warnings_in_ev) >= 1
    assert "429" in warnings_in_ev[0].value.get("warning", "")


# --------------------------------------------------------------------------- Live provider tests
@pytest.mark.live
def test_finnhub_live():
    """Live test against Finnhub API when FINNHUB_API_KEY is configured in env or SSM."""
    key = get_secret("FINNHUB_API_KEY")
    if not key or key.startswith("dummy") or key.startswith("ssm-secret") or key.startswith("env-"):
        pytest.skip("FINNHUB_API_KEY non configurée (env ou SSM). Test ignoré.")

    from alphaforge.tools.news import _finnhub

    items = _finnhub("TSLA", dt.date(2026, 11, 1), dt.date(2026, 11, 10), key)
    assert isinstance(items, list)
    if items:
        assert isinstance(items[0], NewsItem)
        assert items[0].ticker == "TSLA"


@pytest.mark.live
def test_tavily_live():
    """Live test against Tavily Search API when TAVILY_API_KEY is configured in env or SSM."""
    key = get_secret("TAVILY_API_KEY")
    if not key or key.startswith("dummy") or key.startswith("ssm-secret") or key.startswith("env-"):
        pytest.skip("TAVILY_API_KEY non configurée (env ou SSM). Test ignoré.")

    from alphaforge.tools.search import _tavily

    items = _tavily("Tesla ESG controversy", 3, key)
    assert isinstance(items, list)
    if items:
        assert isinstance(items[0], NewsItem)
        assert items[0].provider == "tavily"
