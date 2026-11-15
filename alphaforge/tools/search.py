"""Web search tool for Agent 2 (PRD 5.5), Tavily free tier. Owned by Track B.

Same contract as news.py: cache first, never raises, no look-ahead. Search results without a
publication date cannot be proven to precede the as-of date, so callers must drop them.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import os

import httpx

from alphaforge.tools.news import (
    HTTP_TIMEOUT,
    NewsItem,
    _mode,
    read_cache_file,
    write_cache,
)

TAVILY_URL = "https://api.tavily.com/search"


def query_key(query: str) -> str:
    return hashlib.sha1(query.strip().lower().encode("utf-8")).hexdigest()[:16]


def _parse_date(raw: str | None) -> dt.datetime | None:
    if not raw:
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = dt.datetime.strptime(raw[:25], "%a, %d %b %Y %H:%M:%S")
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.UTC)


def _tavily(query: str, max_results: int, key: str) -> list[NewsItem]:
    r = httpx.post(
        TAVILY_URL,
        headers={"Authorization": f"Bearer {key}"},
        json={"query": query, "topic": "news", "max_results": max_results},
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    out = []
    for row in r.json().get("results", []):
        if not row.get("title"):
            continue
        out.append(
            NewsItem(
                ticker="",
                headline=row["title"].strip(),
                summary=(row.get("content") or "").strip()[:500],
                source=(row.get("url") or "Tavily").split("/")[2] if row.get("url") else "Tavily",
                url=row.get("url") or None,
                published_at=_parse_date(row.get("published_date")),
                provider="tavily",
            )
        )
    return out


def web_search(
    query: str,
    max_results: int = 5,
    *,
    mode: str | None = None,
    warnings: list[str] | None = None,
) -> list[NewsItem]:
    """Search results for `query`, from the cache or (live mode) Tavily."""
    warnings = warnings if warnings is not None else []
    from alphaforge.tools.news import cache_path

    key = query_key(query)
    path = cache_path("search", key)
    if _mode(mode) == "live":
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            warnings.append("TAVILY_API_KEY absente : lecture du cache uniquement.")
        else:
            try:
                fresh = _tavily(query, max_results, api_key)
                if fresh:
                    write_cache("search", key, fresh)
            except (httpx.HTTPError, ValueError) as exc:
                warnings.append(f"Tavily indisponible ({type(exc).__name__}) : cache utilisé.")
    return read_cache_file(path)[:max_results]
