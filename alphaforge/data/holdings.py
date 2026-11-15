"""Cached ETF holdings (PRD 5.2 ESG screen, 5.3 ETF overlap). Track A.

Files live in data/cache/holdings/<TICKER>.json, one per ETF, fetched once and committed:

    {"ticker", "as_of", "source_url", "source_name", "retrieved_at",
     "complete", "total_holdings", "coverage_weight",
     "holdings": [{"ticker", "name", "weight"}]}       weight is a fraction (0.079 = 7.9%)

`complete` is false when only the top holdings were published (then absence from the list
proves nothing). Underlying tickers use the universe convention (TSX names end in ".TO").
See data/cache/holdings/README.md for sources and processing.
"""

from __future__ import annotations

import datetime as dt
import functools
import json
from pathlib import Path

from alphaforge import config

HOLDINGS_DIR = config.CACHE_DIR / "holdings"


@functools.cache
def _read(path: str) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_holdings(etf: str, holdings_dir: Path | None = None) -> dict | None:
    """The cached holdings document of an ETF, or None if there is no readable file."""
    return _read(str((holdings_dir or HOLDINGS_DIR) / f"{etf}.json"))


def holdings_weights(etf: str, holdings_dir: Path | None = None) -> dict[str, float]:
    """{underlying ticker: weight} for an ETF; empty if no holdings are cached."""
    doc = load_holdings(etf, holdings_dir)
    if not doc:
        return {}
    out: dict[str, float] = {}
    for h in doc.get("holdings", []):
        t, w = h.get("ticker"), h.get("weight")
        if isinstance(t, str) and isinstance(w, (int, float)):
            out[t] = out.get(t, 0.0) + float(w)
    return out


def holdings_date(etf: str, holdings_dir: Path | None = None) -> dt.date | None:
    doc = load_holdings(etf, holdings_dir)
    try:
        return dt.date.fromisoformat(doc["as_of"]) if doc else None
    except (KeyError, TypeError, ValueError):
        return None


def is_complete(etf: str, holdings_dir: Path | None = None) -> bool:
    doc = load_holdings(etf, holdings_dir)
    return bool(doc and doc.get("complete", True))


def is_held(etf: str, ticker: str, holdings_dir: Path | None = None) -> bool | None:
    """True if listed. False only when the cached list is complete. None when unknown."""
    weights = holdings_weights(etf, holdings_dir)
    if ticker in weights:
        return True
    if weights and is_complete(etf, holdings_dir):
        return False
    return None


def look_through(weights: dict[str, float], holdings_dir: Path | None = None) -> dict[str, float]:
    """Effective exposure per underlying name: direct weight plus weight held via ETFs.

    An ETF with cached holdings is replaced by its holdings (weight x holding weight). The part
    of a partial list that is not published stays under "<ETF>:other". An ETF without cached
    holdings stays as itself. Example: NVDA 10% + QQQ 50% -> NVDA = 0.10 + 0.50 x 6.5%.
    """
    out: dict[str, float] = {}
    for t, w in weights.items():
        inner = holdings_weights(t, holdings_dir)
        if not inner:
            out[t] = out.get(t, 0.0) + w
            continue
        for name, hw in inner.items():
            out[name] = out.get(name, 0.0) + w * hw
        rest = 1.0 - sum(inner.values())
        if rest > 1e-9:
            out[f"{t}:other"] = out.get(f"{t}:other", 0.0) + w * rest
    return out
