"""Quant (PRD 5.3). STUB with fictional numbers: Track A replaces the body in A-2."""

from __future__ import annotations

import zlib

from alphaforge.evidence import EvidenceRegistry
from alphaforge.state import GraphState
from alphaforge.tracing import traced


def _fake(ticker: str, metric: str, lo: float, hi: float) -> float:
    h = zlib.crc32(f"{ticker}:{metric}".encode()) % 1000 / 1000
    return round(lo + (hi - lo) * h, 4)


@traced("quant")
def quant_node(state: GraphState) -> dict:
    reg = EvidenceRegistry("EQ")
    for t in sorted(state.eligible_universe):
        for metric, lo, hi in (("volatility_ann", 0.05, 0.7), ("max_drawdown", -0.75, -0.03)):
            reg.add(
                value={"metric": metric, "ticker": t, "value": _fake(t, metric, lo, hi), "unit": "ratio"},
                source="stub",
                date=state.as_of_date,
                method="fictional placeholder, not computed from data",
                confidence="fictional",
            )
    return {"evidence": reg.items(), "summary": "Statistiques de risque calculées [stub]."}
