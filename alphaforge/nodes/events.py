"""Agent 2: news and events (PRD 5.5). Owned by Track B.

The only node with agency: a small ReAct loop where a model picks what to look up next
(news for a ticker, a web search, an ETF's holdings), bounded by a tool-call budget. Each
retained item is classified (relevant, fact vs opinion, risk type, material) on the fast
model, with a rule-based fallback, and registered as `EN` evidence.

Rules: items dated after the as-of date are dropped; the provider's publication timestamp is
kept; news feeds the present-day view only. Budget: 8 tool calls, 40 classified items.
"""
from __future__ import annotations

import csv
import datetime as dt
import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel

from alphaforge import config, llm
from alphaforge.evidence import EvidenceRegistry
from alphaforge.state import GraphState
from alphaforge.tools.news import NewsItem, fetch_company_news, fetch_etf_holdings
from alphaforge.tools.search import web_search
from alphaforge.tracing import traced

MAX_TOOL_CALLS = 8
MAX_CLASSIFIED = 40
MAX_EVENTS = 12
LOOKBACK_DAYS = 180
TOP_HOLDINGS = 2

ENERGY_NAMES = ("XOM", "ENB.TO", "CNQ.TO")


@lru_cache(maxsize=1)
def _universe() -> dict[str, dict]:
    with open(config.STARTER_DIR / "assets_universe.csv", newline="") as f:
        return {r["ticker"]: r for r in csv.DictReader(f)}


RiskType = Literal[
    "market", "credit", "liquidity", "rates_inflation", "currency", "concentration", "controversy"
]


class Classification(BaseModel):
    relevant: bool
    kind: Literal["fact", "opinion"]
    risk_type: RiskType
    material: bool


class Action(BaseModel):
    action: Literal["news", "search", "holdings", "done"]
    ticker: str | None = None
    query: str | None = None


# ----------------------------------------------------------------------- classification
_CLASSIFY_SYSTEM = (
    "You classify one news item for an investor risk tool. Judge only the text given. "
    "relevant: true if it can inform the risk of holding the focus asset. A regulatory filing "
    "by the focus company (8-K, 10-Q) is always relevant; materiality, not relevance, separates "
    "routine filings from important ones. Off-topic items (sponsorships, awards) are not relevant. "
    "kind: 'fact' for a reported event or filing, 'opinion' for analysis, forecasts or commentary. "
    "risk_type: market (price, earnings, business), credit (debt, default, downgrade), liquidity "
    "(trading halts, delisting, redemption limits), rates_inflation, currency, concentration "
    "(single customer, supplier or product dependence), controversy (lawsuit, investigation, "
    "recall, ban, strike, fraud, ESG or governance scandal). "
    "material: true only for an event likely to change the asset's risk picture."
)

_MATERIAL_ITEMS = {"1.01", "1.02", "2.03", "2.04", "2.05", "2.06", "3.01", "4.01", "4.02", "5.01", "5.02"}
_RULES: list[tuple[RiskType, re.Pattern]] = [
    ("controversy", re.compile(
        r"lawsuit|sued|investigat|probe|recall|ban(?:ned)?\b|strike|fraud|scandal|violation|"
        r"subpoena|class action|poursuite|enquête|rappel|grève|fraude|non-reliance|\b4\.02\b", re.I)),
    ("controversy", re.compile(r"exempt solicitation|conflict minerals|payments to governments", re.I)),
    ("credit", re.compile(
        r"downgrad|default|bankruptcy|going concern|debt|notes due|credit|\b2\.0[34]\b|"
        r"prospectus supplement", re.I)),
    ("liquidity", re.compile(r"delist|halt|suspend|redemption|liquidity|\b3\.01\b", re.I)),
    ("rates_inflation", re.compile(r"interest rate|inflation|\bcpi\b|central bank|fed\b|taux d'intérêt", re.I)),
    ("currency", re.compile(r"currency|exchange rate|\bfx\b|dollar|devise", re.I)),
    ("concentration", re.compile(r"single customer|largest customer|sole supplier|dependence|concentration", re.I)),
]
_OPINION = re.compile(
    r"analyst|expects?|forecast|could|may |might|should|predict|outlook|price target|"
    r"overvalued|undervalued|opinion|selon|prévoit|pourrait|\bbuy rating\b|\bupgrade\b", re.I)
_OFFTOPIC = re.compile(r"marathon|charity|sponsor|anniversary|award|recipe|festival|podcast", re.I)
_ITEM_RE = re.compile(r"\b(\d\.\d{2})\b")


def heuristic_classify(item: NewsItem) -> Classification:
    """Rule-based classifier used when the model is unavailable."""
    # Filing summaries are boilerplate, so only the headline is read for them.
    text = item.headline if item.provider == "sec_edgar" else f"{item.headline} {item.summary}"
    risk: RiskType = "market"
    for name, rx in _RULES:
        if rx.search(text):
            risk = name
            break
    items = set(_ITEM_RE.findall(item.headline)) if item.provider == "sec_edgar" else set()
    # Filing items 9.01 / 7.01 alone are exhibits and disclosures, not risk events.
    kind: Literal["fact", "opinion"] = "opinion" if _OPINION.search(item.headline) else "fact"
    if item.provider == "sec_edgar":
        kind = "fact"
    material = bool(items & _MATERIAL_ITEMS) or "2.02" in items or (
        risk == "controversy" and item.provider != "sec_edgar"
    )
    if item.provider != "sec_edgar" and risk == "market":
        material = False
    relevant = not _OFFTOPIC.search(text)
    return Classification(relevant=relevant, kind=kind, risk_type=risk, material=material)


def classify_item(item: NewsItem, focus: str, llm_client=None) -> tuple[Classification, str]:
    """Classify one item on the fast model. Returns (classification, "llm" | "rules")."""
    prompt = (
        f"Focus asset: {focus}\nPublisher: {item.source}\nHeadline: {item.headline}\n"
        f"Summary: {item.summary[:400]}"
    )
    try:
        return (
            llm.call_json(prompt, Classification, kind="fast", system=_CLASSIFY_SYSTEM, llm=llm_client),
            "llm",
        )
    except llm.LLMError:
        return heuristic_classify(item), "rules"


# ----------------------------------------------------------------------- planning
def default_plan(state: GraphState) -> list[tuple[str, str]]:
    """Fixed query plan, used first and whenever the planner model is unavailable."""
    p = state.profile
    eligible = set(state.eligible_universe)
    plan: list[tuple[str, str]] = []
    if p and p.requested_idea:
        t = p.requested_idea["ticker"]
        plan.append(("news", t))
        if _universe().get(t, {}).get("asset_class", "").startswith("etf"):
            plan.append(("holdings", t))
    if p and "no_controversies" in p.constraints:
        for t in ENERGY_NAMES:
            if t in eligible:
                plan.append(("news", t))
                plan.append(("search", f"{_universe()[t]['name']} ESG controversy"))
    if p and "likes_crypto" in p.preferences and "BTC-USD" in eligible:
        plan.append(("news", "BTC-USD"))
    if p and "likes_tech" in p.preferences:
        plan += [("news", t) for t in ("NVDA", "TSLA") if t in eligible]
    if not plan:
        plan.append(("holdings", "SPY"))
    return list(dict.fromkeys(plan))


def _plan_prompt(state: GraphState, log: list[str], left: int, suggestion: list) -> str:
    p = state.profile
    return (
        f"Investor: tolerance={p.risk_tolerance}, horizon={p.horizon_years} years, "
        f"constraints={p.constraints}, request type={p.request_type}, idea={p.requested_idea}.\n"
        f"Tool calls left: {left}.\nAllowed tickers: {', '.join(sorted(state.eligible_universe))}.\n"
        f"Done so far: {log or 'nothing'}.\nSuggested next steps: {suggestion[:3] or 'none'}.\n"
        "Pick ONE next lookup that most improves the risk picture of what the investor asks about, "
        "or 'done'. Actions: news(ticker), search(query), holdings(etf ticker)."
    )


def _valid(action: Action, state: GraphState, seen: set) -> tuple[str, str] | None:
    universe = _universe()
    if action.action == "news" and action.ticker in universe:
        call = ("news", action.ticker)
    elif action.action == "holdings" and (action.ticker or "") in universe:
        call = ("holdings", action.ticker)
    elif action.action == "search" and action.query and 3 <= len(action.query) <= 120:
        call = ("search", action.query.strip())
    else:
        return None
    return None if call in seen else call


# ----------------------------------------------------------------------- the loop
def planner_enabled() -> bool:
    """The model picks lookups only when fresh data can be fetched; otherwise the fixed plan runs."""
    import os

    live = (config.NEWS_MODE or "cache").lower() == "live"
    return live and bool(os.getenv("FINNHUB_API_KEY") or os.getenv("TAVILY_API_KEY"))


def gather(state: GraphState, llm_client=None) -> tuple[list[NewsItem], list[str], list[str], int]:
    """Run the bounded tool loop. Returns (items, warnings, log, calls_used)."""
    as_of = state.as_of_date
    start = as_of - dt.timedelta(days=LOOKBACK_DAYS)
    queue = default_plan(state)
    seen: set[tuple[str, str]] = set()
    items: list[NewsItem] = []
    warnings: list[str] = []
    log: list[str] = []
    while len(seen) < MAX_TOOL_CALLS:
        call = None
        if state.profile and seen and planner_enabled():  # first step: always the fixed plan
            try:
                act = llm.call_json(
                    _plan_prompt(state, log, MAX_TOOL_CALLS - len(seen), queue),
                    Action, kind="fast", llm=llm_client,
                )
            except llm.LLMError:
                act = None
            if act is not None:
                if act.action == "done":
                    break
                call = _valid(act, state, seen)
        if call is None:
            while queue and queue[0] in seen:
                queue.pop(0)
            if not queue:
                break
            call = queue.pop(0)
        seen.add(call)
        tool, arg = call
        if tool == "news":
            got = fetch_company_news(arg, start, as_of, warnings=warnings)
            items += got
            log.append(f"news({arg}) -> {len(got)}")
        elif tool == "search":
            got = [i for i in web_search(arg, warnings=warnings) if i.published_date]
            items += [i for i in got if start <= i.published_date <= as_of]
            log.append(f"search({arg!r}) -> {len(got)}")
        else:
            held = fetch_etf_holdings(arg)
            log.append(f"holdings({arg}) -> {len(held)}")
            for h in held[:TOP_HOLDINGS]:
                if h["ticker"] in _universe():
                    queue.insert(0, ("news", h["ticker"]))
    return items, warnings, log, len(seen)


def _select(items: list[NewsItem], as_of: dt.date) -> list[NewsItem]:
    """Drop look-ahead and duplicates, interleave tickers, cap at MAX_CLASSIFIED."""
    uniq: dict[str, NewsItem] = {}
    titles: set[tuple[str, str, dt.date]] = set()
    for i in items:
        d = i.published_date
        if d is None or d > as_of:
            continue
        key = (i.ticker, re.sub(r"\W+", " ", i.headline.lower()).strip(), d)
        url = i.url or f"{i.provider}:{i.headline}"
        if url in uniq or (key in titles and i.provider != "sec_edgar"):
            continue  # same story from another outlet; filings share titles but not urls
        titles.add(key)
        uniq[url] = i
    by_ticker: dict[str, list[NewsItem]] = {}
    for i in sorted(uniq.values(), key=lambda x: (x.published_at, x.url or ""), reverse=True):
        by_ticker.setdefault(i.ticker, []).append(i)
    out: list[NewsItem] = []
    queues = [by_ticker[k] for k in sorted(by_ticker)]
    while queues and len(out) < MAX_CLASSIFIED:
        for q in list(queues):
            out.append(q.pop(0))
            if not q:
                queues.remove(q)
            if len(out) >= MAX_CLASSIFIED:
                break
    return out


def classify_all(items: list[NewsItem], llm_client=None) -> list[tuple[NewsItem, Classification, str]]:
    def one(i: NewsItem):
        c, how = classify_item(i, i.ticker or "general market", llm_client)
        return i, c, how

    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(one, items))


@traced("events")
def events_node(state: GraphState) -> dict:
    reg = EvidenceRegistry("EN")
    items, warnings, log, calls = gather(state)
    chosen = _select(items, state.as_of_date)
    classified = classify_all(chosen)
    kept = [(i, c, how) for i, c, how in classified if c.relevant]
    kept.sort(key=lambda t: (
        not (t[1].material and t[1].risk_type == "controversy"),  # surfaced first (Mateo)
        not t[1].material, -t[0].published_at.timestamp(), t[0].url or "",
    ))
    # Best item of each ticker first, so one busy filer cannot crowd out the others.
    firsts, seen_t = [], set()
    for t in kept:
        if t[0].ticker not in seen_t:
            seen_t.add(t[0].ticker)
            firsts.append(t)
    rest = [t for t in kept if t not in firsts]
    kept = sorted(firsts, key=kept.index)[:MAX_EVENTS]
    kept += rest[: MAX_EVENTS - len(kept)]

    events = []
    for i, c, how in kept:
        model = "fast model" if how == "llm" else "keyword rules"
        eid = reg.add(
            value={
                "metric": "news", "ticker": i.ticker, "value": i.headline, "kind": c.kind,
                "risk_type": c.risk_type, "material": c.material,
            },
            source=f"{i.source} ({i.provider})",
            date=i.published_date,
            date_kind="publication",
            url=i.url,
            method=f"classified by {model}: {c.kind}, {c.risk_type}, material={c.material}",
            confidence="fact" if c.kind == "fact" else "assumption",
        )
        events.append(
            {
                "ticker": i.ticker,
                "headline": i.headline,
                "published_at": i.published_date.isoformat(),
                "relevant": True,
                "kind": c.kind,
                "risk_type": c.risk_type,
                "material": c.material,
                "evidence_id": eid,
                "url": i.url,
                "source": i.source,
                "classifier": how,
            }
        )
    note = (
        f"{len(chosen)} élément(s) lus, {len(events)} retenu(s) ; outils : {'; '.join(log) or 'aucun'}. "
        + " ".join(warnings)
    ).strip()
    reg.add(
        value={"metric": "news_items_retained", "value": len(events), "note": note},
        source="data/cache/news",
        date=state.as_of_date,
        method="count of news items kept after the as-of filter and classification",
        confidence="fact" if events else "assumption",
    )
    if events:
        summary = f"{len(events)} actualité(s) retenue(s) sur {len(chosen)} lue(s), {calls} appel(s) d'outil."
    else:
        summary = f"Aucune actualité datée avant l'analyse pour cette demande ({calls} appel(s) d'outil)."
    return {"events": events, "evidence": reg.items(), "summary": summary}
