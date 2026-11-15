"""Cached ETF holdings (PRD 5.2 ESG screen, 5.3 ETF overlap). Track A.

Files live in data/cache/holdings/<TICKER>.json or data/cache/holdings/<TICKER>/<DATE>.json,
one per ETF (or dated snapshots), fetched and committed:

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


def _normalize_args(
    holdings_dir: Path | str | dt.date | None = None,
    as_of: dt.date | str | None = None,
) -> tuple[Path, dt.date | None]:
    actual_dir: Path = HOLDINGS_DIR
    target_as_of: dt.date | None = None

    if isinstance(holdings_dir, dt.date):
        target_as_of = holdings_dir
    elif isinstance(holdings_dir, str):
        try:
            target_as_of = dt.date.fromisoformat(holdings_dir)
        except ValueError:
            actual_dir = Path(holdings_dir)
    elif isinstance(holdings_dir, Path):
        actual_dir = holdings_dir

    if as_of is not None and target_as_of is None:
        if isinstance(as_of, dt.date):
            target_as_of = as_of
        elif isinstance(as_of, str):
            try:
                target_as_of = dt.date.fromisoformat(as_of)
            except ValueError:
                target_as_of = None

    return actual_dir, target_as_of


def load_holdings(
    etf: str,
    holdings_dir: Path | str | dt.date | None = None,
    as_of: dt.date | str | None = None,
) -> dict | None:
    """The cached holdings document of an ETF, or None if there is no readable file.

    When dated snapshots exist in holdings/<ETF>/<date>.json:
    - picks the latest snapshot at or before as_of (if as_of given)
    - falls back to the earliest future snapshot if none exist before as_of
    - picks the latest overall snapshot when as_of is None
    Falls back to holdings/<ETF>.json if no sub-directory exists.
    """
    base_dir, target_as_of = _normalize_args(holdings_dir, as_of)
    sub_dir = base_dir / etf

    if sub_dir.is_dir():
        candidates: list[tuple[dt.date, Path]] = []
        for file_path in sub_dir.glob("*.json"):
            try:
                d = dt.date.fromisoformat(file_path.stem)
                candidates.append((d, file_path))
            except ValueError:
                doc = _read(str(file_path))
                if doc and "as_of" in doc:
                    try:
                        candidates.append((dt.date.fromisoformat(doc["as_of"]), file_path))
                    except ValueError:
                        pass

        if candidates:
            candidates.sort(key=lambda x: x[0])
            if target_as_of is not None:
                valid = [c for c in candidates if c[0] <= target_as_of]
                chosen = valid[-1][1] if valid else candidates[0][1]
            else:
                chosen = candidates[-1][1]
            return _read(str(chosen))

    flat_file = base_dir / f"{etf}.json"
    return _read(str(flat_file))


def holdings_weights(
    etf: str,
    holdings_dir: Path | str | dt.date | None = None,
    as_of: dt.date | str | None = None,
) -> dict[str, float]:
    """{underlying ticker: weight} for an ETF; empty if no holdings are cached."""
    doc = load_holdings(etf, holdings_dir=holdings_dir, as_of=as_of)
    if not doc:
        return {}
    out: dict[str, float] = {}
    for h in doc.get("holdings", []):
        t, w = h.get("ticker"), h.get("weight")
        if isinstance(t, str) and isinstance(w, (int, float)):
            out[t] = out.get(t, 0.0) + float(w)
    return out


def holdings_date(
    etf: str,
    holdings_dir: Path | str | dt.date | None = None,
    as_of: dt.date | str | None = None,
) -> dt.date | None:
    doc = load_holdings(etf, holdings_dir=holdings_dir, as_of=as_of)
    try:
        return dt.date.fromisoformat(doc["as_of"]) if doc else None
    except (KeyError, TypeError, ValueError):
        return None


def is_complete(
    etf: str,
    holdings_dir: Path | str | dt.date | None = None,
    as_of: dt.date | str | None = None,
) -> bool:
    doc = load_holdings(etf, holdings_dir=holdings_dir, as_of=as_of)
    return bool(doc and doc.get("complete", True))


def is_held(
    etf: str,
    ticker: str,
    holdings_dir: Path | str | dt.date | None = None,
    as_of: dt.date | str | None = None,
) -> bool | None:
    """True if listed. False only when the cached list is complete. None when unknown."""
    weights = holdings_weights(etf, holdings_dir=holdings_dir, as_of=as_of)
    if ticker in weights:
        return True
    if weights and is_complete(etf, holdings_dir=holdings_dir, as_of=as_of):
        return False
    return None


def look_through(
    weights: dict[str, float],
    holdings_dir: Path | str | dt.date | None = None,
    as_of: dt.date | str | None = None,
) -> dict[str, float]:
    """Effective exposure per underlying name: direct weight plus weight held via ETFs.

    An ETF with cached holdings is replaced by its holdings (weight x holding weight). The part
    of a partial list that is not published stays under "<ETF>:other". An ETF without cached
    holdings stays as itself. Example: NVDA 10% + QQQ 50% -> NVDA = 0.10 + 0.50 x 6.5%.
    """
    out: dict[str, float] = {}
    for t, w in weights.items():
        inner = holdings_weights(t, holdings_dir=holdings_dir, as_of=as_of)
        if not inner:
            out[t] = out.get(t, 0.0) + w
            continue
        for name, hw in inner.items():
            out[name] = out.get(name, 0.0) + w * hw
        rest = 1.0 - sum(inner.values())
        if rest > 1e-9:
            out[f"{t}:other"] = out.get(f"{t}:other", 0.0) + w * rest
    return out
