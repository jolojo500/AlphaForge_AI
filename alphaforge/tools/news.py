"""News and holdings tools for Agent 2 (PRD 5.5). Owned by Track B.

Cache first: every fetched item is stored as JSON under data/cache/news/ so a rate limit or a
missing key never breaks the demo. `AF_NEWS_MODE=cache` (default) reads the cache only;
`live` calls Finnhub and refreshes the cache. Tools never raise: on any failure they fall back
to the cache and append a message to `warnings`.

Stored `published_at` is the provider's publication timestamp, not the fetch time.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path

import httpx
from pydantic import BaseModel

from alphaforge import config

FINNHUB_URL = "https://finnhub.io/api/v1/company-news"
HTTP_TIMEOUT = 10.0


class NewsItem(BaseModel):
    ticker: str
    headline: str
    summary: str = ""
    source: str  # publisher or filing authority
    url: str | None = None
    published_at: dt.datetime | None = None  # provider publication time (UTC); None if unknown
    provider: str  # finnhub | tavily | sec_edgar | ...

    @property
    def published_date(self) -> dt.date | None:
        return self.published_at.date() if self.published_at else None


def cache_dir() -> Path:
    d = Path(config.CACHE_DIR) / "news"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", name)


def cache_path(provider: str, key: str) -> Path:
    return cache_dir() / f"{_safe(provider)}_{_safe(key)}.json"


def _mode(mode: str | None) -> str:
    return (mode or config.NEWS_MODE or "cache").lower()


def read_cache_file(path: Path) -> list[NewsItem]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [NewsItem.model_validate(i) for i in raw.get("items", [])]
    except (OSError, ValueError):
        return []


def write_cache(provider: str, key: str, items: list[NewsItem]) -> None:
    """Merge `items` into the cache file for (provider, key), deduplicated by url/headline."""
    path = cache_path(provider, key)
    merged = {_dedupe_key(i): i for i in read_cache_file(path)}
    merged.update({_dedupe_key(i): i for i in items})
    ordered = sorted(
        merged.values(),
        key=lambda i: (i.published_at or dt.datetime.min.replace(tzinfo=dt.UTC), i.url or ""),
        reverse=True,
    )
    payload = {
        "provider": provider,
        "key": key,
        "fetched_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "items": [json.loads(i.model_dump_json()) for i in ordered],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _dedupe_key(i: NewsItem) -> str:
    return i.url or f"{i.provider}:{i.headline}"


def _in_window(i: NewsItem, date_from: dt.date, date_to: dt.date) -> bool:
    d = i.published_date
    return d is not None and date_from <= d <= date_to


def _sorted(items: list[NewsItem]) -> list[NewsItem]:
    floor = dt.datetime.min.replace(tzinfo=dt.UTC)
    return sorted(items, key=lambda i: (i.published_at or floor, i.url or ""), reverse=True)


def cached_company_news(ticker: str) -> list[NewsItem]:
    items: list[NewsItem] = []
    for path in sorted(cache_dir().glob(f"*_{_safe(ticker)}.json")):
        if path.name.startswith("search_"):
            continue
        items += read_cache_file(path)
    return items


def _finnhub(ticker: str, date_from: dt.date, date_to: dt.date, key: str) -> list[NewsItem]:
    r = httpx.get(
        FINNHUB_URL,
        params={"symbol": ticker, "from": date_from.isoformat(), "to": date_to.isoformat(), "token": key},
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    out = []
    for row in r.json():
        ts = row.get("datetime")
        if not ts or not row.get("headline"):
            continue
        out.append(
            NewsItem(
                ticker=ticker,
                headline=row["headline"].strip(),
                summary=(row.get("summary") or "").strip(),
                source=row.get("source") or "Finnhub",
                url=row.get("url") or None,
                published_at=dt.datetime.fromtimestamp(int(ts), dt.UTC),
                provider="finnhub",
            )
        )
    return out


def fetch_company_news(
    ticker: str,
    date_from: dt.date,
    date_to: dt.date,
    *,
    mode: str | None = None,
    warnings: list[str] | None = None,
) -> list[NewsItem]:
    """News for `ticker` published within [date_from, date_to], newest first.

    Items dated after `date_to` are never returned (no look-ahead).
    """
    warnings = warnings if warnings is not None else []
    if _mode(mode) == "live":
        key = os.getenv("FINNHUB_API_KEY")
        if not key:
            warnings.append("FINNHUB_API_KEY absente : lecture du cache uniquement.")
        else:
            try:
                fresh = _finnhub(ticker, date_from, date_to, key)
                if fresh:
                    write_cache("finnhub", ticker, fresh)
            except (httpx.HTTPError, ValueError) as exc:
                warnings.append(f"Finnhub indisponible pour {ticker} ({type(exc).__name__}) : cache utilisé.")
    return _sorted([i for i in cached_company_news(ticker) if _in_window(i, date_from, date_to)])


def fetch_etf_holdings(ticker: str, top_n: int = 5) -> list[dict]:
    """Top holdings of an ETF as [{"ticker", "weight"}], via Track A's cached loader.

    Returns [] if the loader is not available or the ETF is unknown.
    """
    try:
        from alphaforge.data import holdings as loader
    except ImportError:
        return []
    fn = getattr(loader, "load_holdings", None)
    if fn is None:
        return []
    try:
        rows = fn(ticker)
    except Exception:  # loader owned by another track: never let it break this agent
        return []
    cleaned = []
    for r in rows or []:
        t, w = (r.get("ticker"), r.get("weight")) if isinstance(r, dict) else (None, None)
        if t and isinstance(w, (int, float)):
            cleaned.append({"ticker": str(t), "weight": float(w)})
    return sorted(cleaned, key=lambda r: (-r["weight"], r["ticker"]))[:top_n]
