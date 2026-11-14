"""Screening engine (PRD 5.2). STUB: Track A replaces the body in A-5."""

from __future__ import annotations

import csv

from alphaforge import config
from alphaforge.evidence import EvidenceRegistry
from alphaforge.state import GraphState
from alphaforge.tracing import traced


def _universe() -> list[dict]:
    with open(config.STARTER_DIR / "assets_universe.csv", newline="") as f:
        return list(csv.DictReader(f))


@traced("screening")
def screening_node(state: GraphState) -> dict:
    reg = EvidenceRegistry("ES")
    profile = state.profile
    eligible, exclusions = [], []
    for row in sorted(_universe(), key=lambda r: r["ticker"]):
        t = row["ticker"]
        reason = None
        if "no_crypto" in profile.constraints and row["asset_class"] == "crypto":
            reason = "Cryptoactif exclu par les contraintes du profil."
        elif t in profile.excluded_tickers:
            reason = "Actif exclu par l'hypothèse what-if."
        if reason:
            eid = reg.add(
                value={"metric": "exclusion", "ticker": t, "value": reason},
                source="assets_universe.csv",
                date=state.as_of_date,
                method="stub rule on asset_class",
                confidence="fictional",
            )
            exclusions.append({"ticker": t, "reason": reason, "evidence_id": eid})
        else:
            eligible.append(t)
    return {
        "eligible_universe": eligible,
        "exclusions": exclusions,
        "evidence": reg.items(),
        "summary": f"{len(eligible)} actifs admissibles, {len(exclusions)} exclus [stub].",
    }
