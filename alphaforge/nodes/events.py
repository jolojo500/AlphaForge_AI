"""Agent 2: news and events (PRD 5.5). STUB: Track B replaces the body in B-5."""

from __future__ import annotations

from alphaforge.evidence import EvidenceRegistry
from alphaforge.state import GraphState
from alphaforge.tracing import traced


@traced("events")
def events_node(state: GraphState) -> dict:
    reg = EvidenceRegistry("EN")
    idea = state.profile.requested_idea if state.profile else None
    ticker = idea["ticker"] if idea else "SPY"
    headline = f"Exemple d'actualité concernant {ticker}"
    eid = reg.add(
        value={"metric": "news", "ticker": ticker, "value": headline},
        source="stub",
        date=state.as_of_date,
        date_kind="publication",
        method="fictional placeholder",
        confidence="fictional",
    )
    event = {
        "ticker": ticker,
        "headline": headline,
        "published_at": state.as_of_date.isoformat(),
        "relevant": True,
        "kind": "fact",
        "risk_type": "market",
        "material": False,
        "evidence_id": eid,
    }
    return {"events": [event], "evidence": reg.items(), "summary": "1 actualité retenue [stub]."}
