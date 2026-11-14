"""Evidence registry (PRD 3.4, 3.5). Orchestrator-owned."""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable, Mapping

from alphaforge.state import Evidence

PREFIXES = {
    "ES": "screening",
    "EQ": "quant",
    "EM": "macro",
    "EN": "news",
    "EP": "portfolio",
}

# Matches evidence ids inside free text, e.g. "EQ12". Used by the verifier.
EID_RE = re.compile(r"\bE[SQMNP]\d+\b")


class EvidenceRegistry:
    """Per-node registry. Ids are `<prefix><n>`, numbered in insertion order.

    Insert in a stable order (sorted tickers, fixed metric order) so that two runs on the
    same input give the same ids.
    """

    def __init__(self, prefix: str, start: int = 1):
        if prefix not in PREFIXES:
            raise ValueError(f"unknown evidence prefix {prefix!r}; use one of {sorted(PREFIXES)}")
        self.prefix = prefix
        self._next = start
        self._items: dict[str, Evidence] = {}

    def add(
        self,
        value: float | str | dict,
        source: str,
        date: dt.date,
        method: str,
        *,
        date_kind: str = "observation",
        url: str | None = None,
        confidence: str = "fact",
    ) -> str:
        eid = f"{self.prefix}{self._next}"
        self._next += 1
        self._items[eid] = Evidence(
            id=eid,
            value=value,
            source=source,
            date=date,
            date_kind=date_kind,
            url=url,
            method=method,
            confidence=confidence,
        )
        return eid

    def get(self, eid: str) -> Evidence:
        return self._items[eid]

    def items(self) -> dict[str, Evidence]:
        """What a node returns under the `evidence` key."""
        return dict(self._items)


def find(evidence: Mapping[str, Evidence], **match) -> list[Evidence]:
    """Evidence whose dict value matches every key, e.g. find(ev, metric="volatility_ann", ticker="TSLA").

    For pairwise metrics pass tickers=["SPY", "QQQ"]; order does not matter.
    """
    out = []
    for ev in evidence.values():
        v = ev.value
        if not isinstance(v, dict):
            continue
        ok = True
        for k, want in match.items():
            got = v.get(k)
            if k == "tickers" and isinstance(got, Iterable) and not isinstance(got, str):
                ok = sorted(got) == sorted(want)
            else:
                ok = got == want
            if not ok:
                break
        if ok:
            out.append(ev)
    return out


def find_one(evidence: Mapping[str, Evidence], **match) -> Evidence | None:
    hits = find(evidence, **match)
    return hits[0] if hits else None


def numeric(ev: Evidence) -> float | None:
    """The number carried by an evidence entry, if any."""
    v = ev.value
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict) and isinstance(v.get("value"), (int, float)):
        return float(v["value"])
    return None
