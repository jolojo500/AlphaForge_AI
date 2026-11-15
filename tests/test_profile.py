import datetime as dt
import json
import uuid
from pathlib import Path

import pytest

from alphaforge import llm
from alphaforge.graph import initial_state, resume_run, stream_run
from alphaforge.nodes import profile as prof
from alphaforge.nodes.profile import profile_node
from alphaforge.personas import PERSONAS
from alphaforge.risk import effective_risk
from alphaforge.state import GraphState

FIXTURES = Path(__file__).parent / "fixtures" / "llm"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"profile_{name}.json").read_text(encoding="utf-8"))


class Canned:
    """Override that answers the profile extraction with fixed replies, in order."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0
        self.kinds = []

    def __call__(self, messages, kind):
        self.calls += 1
        self.kinds.append(kind)
        r = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return r if isinstance(r, str) else json.dumps(r)


@pytest.fixture
def canned():
    def _use(*replies):
        fake = Canned(*replies)
        llm.set_llm_override(fake)
        return fake

    return _use


def _state(persona, text):
    return GraphState(as_of_date=dt.date(2026, 11, 12), persona=persona, request_text=text)


def _run(persona, text):
    return profile_node(_state(persona, text))["profile"]


# ---- the three canonical requests: expected profile, no question
def test_amira_no_question(canned):
    canned(fixture("amira"))
    assert prof.needs_clarification(PERSONAS["amira"]["example_request"], prof.Extraction()) is None
    p = _run("amira", PERSONAS["amira"]["example_request"])
    assert (p.request_type, p.risk_tolerance, p.risk_capacity) == ("build", "high", "high")
    assert p.budget_cad == 100000 and p.horizon_years == 15
    assert p.constraints == [] and p.conflicts == []
    assert "likes_tech" in p.preferences and p.preferences.count("likes_crypto") == 1


def test_mateo_no_question_keeps_hard_constraints(canned):
    canned(fixture("mateo"))
    assert prof.needs_clarification(PERSONAS["mateo"]["example_request"], prof.Extraction()) is None
    p = _run("mateo", PERSONAS["mateo"]["example_request"])
    assert p.request_type == "build" and p.risk_tolerance == "moderate"
    assert set(p.constraints) == {"no_crypto", "esg_only", "no_controversies"}


def test_robert_tsla_is_judged_with_conflict(canned):
    canned(fixture("robert"))
    p = _run("robert", PERSONAS["robert"]["example_request"])
    assert p.request_type == "judge"
    assert p.requested_idea == {"ticker": "TSLA", "weight": 0.25}
    assert p.conflicts and "TSLA" in p.conflicts[0]  # deterministic rule first
    assert len(p.conflicts) == 2  # plus what the model reported
    assert p.risk_tolerance == "low_moderate" and p.risk_capacity == "low"


def test_model_cannot_drop_or_invent_constraints(canned):
    canned({"request_type": "build", "extra_constraints": ["not_a_rule"]})
    p = _run("robert", "Je veux un portefeuille stable.")
    assert p.constraints == ["no_crypto"]


def test_unknown_ticker_is_not_kept(canned):
    canned({"request_type": "judge", "ticker": "ZZZZ", "weight_pct": 10})
    p = _run("amira", "10 % dans ZZZZ")
    assert p.requested_idea is None and p.request_type == "build"


def test_unparseable_reply_falls_back_to_persona_table(canned):
    fake = canned("garbage", "still garbage")
    p = _run("robert", PERSONAS["robert"]["example_request"])
    assert fake.calls == 2  # first try + one repair
    assert p.requested_idea == {"ticker": "TSLA", "weight": 0.25}
    assert any(c.startswith("Hypothèse") for c in p.conflicts)
    assert p.risk_tolerance == "low_moderate"


def test_offline_fallback_without_llm():
    p = _run("robert", PERSONAS["robert"]["example_request"])
    assert p.request_type == "judge" and p.requested_idea["ticker"] == "TSLA"


# ---- parsing
@pytest.mark.parametrize(
    "text,ticker,weight",
    [
        ("Je veux mettre un quart de mon portefeuille dans Tesla.", "TSLA", 25.0),
        ("La moitié dans Nvidia", "NVDA", 50.0),
        ("10 pour cent en SPY", "SPY", 10.0),
        ("Mettre 12,5 % dans Shopify", "SHOP.TO", 12.5),
        ("un tiers dans XIU", "XIU.TO", 33.33),
    ],
)
def test_regex_reads_tickers_and_weights_in_words(text, ticker, weight):
    e = prof._regex_extract(text)
    assert (e.ticker, e.weight_pct) == (ticker, weight)


def test_detect_conflict_rules():
    kw = dict(tolerance="low_moderate", horizon_years=4, constraints=["no_crypto"])
    assert prof.detect_conflict(**kw, idea=None) == []
    assert prof.detect_conflict(**kw, idea={"ticker": "TSLA", "weight": 0.05}) == []
    assert prof.detect_conflict(**kw, idea={"ticker": "TSLA", "weight": 0.25})
    assert prof.detect_conflict(**kw, idea={"ticker": "SPY", "weight": 0.5}) == []
    assert "exclu" in prof.detect_conflict(**kw, idea={"ticker": "BTC-USD", "weight": 0.02})[0]
    short = dict(tolerance="high", horizon_years=3, constraints=[])
    assert prof.detect_conflict(**short, idea={"ticker": "ETH-USD", "weight": 0.05})
    # 12-month loss tolerance conflicts
    c5 = prof.detect_conflict(tolerance="high", horizon_years=10, constraints=[], idea=None, max_loss_pct=5)
    assert any("5 %" in c and "élevée" in c for c in c5)
    c15 = prof.detect_conflict(tolerance="high", horizon_years=10, constraints=[], idea=None, max_loss_pct=15)
    assert any("15 %" in c and "élevée" in c for c in c15)
    c25 = prof.detect_conflict(tolerance="moderate", horizon_years=10, constraints=[], idea=None, max_loss_pct=25)
    assert c25 == []


def test_effective_risk_is_the_more_conservative_level():
    assert effective_risk("high", "low") == "low"
    assert effective_risk("low_moderate", "low") == "low"
    assert effective_risk("moderate", "high") == "moderate"
    assert effective_risk("high", "high") == "high"


def test_detect_conflict_uses_capacity_for_the_single_stock_cap():
    kw = dict(tolerance="low_moderate", capacity="low", horizon_years=4, constraints=["no_crypto"])
    # 5 % is allowed by the stated tolerance but not by the lower capacity (3 %).
    conflicts = prof.detect_conflict(**kw, idea={"ticker": "TSLA", "weight": 0.05})
    assert conflicts and "3%" in conflicts[0] and "capacité" in conflicts[0]
    assert prof.detect_conflict(**kw, idea={"ticker": "TSLA", "weight": 0.03}) == []


def test_wide_tolerance_capacity_gap_adds_a_conflict():
    high_low = prof.detect_conflict(
        tolerance="high", capacity="low", horizon_years=10, constraints=[], idea=None
    )
    assert len(high_low) == 1
    assert "plus d'un niveau" in high_low[0] and "capacité" in high_low[0]
    # One level apart is reported by the caps evidence, not as a profile conflict.
    assert prof.detect_conflict(
        tolerance="high", capacity="moderate", horizon_years=10, constraints=[], idea=None
    ) == []
    assert prof.detect_conflict(
        tolerance="low_moderate", capacity="low", horizon_years=4, constraints=[], idea=None
    ) == []


def test_questionnaire_high_tolerance_low_capacity_profile_reports_the_gap(monkeypatch):
    monkeypatch.setitem(
        PERSONAS,
        "questionnaire",
        {
            "objective": "growth",
            "horizon_years": 10,
            "risk_tolerance": "high",
            "risk_capacity": "low",
            "constraints": [],
            "preferences": [],
            "budget_cad": None,
        },
    )
    p = prof.build_profile("questionnaire", prof.Extraction(), False)
    assert p.risk_tolerance == "high" and p.risk_capacity == "low"
    assert any("plus d'un niveau" in c for c in p.conflicts)


def test_regex_extract_ignores_appended_investor_context():
    text = "Que pensez-vous de TSLA ?\n\n[Contexte investisseur]\nTolérance de perte sur 12 mois : 5 %"
    e = prof._regex_extract(text)
    assert e.ticker == "TSLA"
    assert e.weight_pct is None  # Does not mistake 5% loss limit for TSLA allocation weight


def test_ticker_resolution():
    assert prof._resolve_ticker("tsla") == "TSLA"
    assert prof._resolve_ticker("XIU") == "XIU.TO"
    assert prof._resolve_ticker("nope") is None


def test_needs_clarification_variants():
    e = prof.Extraction
    assert prof.needs_clarification("", e())
    assert prof.needs_clarification("Je veux investir", e())
    assert prof.needs_clarification("TSLA", e(request_type="judge", ticker="TSLA"))
    assert prof.needs_clarification("x", e(ticker="TSLA", weight_pct=5)) is None
    assert prof.needs_clarification("Un portefeuille équilibré", e()) is None


# ---- interrupt flow through the graph
def test_vague_request_asks_exactly_one_question_then_proceeds(canned):
    fake = canned(fixture("amira"))
    tid = uuid.uuid4().hex
    events = list(stream_run(initial_state("amira", "Je veux investir"), tid))
    questions = [e for e in events if e["type"] == "interrupt"]
    assert len(questions) == 1 and questions[0]["question"] == prof.ASK_GOAL
    assert fake.calls == 0  # nothing asked of the model before the answer
    events = list(resume_run("Construire une allocation diversifiée sur 15 ans.", tid))
    assert [e["type"] for e in events].count("interrupt") == 0
    final = events[-1]["state"]
    assert final.profile is not None and final.retries["clarify"] == 1
    assert final.request_text.startswith("Je veux investir ")


def test_missing_weight_question_then_profile(canned):
    canned(fixture("robert"))
    tid = uuid.uuid4().hex
    events = list(stream_run(initial_state("robert", "Je pense à Tesla."), tid))
    assert events[-1]["type"] == "interrupt" and "TSLA" in events[-1]["question"]
    events = list(resume_run("25 %", tid))
    final = events[-1]["state"]
    assert events[-1]["type"] == "final"
    assert final.profile.requested_idea == {"ticker": "TSLA", "weight": 0.25}
    assert "25 %" in final.request_text


def test_at_most_one_question(canned):
    canned({"request_type": "judge", "ticker": "TSLA"})  # weight never provided
    tid = uuid.uuid4().hex
    list(stream_run(initial_state("robert", "Tesla"), tid))
    events = list(resume_run("je ne sais pas", tid))
    assert events[-1]["type"] == "final"
    assert events[-1]["state"].profile.requested_idea is None


def test_contradictory_profile_escalates_to_opus_before_question(canned):
    reply = {
        "request_type": "judge",
        "ticker": "BTC-USD",
        "weight_pct": 100.0,
        "horizon_years": 4,
    }
    fake = canned(reply, reply, reply)
    tid = uuid.uuid4().hex
    events = list(
        stream_run(
            initial_state("amira", "Je prévois ma retraite dans 4 ans et je veux 100 % en crypto"),
            tid,
        )
    )
    questions = [e for e in events if e["type"] == "interrupt"]
    assert len(questions) == 1
    assert "contradit" in questions[0]["question"] or "horizon" in questions[0]["question"]
    assert "review" in fake.kinds
    assert fake.kinds[:2] == ["main", "review"]

    events = list(resume_run("Je préfère allonger mon horizon à 10 ans.", tid))
    assert [e["type"] for e in events].count("interrupt") == 0
    final = events[-1]["state"]
    assert final.profile is not None


@pytest.mark.live
def test_live_opus_escalation_on_contradictory_profile():
    ext, fallback = prof.extract_profile(
        "amira",
        "Je prévois ma retraite dans 4 ans et je veux 100 % en crypto (BTC-USD)",
        kind="review",
    )
    assert not fallback
    assert ext.ticker == "BTC-USD" or "crypto" in str(ext.model_dump())


@pytest.mark.live
@pytest.mark.parametrize("persona", sorted(PERSONAS))
def test_live_canonical_requests(persona):
    p = _run(persona, PERSONAS[persona]["example_request"])
    assert p.persona == persona
    if persona == "robert":
        assert p.request_type == "judge" and p.requested_idea["ticker"] == "TSLA"
        assert p.requested_idea["weight"] == pytest.approx(0.25)
        assert p.conflicts
    else:
        assert p.request_type == "build"
