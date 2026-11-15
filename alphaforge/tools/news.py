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
        from alphaforge.secrets import get_secret

        key = get_secret("FINNHUB_API_KEY")
        if not key:
            warnings.append("FINNHUB_API_KEY absente : lecture du cache uniquement.")
        else:
            try:
                fresh = _finnhub(ticker, date_from, date_to, key)
                if fresh:
                    write_cache("finnhub", ticker, fresh)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    warnings.append(f"Finnhub limite de débit atteinte (HTTP 429) pour {ticker} : repli sur le cache.")
                else:
                    warnings.append(f"Finnhub indisponible pour {ticker} (HTTP {exc.response.status_code}) : repli sur le cache.")
            except httpx.TimeoutException:
                warnings.append(f"Finnhub délai d'attente dépassé (timeout) pour {ticker} : repli sur le cache.")
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


# --------------------------------------------------------------------------- SEC EDGAR refresh
# Dated, public-domain filing references. Used to build the committed cache:
#   uv run python -m alphaforge.tools.news
EDGAR_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
EDGAR_UA = os.getenv("AF_EDGAR_USER_AGENT", "AlphaForge Datathon alphaforge.datathon@gmail.com")
# universe ticker -> (CIK, filer label shown in the headline)
EDGAR_FILERS = {
    "TSLA": ("0001318605", "Tesla"),
    "NVDA": ("0001045810", "NVIDIA"),
    "XOM": ("0000034088", "Exxon Mobil"),
    "ENB.TO": ("0000895728", "Enbridge"),
    "BTC-USD": ("0001980994", "iShares Bitcoin Trust (IBIT)"),
}
EDGAR_START = dt.date(2025, 1, 1)
EDGAR_8K_ITEMS = {
    "1.01": "Entry into a Material Definitive Agreement",
    "1.02": "Termination of a Material Definitive Agreement",
    "1.05": "Material Cybersecurity Incidents",
    "2.01": "Completion of Acquisition or Disposition of Assets",
    "2.02": "Results of Operations and Financial Condition",
    "2.03": "Creation of a Direct Financial Obligation",
    "2.04": "Triggering Events That Accelerate a Financial Obligation",
    "2.05": "Costs Associated with Exit or Disposal Activities",
    "2.06": "Material Impairments",
    "3.01": "Notice of Delisting or Failure to Satisfy a Listing Rule",
    "3.02": "Unregistered Sales of Equity Securities",
    "3.03": "Material Modification to Rights of Security Holders",
    "4.01": "Changes in Registrant's Certifying Accountant",
    "4.02": "Non-Reliance on Previously Issued Financial Statements",
    "5.01": "Changes in Control of Registrant",
    "5.02": "Departure or Appointment of Directors or Officers",
    "5.03": "Amendments to Articles of Incorporation or Bylaws",
    "5.07": "Submission of Matters to a Vote of Security Holders",
    "7.01": "Regulation FD Disclosure",
    "8.01": "Other Events",
    "9.01": "Financial Statements and Exhibits",
}
EDGAR_FORMS = {
    "10-Q": "quarterly report",
    "10-K": "annual report",
    "DEF 14A": "definitive proxy statement (shareholder vote)",
    "DEFA14A": "additional proxy soliciting materials",
    "PX14A6G": "notice of exempt solicitation by a shareholder group",
    "SD": "specialized disclosure (conflict minerals or payments to governments)",
    "424B2": "prospectus supplement for a debt or securities offering",
    "424B5": "prospectus supplement for a debt or securities offering",
}


def edgar_headline(label: str, form: str, items: str) -> str | None:
    """Headline built from the SEC form type and 8-K item numbers (the document is not read)."""
    if form in ("8-K", "8-K/A"):
        codes = [c for c in (items or "").split(",") if c]
        if not codes:
            return f"{label}: Form {form} filing"
        desc = "; ".join(f"{c} {EDGAR_8K_ITEMS.get(c, '')}".strip() for c in codes)
        return f"{label}: Form {form}, items {desc}"
    if form in EDGAR_FORMS:
        return f"{label}: Form {form}, {EDGAR_FORMS[form]}"
    return None  # insider forms, 13G and the like are not risk events


def fetch_edgar_filings(ticker: str, until: dt.date, since: dt.date = EDGAR_START) -> list[NewsItem]:
    cik, label = EDGAR_FILERS[ticker]
    r = httpx.get(EDGAR_URL.format(cik=cik), headers={"User-Agent": EDGAR_UA}, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    rec = r.json()["filings"]["recent"]
    out = []
    for i, form in enumerate(rec["form"]):
        filed = dt.date.fromisoformat(rec["filingDate"][i])
        if not since <= filed <= until:
            continue
        headline = edgar_headline(label, form, rec["items"][i])
        if headline is None:
            continue
        acc = rec["accessionNumber"][i].replace("-", "")
        doc = rec["primaryDocument"][i]
        out.append(
            NewsItem(
                ticker=ticker,
                headline=headline,
                summary=(
                    "SEC EDGAR filing reference; the headline is derived from the form type and "
                    "item numbers, not from the document text."
                ),
                source="SEC EDGAR",
                url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{doc}",
                published_at=dt.datetime.combine(filed, dt.time(), dt.UTC),
                provider="sec_edgar",
            )
        )
    return out


def refresh_edgar_cache(until: dt.date | None = None) -> dict[str, int]:
    """Rebuild data/cache/news/sec_edgar_<TICKER>.json for every filer in EDGAR_FILERS."""
    import time

    until = until or config.DEFAULT_AS_OF
    counts = {}
    for ticker in EDGAR_FILERS:
        items = fetch_edgar_filings(ticker, until)
        path = cache_path("sec_edgar", ticker)
        path.unlink(missing_ok=True)
        write_cache("sec_edgar", ticker, items)
        counts[ticker] = len(items)
        time.sleep(0.3)  # SEC fair-access policy: at most 10 requests per second
    return counts


if __name__ == "__main__":
    print(refresh_edgar_cache())
