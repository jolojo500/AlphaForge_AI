import datetime as dt
import json
from pathlib import Path

import httpx
import pytest

from alphaforge import config, llm
from alphaforge.graph import run
from alphaforge.nodes import events as ev
from alphaforge.personas import PERSONAS
from alphaforge.tools import news as news_tool
from alphaforge.tools import search as search_tool
from alphaforge.tools.news import NewsItem

AS_OF = dt.date(2026, 11, 12)
LABELS = json.loads((Path(__file__).parent / "fixtures" / "news_labels.json").read_text())


def item(headline="Tesla recalls cars", d="2026-11-01", ticker="TSLA", **kw):
    return NewsItem(
        ticker=ticker, headline=headline, source="Wire", provider="finnhub",
        url=f"https://x.test/{headline}-{d}", published_at=dt.datetime.fromisoformat(d + "T12:00:00+00:00"),
        **kw,
    )


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    return tmp_path


class Resp:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


# --------------------------------------------------------------------------- tools
def test_cache_returns_only_items_inside_window(tmp_cache):
    news_tool.write_cache("finnhub", "TSLA", [item(d="2026-11-01"), item("late", d="2026-11-20"), item("old", d="2025-01-01")])
    got = news_tool.fetch_company_news("TSLA", dt.date(2026, 6, 1), AS_OF)
    assert [i.headline for i in got] == ["Tesla recalls cars"]


def test_live_without_key_warns_and_uses_cache(tmp_cache, monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    news_tool.write_cache("finnhub", "TSLA", [item()])
    warnings: list[str] = []
    got = news_tool.fetch_company_news("TSLA", dt.date(2026, 1, 1), AS_OF, mode="live", warnings=warnings)
    assert len(got) == 1 and "FINNHUB_API_KEY" in warnings[0]


def test_live_fetch_is_cached_with_publication_time(tmp_cache, monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    ts = int(dt.datetime(2026, 10, 30, 15, 0, tzinfo=dt.UTC).timestamp())
    payload = [{"headline": "Tesla sued", "summary": "s", "source": "Reuters", "url": "https://r/1", "datetime": ts}]
    monkeypatch.setattr(news_tool.httpx, "get", lambda *a, **k: Resp(payload))
    got = news_tool.fetch_company_news("TSLA", dt.date(2026, 1, 1), AS_OF, mode="live")
    assert got[0].published_at == dt.datetime(2026, 10, 30, 15, 0, tzinfo=dt.UTC)
    # now offline: served from the cache
    again = news_tool.fetch_company_news("TSLA", dt.date(2026, 1, 1), AS_OF, mode="cache")
    assert [i.headline for i in again] == ["Tesla sued"]


def test_live_http_error_falls_back_to_cache(tmp_cache, monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    news_tool.write_cache("finnhub", "TSLA", [item()])

    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(news_tool.httpx, "get", boom)
    warnings: list[str] = []
    got = news_tool.fetch_company_news("TSLA", dt.date(2026, 1, 1), AS_OF, mode="live", warnings=warnings)
    assert len(got) == 1 and "indisponible" in warnings[0]


def test_web_search_caches_and_parses_dates(tmp_cache, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    payload = {"results": [
        {"title": "Exxon lawsuit", "url": "https://news.test/a", "content": "c", "published_date": "2026-10-10T08:00:00Z"},
        {"title": "No date", "url": "https://news.test/b", "content": "c"},
    ]}
    monkeypatch.setattr(search_tool.httpx, "post", lambda *a, **k: Resp(payload))
    got = search_tool.web_search("Exxon ESG controversy", mode="live")
    assert [i.published_at is not None for i in got] == [True, False]
    assert len(search_tool.web_search("Exxon ESG controversy", mode="cache")) == 2


def test_holdings_wrapper_returns_empty_without_loader():
    assert news_tool.fetch_etf_holdings("SPY") == []


# --------------------------------------------------------------------------- classification
def test_rules_classifier_basics():
    c = ev.heuristic_classify(item("Regulator opens investigation into Tesla"))
    assert (c.risk_type, c.material, c.kind) == ("controversy", True, "fact")
    assert ev.heuristic_classify(item("Analyst says stock could fall")).kind == "opinion"
    assert ev.heuristic_classify(item("Company sponsors charity marathon")).relevant is False


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        return type("M", (), {"content": json.dumps(self.reply)})()


def test_llm_classification_and_schema_failure_fallback():
    good = {"relevant": True, "kind": "fact", "risk_type": "credit", "material": True}
    c, how = ev.classify_item(item(), "TSLA", FakeLLM(good))
    assert how == "llm" and c.risk_type == "credit"
    bad = {"relevant": True, "kind": "fact", "risk_type": "weather", "material": True}
    c, how = ev.classify_item(item("Tesla recalls cars"), "TSLA", FakeLLM(bad))
    assert how == "rules" and c.risk_type == "controversy"


def _accuracy(predict):
    hits = {"relevant": 0, "kind": 0, "risk_type": 0, "material": 0}
    for row in LABELS:
        it = NewsItem(
            ticker=row["ticker"], headline=row["headline"], summary=row["summary"], source=row["source"],
            provider=row["provider"], published_at=dt.datetime(2026, 11, 1, tzinfo=dt.UTC),
        )
        pred = predict(it)
        for k in hits:
            hits[k] += getattr(pred, k) == row[k]
    return {k: v / len(LABELS) for k, v in hits.items()}


def test_labeled_set_shape():
    assert len(LABELS) == 50
    assert {r["risk_type"] for r in LABELS} >= {"market", "credit", "liquidity", "controversy", "concentration"}


def test_rules_classifier_accuracy_on_labeled_set():
    acc = _accuracy(ev.heuristic_classify)
    print("rules accuracy", acc)
    assert min(acc.values()) >= 0.8, acc


@pytest.mark.live
def test_llm_classifier_accuracy_on_labeled_set():
    acc = _accuracy(lambda it: ev.classify_item(it, it.ticker)[0])
    print("llm accuracy", acc)
    assert min(acc.values()) >= 0.8, acc


# --------------------------------------------------------------------------- node
def test_robert_tsla_uses_cache_and_respects_as_of():
    s = run("robert", PERSONAS["robert"]["example_request"])
    real = [e for e in s.events if e["ticker"] == "TSLA"]
    assert real, "TSLA filings should be read from the committed cache"
    assert all(dt.date.fromisoformat(e["published_at"]) <= s.as_of_date for e in s.events)
    assert all(e["evidence_id"] in s.evidence and s.evidence[e["evidence_id"]].date_kind == "publication" for e in s.events)
    assert all(e["url"] and e["classifier"] == "rules" for e in real)  # offline in unit tests


def test_earlier_as_of_drops_later_items():
    late = run("robert", PERSONAS["robert"]["example_request"], as_of_date=dt.date(2026, 11, 12))
    early = run("robert", PERSONAS["robert"]["example_request"], as_of_date=dt.date(2026, 3, 1))
    assert max(e["published_at"] for e in early.events) <= "2026-03-01"
    assert len(early.events) < len(late.events) or max(e["published_at"] for e in late.events) > "2026-03-01"


def test_same_input_gives_same_classified_list():
    a = run("robert", PERSONAS["robert"]["example_request"])
    b = run("robert", PERSONAS["robert"]["example_request"])
    assert a.events == b.events
    assert [k for k in a.evidence if k.startswith("EN")] == [k for k in b.evidence if k.startswith("EN")]


def test_no_news_still_yields_coverage_evidence_and_no_crash():
    s = run("mateo", PERSONAS["mateo"]["example_request"])
    assert any(k.startswith("EN") for k in s.evidence)
    cov = [e for e in s.evidence.values() if isinstance(e.value, dict) and e.value.get("metric") == "news_items_retained"]
    assert cov and cov[0].date == s.as_of_date


def test_tool_budget_is_enforced(monkeypatch):
    calls = []

    def fake_news(ticker, d1, d2, **kw):
        calls.append(ticker)
        return []

    monkeypatch.setattr(ev, "fetch_company_news", fake_news)
    monkeypatch.setattr(ev, "default_plan", lambda state: [("news", t) for t in sorted(ev._universe())])
    s = run("amira", PERSONAS["amira"]["example_request"])
    assert len(calls) == ev.MAX_TOOL_CALLS and s.events == []


def test_item_budget_and_interleaving():
    items = [item(f"h{i}", d="2026-10-01", ticker="TSLA") for i in range(60)] + [item("n1", ticker="NVDA")]
    chosen = ev._select(items, AS_OF)
    assert len(chosen) == ev.MAX_CLASSIFIED
    assert "NVDA" in {i.ticker for i in chosen}  # not starved by the larger TSLA list


def test_planner_model_can_stop_the_loop(monkeypatch):
    seen = []
    monkeypatch.setattr(ev, "fetch_company_news", lambda t, *a, **k: seen.append(t) or [])
    monkeypatch.setattr(ev, "default_plan", lambda state: [("news", "TSLA"), ("news", "NVDA")])
    s = run("amira", PERSONAS["amira"]["example_request"])  # offline: no planner, plan is followed
    assert seen == ["TSLA", "NVDA"] and s.events == []
    seen.clear()
    monkeypatch.setattr(llm, "get_llm", lambda kind="main": FakeLLM({"action": "done"}))
    monkeypatch.setenv("AF_LLM_OFFLINE", "0")
    run("amira", PERSONAS["amira"]["example_request"])
    assert seen == ["TSLA"]  # first step is the plan, then the model said "done"
