"""Screening engine (PRD 5.2). Track A: hard constraints applied by code, one reason each.

Constraints are rules, so they live in code and cannot be argued away by a model.
Every exclusion carries a French reason and an ES evidence id.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from alphaforge import config
from alphaforge.data.holdings import load_holdings
from alphaforge.data.provider import get_provider
from alphaforge.evidence import EvidenceRegistry
from alphaforge.state import GraphState, Profile
from alphaforge.tracing import traced

HOLDINGS_DIR = config.CACHE_DIR / "holdings"
UNIVERSE_SOURCE = "assets_universe.csv"
US_MARKETS = {"NYSE", "NASDAQ", "NYSE Arca", "Cboe BZX"}

# constraint token -> (rule on a universe row, French reason)
CLASS_GEO_RULES = {
    "no_crypto": (
        lambda r: r["asset_class"] == "crypto",
        "Cryptoactif exclu par les contraintes du profil.",
    ),
    "no_bonds": (
        lambda r: r["asset_class"] == "etf_bond",
        "Obligations exclues par les contraintes du profil.",
    ),
    "no_commodities": (
        lambda r: r["asset_class"] == "etf_commodity",
        "Matières premières exclues par les contraintes du profil.",
    ),
    "canada_only": (
        lambda r: r["market"] != "TSX",
        "Actif hors Canada exclu (profil limité au Canada).",
    ),
    "us_only": (
        lambda r: r["market"] not in US_MARKETS,
        "Actif hors États-Unis exclu (profil limité aux États-Unis).",
    ),
}


@dataclass(frozen=True)
class Hit:
    """One reason to exclude one ticker, with what the evidence entry needs."""

    ticker: str
    reason: str
    source: str
    method: str
    confidence: str = "fact"
    url: str | None = None
    date: dt.date | None = None


# --- rules --------------------------------------------------------------------------------


def class_and_geo_filters(profile: Profile, universe: pd.DataFrame) -> list[Hit]:
    hits = []
    for constraint in profile.constraints:
        rule = CLASS_GEO_RULES.get(constraint)
        if rule is None:
            continue
        matches, reason = rule
        for _, row in universe.iterrows():
            if matches(row):
                hits.append(
                    Hit(row["ticker"], reason, UNIVERSE_SOURCE, f"constraint {constraint} on asset_class/market")
                )
    return hits


def load_esgv(holdings_dir: Path | None = None) -> dict | None:
    """Cached ESGV holdings (A-4 format), or None if the file is missing or unreadable."""
    return load_holdings("ESGV", holdings_dir or HOLDINGS_DIR)


def esg_exclusions(
    profile: Profile, universe: pd.DataFrame, holdings_dir: Path | None = None
) -> tuple[list[Hit], list[str]]:
    """Exclusions and coverage notes for `esg_only`. Notes become assumption evidence."""
    if "esg_only" not in profile.constraints:
        return [], []

    hits, notes = [], []
    energy = universe[universe["sector"] == "Energy"]
    for t in energy["ticker"]:
        hits.append(
            Hit(
                t,
                "Secteur de l'énergie exclu par le critère ESG du profil.",
                UNIVERSE_SOURCE,
                "esg_only: energy sector excluded (fossil-fuel exposure)",
                confidence="assumption",
            )
        )

    us_stocks = universe[
        (universe["asset_class"] == "equity")
        & universe["market"].isin(US_MARKETS)
        & (universe["sector"] != "Energy")
    ]
    esgv = load_esgv(holdings_dir)
    if esgv is None:
        notes.append(
            "Composition du FNB Vanguard ESGV non disponible : le filtre ESG se limite "
            "à l'exclusion du secteur de l'énergie."
        )
    else:
        held = {h.get("ticker") for h in esgv.get("holdings", [])}
        complete = esgv.get("complete", True)
        try:
            as_of = dt.date.fromisoformat(esgv.get("as_of", ""))
        except ValueError:
            as_of = None
        unknown = [t for t in us_stocks["ticker"] if t not in held and not complete]
        if unknown:
            notes.append(
                f"Seules les principales positions d'ESGV sont publiées ({len(held)} sur "
                f"{esgv.get('total_holdings', '?')}, au {esgv.get('as_of', '?')}) : "
                f"{', '.join(unknown)} n'y figurent pas, sans que leur absence du fonds soit "
                "établie. Ils ne sont donc pas exclus pour ce motif."
            )
        for t in us_stocks["ticker"]:
            if t not in held and complete:
                hits.append(
                    Hit(
                        t,
                        "Absent du FNB Vanguard ESGV (indice filtré ESG) : exclu par le critère "
                        "ESG du profil.",
                        "Vanguard ESGV holdings",
                        f"membership in ESGV holdings as of {esgv.get('as_of', 'unknown')}",
                        url=esgv.get("source_url"),
                        date=as_of,
                    )
                )

    notes.append(
        "Les actions canadiennes ne font pas partie de l'univers américain d'ESGV : elles ne "
        "sont pas exclues pour cette absence, seul le filtre sectoriel s'applique."
    )
    notes.append(
        "Les FNB larges (SPY, QQQ, XIU.TO) ne sont pas filtrés : ils peuvent contenir des "
        "sociétés que le critère ESG exclurait."
    )
    return hits, notes


def apply_constraints(
    profile: Profile, universe: pd.DataFrame, holdings_dir: Path | None = None
) -> tuple[list[str], list[Hit], list[str]]:
    """Eligible tickers, one Hit per excluded ticker (first reason wins), coverage notes."""
    hits = [
        Hit(t, "Actif exclu par l'hypothèse what-if.", "what-if", "excluded_tickers set by the user")
        for t in sorted(profile.excluded_tickers)
        if t in set(universe["ticker"])
    ]
    hits += class_and_geo_filters(profile, universe)
    esg_hits, notes = esg_exclusions(profile, universe, holdings_dir)
    hits += esg_hits

    first: dict[str, Hit] = {}
    for h in hits:
        first.setdefault(h.ticker, h)
    eligible = sorted(t for t in universe["ticker"] if t not in first)
    return eligible, [first[t] for t in sorted(first)], notes


# --- node ---------------------------------------------------------------------------------


@traced("screening")
def screening_node(state: GraphState) -> dict:
    reg = EvidenceRegistry("ES")
    universe = get_provider().universe().sort_values("ticker", ignore_index=True)
    profile = state.profile
    if profile is None:
        return {
            "eligible_universe": list(universe["ticker"]),
            "evidence": reg.items(),
            "summary": "Profil absent : aucun filtre appliqué.",
        }

    eligible, hits, notes = apply_constraints(profile, universe)
    for note in notes:
        reg.add(
            note,
            source=UNIVERSE_SOURCE,
            date=state.as_of_date,
            method="screening coverage note",
            confidence="assumption",
        )

    requested = (profile.requested_idea or {}).get("ticker")
    exclusions = []
    for h in hits:
        eid = reg.add(
            {"metric": "exclusion", "ticker": h.ticker, "value": h.reason},
            source=h.source,
            date=h.date or state.as_of_date,
            method=h.method,
            url=h.url,
            confidence=h.confidence,
        )
        ex = {"ticker": h.ticker, "reason": h.reason, "evidence_id": eid}
        if h.ticker == requested:
            ex["requested"] = True  # never silently dropped: the scenario builder flags it
        exclusions.append(ex)

    summary = f"{len(eligible)} actifs admissibles, {len(exclusions)} exclus."
    if any(ex.get("requested") for ex in exclusions):
        summary += f" L'actif demandé ({requested}) est exclu par une contrainte et sera signalé."
    return {
        "eligible_universe": eligible,
        "exclusions": exclusions,
        "evidence": reg.items(),
        "summary": summary,
    }
