import datetime as dt
import json
import uuid

import pytest

from alphaforge import llm
from alphaforge.graph import initial_state, resume_run, stream_run
from alphaforge.nodes import profile as prof
from alphaforge.nodes.profile import profile_node
from alphaforge.personas import PERSONAS
from alphaforge.state import GraphState


class FakeMsg:
    def __init__(self, content):
        self.content = content


class FakeLLM:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        r = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return FakeMsg(r if isinstance(r, str) else json.dumps(r))


@pytest.fixture
def use_llm(monkeypatch):
    def _use(*replies):
        fake = FakeLLM(*replies)
        monkeypatch.setenv("AF_LLM_OFFLINE", "0")
        monkeypatch.setattr(llm, "get_llm", lambda kind="main": fake)
        return fake

    return _use


def _state(persona, text):
    return GraphState(as_of_date=dt.date(2026, 11, 12), persona=persona, request_text=text)


def _run(persona, text):
    return profile_node(_state(persona, text))["profile"]


# Three persona fixtures: expected Profile, no question.
AMIRA = {
    "request_type": "build",
    "budget_cad": 100000,
    "horizon_years": 15,
    "extra_preferences": ["Likes Tech", "likes_crypto"],
}
MATEO = {"request_type": "build", "horizon_years": 10, "extra_constraints": ["no_controversies"]}
ROBERT = {"request_type": "judge", "ticker": "TSLA", "weight_pct": 25}


def test_amira_no_question(use_llm):
    use_llm(AMIRA)
    p = _run("amira", PERSONAS["amira"]["example_request"])
    assert (p.request_type, p.risk_tolerance, p.risk_capacity) == ("build", "high", "high")
    assert p.budget_cad == 100000 and p.horizon_years == 15
    assert p.constraints == [] and p.conflicts == []
    assert "likes_tech" in p.preferences and p.preferences.count("likes_crypto") == 1


def test_mateo_no_question_keeps_hard_constraints(use_llm):
    use_llm(MATEO)
    p = _run("mateo", PERSONAS["mateo"]["example_request"])
    assert p.request_type == "build" and p.risk_tolerance == "moderate"
    assert set(p.constraints) == {"no_crypto", "esg_only", "no_controversies"}


def test_robert_tsla_is_judged_with_conflict(use_llm):
    use_llm(ROBERT)
    p = _run("robert", PERSONAS["robert"]["example_request"])
    assert p.request_type == "judge"
    assert p.requested_idea == {"ticker": "TSLA", "weight": 0.25}
    assert p.conflicts and "TSLA" in p.conflicts[0]
    assert p.risk_tolerance == "low_moderate" and p.risk_capacity == "low"


def test_model_cannot_drop_persona_constraints(use_llm):
    use_llm({"request_type": "build", "extra_constraints": ["not_a_rule"]})
    p = _run("robert", "Je veux un portefeuille stable.")
    assert p.constraints == ["no_crypto"]


def test_unknown_ticker_is_not_kept(use_llm):
    use_llm({"request_type": "judge", "ticker": "ZZZZ", "weight_pct": 10})
    p = _run("amira", "10 % dans ZZZZ")
    assert p.requested_idea is None and p.request_type == "build"


def test_invalid_json_falls_back_to_persona_table(use_llm):
    fake = use_llm("garbage", "still garbage")
    p = _run("robert", PERSONAS["robert"]["example_request"])
    assert fake.calls == 2  # first try + one repair
    assert p.requested_idea == {"ticker": "TSLA", "weight": 0.25}
    assert any(c.startswith("Hypothèse") for c in p.conflicts)
    assert p.risk_tolerance == "low_moderate"


def test_offline_fallback_without_llm():
    p = _run("robert", PERSONAS["robert"]["example_request"])
    assert p.request_type == "judge" and p.requested_idea["ticker"] == "TSLA"


def test_detect_conflict_rules():
    kw = dict(tolerance="low_moderate", horizon_years=4, constraints=["no_crypto"])
    assert prof.detect_conflict(**kw, idea=None) == []
    assert prof.detect_conflict(**kw, idea={"ticker": "TSLA", "weight": 0.05}) == []
    assert prof.detect_conflict(**kw, idea={"ticker": "TSLA", "weight": 0.25})
    assert prof.detect_conflict(**kw, idea={"ticker": "SPY", "weight": 0.5}) == []
    assert "exclu" in prof.detect_conflict(**kw, idea={"ticker": "BTC-USD", "weight": 0.02})[0]
    short = dict(tolerance="high", horizon_years=3, constraints=[])
    assert prof.detect_conflict(**short, idea={"ticker": "ETH-USD", "weight": 0.05})


def test_ticker_resolution():
    assert prof._resolve_ticker("tsla") == "TSLA"
    assert prof._resolve_ticker("XIU") == "XIU.TO"
    assert prof._resolve_ticker("nope") is None


def test_needs_clarification_variants():
    e = prof.Extraction
    assert prof.needs_clarification("", e())
    assert prof.needs_clarification("TSLA", e(request_type="judge", ticker="TSLA"))
    assert prof.needs_clarification("x", e(ticker="TSLA", weight_pct=5)) is None
    assert prof.needs_clarification("x", e()) is None


def test_one_question_then_profile_through_graph(use_llm):
    fake = use_llm(ROBERT)
    tid = uuid.uuid4().hex
    events = list(stream_run(initial_state("robert", "Je pense à Tesla."), tid))
    assert events[-1]["type"] == "interrupt" and "TSLA" in events[-1]["question"]
    assert fake.calls == 0  # the model is only called once the question is answered
    events = list(resume_run("25 %", tid))
    assert events[-1]["type"] == "final"
    final = events[-1]["state"]
    assert final.profile.requested_idea == {"ticker": "TSLA", "weight": 0.25}
    assert final.retries["clarify"] == 1
    assert "25 %" in final.request_text


def test_at_most_one_question(use_llm):
    use_llm({"request_type": "judge", "ticker": "TSLA"})  # weight never provided
    tid = uuid.uuid4().hex
    list(stream_run(initial_state("robert", "Tesla"), tid))
    events = list(resume_run("je ne sais pas", tid))
    assert events[-1]["type"] == "final"
    assert events[-1]["state"].profile.requested_idea is None


@pytest.mark.live
def test_live_robert_tsla():
    p = _run("robert", PERSONAS["robert"]["example_request"])
    assert p.request_type == "judge" and p.requested_idea["ticker"] == "TSLA"
    assert p.requested_idea["weight"] == pytest.approx(0.25)
    assert p.conflicts
