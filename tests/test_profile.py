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


def test_tolerance_far_above_capacity_is_a_conflict():
    from alphaforge.nodes.profile import detect_conflict

    out = detect_conflict(tolerance="high", horizon_years=10, constraints=[], idea=None, capacity="low")
    assert any("capacité" in c for c in out)
    assert not detect_conflict(tolerance="low_moderate", horizon_years=4, constraints=[], idea=None,
                               capacity="low")


# ---- B-13 KYC completeness and multi-turn clarification tests (#117)
def test_kyc_completeness_model_canonical_personas():
    p = _run("amira", PERSONAS["amira"]["example_request"])
    assert p.kyc_completeness is not None
    assert p.kyc_completeness.is_complete is True
    assert p.kyc_completeness.score == 1.0
    assert "has_emergency_fund" in p.kyc_completeness.required_fields
    assert p.kyc_completeness.fields["has_emergency_fund"].source == "persona"
    assert p.kyc_completeness.fields["has_emergency_fund"].collected is True
    assert p.has_emergency_fund is True
    assert p.has_high_interest_debt is False
    assert p.net_worth_share == 0.20


def test_kyc_completeness_model_questionnaire_source():
    persona_data = {
        "objective": "growth",
        "horizon_years": 10,
        "risk_tolerance": "moderate",
        "risk_capacity": "moderate",
        "has_emergency_fund": True,
        "has_high_interest_debt": False,
        "net_worth_share": 0.30,
        "investment_knowledge": "intermediate",
        "current_holdings": ["pension"],
    }
    state = GraphState(
        as_of_date=dt.date(2026, 11, 12),
        persona="custom",
        persona_data=persona_data,
        request_text="Construire une allocation diversifiée",
    )
    res = profile_node(state)
    p = res["profile"]
    assert p.kyc_completeness is not None
    assert p.kyc_completeness.fields["has_emergency_fund"].source == "questionnaire"
    assert p.kyc_completeness.fields["has_emergency_fund"].collected is True
    assert p.net_worth_share == 0.30


def test_clarification_loop_multi_turn_ranked_by_impact_on_caps():
    # A custom profile with missing goal, missing emergency fund, and missing debt
    tid = uuid.uuid4().hex
    inputs = initial_state(
        persona="custom",
        request_text="Je veux investir",
        persona_data={
            "objective": "balanced",
            "horizon_years": 8,
            "risk_tolerance": "moderate",
            "risk_capacity": "moderate",
        },
    )
    # Turn 1: should ask goal first (impact on entire allocation / caps)
    events_1 = list(stream_run(inputs, tid))
    q1 = [e for e in events_1 if e["type"] == "interrupt"]
    assert len(q1) == 1
    assert "construire" in q1[0]["question"].lower() or "allocation" in q1[0]["question"].lower()

    # Turn 2: answer goal, next should ask emergency fund (hard gate on liquidity & capacity)
    events_2 = list(resume_run("Construire une allocation diversifiée", tid))
    q2 = [e for e in events_2 if e["type"] == "interrupt"]
    assert len(q2) == 1
    assert "fonds d'urgence" in q2[0]["question"].lower()

    # Turn 3: answer emergency fund, next should ask high-interest debt (hard gate)
    events_3 = list(resume_run("Oui, j'ai 6 mois d'épargne d'urgence", tid))
    q3 = [e for e in events_3 if e["type"] == "interrupt"]
    assert len(q3) == 1
    assert "dettes" in q3[0]["question"].lower()

    # Turn 4: answer debt, loop reached 3 questions limit, finishes
    events_4 = list(resume_run("Non, aucune dette", tid))
    assert events_4[-1]["type"] == "final"
    final = events_4[-1]["state"]
    assert final.profile is not None
    assert final.retries.get("clarify") == 3
    assert final.profile.has_emergency_fund is True
    assert final.profile.has_high_interest_debt is False


def test_unanswered_kyc_fields_become_assumptions_with_evidence_ids():
    tid = uuid.uuid4().hex
    inputs = initial_state(
        persona="custom",
        request_text="Allocation diversifiée",
        persona_data={
            "objective": "balanced",
            "horizon_years": 8,
            "risk_tolerance": "moderate",
            "risk_capacity": "moderate",
        },
    )
    events_1 = list(stream_run(inputs, tid))
    assert events_1[0]["type"] == "interrupt"
    assert "fonds d'urgence" in events_1[0]["question"].lower()

    # User says "je ne sais pas"
    events_2 = list(resume_run("je ne sais pas", tid))
    assert events_2[0]["type"] == "interrupt"
    assert "dettes" in events_2[0]["question"].lower()

    # User skips debt
    events_3 = list(resume_run("passer", tid))
    assert events_3[0]["type"] == "interrupt"
    assert "patrimoine" in events_3[0]["question"].lower()

    # User answers net worth share -> 3 questions answered!
    events_4 = list(resume_run("20 %", tid))
    assert events_4[-1]["type"] == "final"
    final = events_4[-1]["state"]
    p = final.profile
    assert p.kyc_completeness is not None
    assert any(k.startswith("EK") for k in final.evidence)
    ef_field = p.kyc_completeness.fields["has_emergency_fund"]
    assert ef_field.source == "assumption"
    assert ef_field.evidence_id is not None
    assert ef_field.evidence_id.startswith("EK")
    assert final.evidence[ef_field.evidence_id].confidence == "assumption"


def test_hard_gates_no_emergency_fund_note():
    persona_data = {
        "objective": "growth",
        "horizon_years": 10,
        "risk_tolerance": "high",
        "risk_capacity": "high",
        "has_emergency_fund": False,
        "has_high_interest_debt": False,
        "net_worth_share": 0.20,
        "investment_knowledge": "advanced",
    }
    state = GraphState(
        as_of_date=dt.date(2026, 11, 12),
        persona="custom",
        persona_data=persona_data,
        request_text="Construire une allocation diversifiée",
    )
    res = profile_node(state)
    p = res["profile"]
    assert p.has_emergency_fund is False
    assert len(p.hard_gate_notes) >= 1
    assert any("fonds d'urgence" in note.lower() for note in p.hard_gate_notes)
    assert any("fonds d'urgence" in c.lower() for c in p.conflicts)


def test_hard_gates_high_interest_debt_note():
    persona_data = {
        "objective": "balanced",
        "horizon_years": 5,
        "risk_tolerance": "moderate",
        "risk_capacity": "moderate",
        "has_emergency_fund": True,
        "has_high_interest_debt": True,
        "net_worth_share": 0.20,
        "investment_knowledge": "intermediate",
    }
    state = GraphState(
        as_of_date=dt.date(2026, 11, 12),
        persona="custom",
        persona_data=persona_data,
        request_text="Construire une allocation",
    )
    res = profile_node(state)
    p = res["profile"]
    assert p.has_high_interest_debt is True
    assert len(p.hard_gate_notes) >= 1
    assert any("dettes" in note.lower() for note in p.hard_gate_notes)
    assert any("dettes" in c.lower() for c in p.conflicts)


def test_judge_exact_profile_replay():
    """Verify the judge's exact profile behaviour (findings 1-4, 7)."""
    from alphaforge.guardrails import check_guardrails
    from alphaforge.state import Scenario

    persona_data = {
        "label": "Profil du juge",
        "objective": "growth",
        "horizon_years": 25,
        "risk_tolerance": "high",
        "risk_capacity": "high",
        "account_type": "tfsa",
        "budget_cad": 100_000.0,
        "max_loss_pct": 25,
        "crypto_preference": "15 % et plus",
        "sector_cap_pct": 40,
        "currency_preference": "mixte (CAD / USD)",
        "age_band": "18-29",
        "preferences": ["esg_tilt", "likes_energy"],
        "current_holdings": {"BTC-USD": 0.30, "SOL": 0.40},
        "has_emergency_fund": True,
        "has_high_interest_debt": False,
        "investment_knowledge": "intermediate",
        "net_worth_share": 0.20,
    }
    state = GraphState(
        as_of_date=dt.date(2026, 11, 15),
        persona="custom",
        persona_data=persona_data,
        request_text="Je veux évaluer mon allocation et garder 50 % en crypto.",
    )
    res = profile_node(state)
    p = res["profile"]

    # 1. Profile fields match questionnaire
    assert p.account_type == "tfsa"
    assert p.budget_cad == 100_000.0
    assert p.risk_tolerance == "high"
    assert p.risk_capacity == "high"
    assert p.age_band == "18-29"
    assert p.max_loss_12m == pytest.approx(0.25)
    assert p.crypto_target_min == pytest.approx(0.15)
    assert p.sector_cap == pytest.approx(0.40)
    assert p.currency_pref == "mixed"

    # 2. Holdings: unanalysed SOL 40% kept, BTC 30%, cash 30%, never rescaled
    assert p.holdings_unanalysed == {"SOL": 0.40}
    assert p.not_analysed_holdings == ["SOL"]
    assert p.current_holdings["BTC-USD"] == pytest.approx(0.30)
    assert p.holdings_cash == pytest.approx(0.30)

    # 3. TFSA room exceeded (78k vs 100k) flagged in conflicts
    assert any("78 000 $" in c and "100 000 $" in c for c in p.conflicts)
    room_ev = next(e for e in res["evidence"].values() if e.value.get("metric") == "tfsa_room")
    assert room_ev.value["room_cad"] == 78000.0
    assert room_ev.value["excess_cad"] == 22000.0

    # 4. Guardrails check
    sc = Scenario(
        name="capped",
        weights={"AAPL": 0.30, "MSFT": 0.20, "BTC-USD": 0.05, "XIU.TO": 0.45},
        metrics={"stress_2022": "EQ1", "max_drawdown": "EQ2", "top_weight": "EQ3"},
    )
    from alphaforge.state import Evidence
    ev_map = {
        **res["evidence"],
        "EQ1": Evidence(
            id="EQ1", value={"metric": "stress_2022", "value": -0.26},
            source="test", date=dt.date(2026, 11, 15), method="test",
        ),
        "EQ2": Evidence(
            id="EQ2", value={"metric": "max_drawdown", "value": -0.315},
            source="test", date=dt.date(2026, 11, 15), method="test",
        ),
        "EQ3": Evidence(
            id="EQ3", value={"metric": "top_weight", "value": 0.30},
            source="test", date=dt.date(2026, 11, 15), method="test",
        ),
    }
    gr = check_guardrails(p, [sc], ev_map)
    limits_status = {g["limit"]: g["status"] for g in gr}

    # TFSA room is a breach
    assert limits_status["tfsa_room"] == "breach"
    # Max loss 25% vs 26% stress and 31.5% drawdown is a breach
    loss_entries = [g for g in gr if g["limit"] == "max_loss_12m"]
    assert all(g["status"] == "breach" for g in loss_entries)
    # Crypto target min 15% vs 5% observed is a breach
    assert limits_status["crypto_target_min"] == "breach"
    # Spot crypto in TFSA is a breach
    assert limits_status["account_eligibility"] == "breach"


def test_question_vehicle_and_allocation_extraction():
    """Finding 1 & 5: vehicle outside universe and allocation parsing."""
    from alphaforge.nodes.profile import _regex_extract

    ext = _regex_extract("15 % Bitcoin via BTCC.B")
    assert ext.requested_vehicle == "BTCC.B"
    assert ext.requested_allocation == {"BTC-USD": 0.15}

    ext2 = _regex_extract("Garder 50 % en crypto")
    assert ext2.requested_allocation == {"crypto": 0.50}


def test_crypto_etf_holding_is_eligible_in_guardrails():
    """#186 item 2: crypto held through BTCC.B.TO is analysed via BTC-USD but is eligible."""
    from alphaforge.guardrails import check_guardrails
    from alphaforge.state import Profile, Scenario

    sc = Scenario(name="current", weights={"BTC-USD": 0.30, "XIU.TO": 0.70}, metrics={})
    base = dict(persona="amira", objective="growth", horizon_years=10, risk_tolerance="high",
                risk_capacity="high", account_type="tfsa")
    via_etf = Profile(**base, current_holdings={"BTCC.B.TO": 0.30, "XIU.TO": 0.70})
    entry = next(g for g in check_guardrails(via_etf, [sc], {}) if g["limit"] == "account_eligibility")
    assert entry["status"] == "ok" and entry["observed"] == 0.0
    assert entry["via_etf"] == {"BTC-USD": ["BTCC.B.TO"]}
    assert "FNB coté" in entry["message_fr"] and "sous-jacent" in entry["message_fr"]
    assert "listed ETF" in entry["message_en"]

    spot = Profile(**base, current_holdings={"BTC-USD": 0.30, "XIU.TO": 0.70})
    entry = next(g for g in check_guardrails(spot, [sc], {}) if g["limit"] == "account_eligibility")
    assert entry["status"] == "breach" and entry["tickers"] == ["BTC-USD"]

    asked = Profile(**base, requested_vehicle="BTCC.B", requested_idea={"ticker": "BTC-USD", "weight": 0.3})
    entry = next(g for g in check_guardrails(asked, [sc], {}) if g["limit"] == "account_eligibility")
    assert entry["status"] == "ok"


def test_tfsa_balance_inferred_from_holdings_is_not_compared_with_room():
    """#186 item 3: a balance can exceed cumulative room through growth; only a stated
    contribution is compared."""
    from alphaforge.guardrails import check_guardrails

    persona_data = {
        "objective": "growth", "horizon_years": 25, "risk_tolerance": "high",
        "risk_capacity": "high", "account_type": "tfsa", "age_band": "18-29",
        "current_holdings": {"XIU.TO": 90_000, "AAPL": 30_000},
    }
    state = GraphState(
        as_of_date=dt.date(2026, 11, 15), persona="custom", persona_data=persona_data,
        request_text="Je veux évaluer mon allocation.",
    )
    res = profile_node(state)
    p = res["profile"]
    assert p.budget_cad == pytest.approx(120_000.0) and p.budget_inferred is True
    assert not any("droits de cotisation" in c for c in p.conflicts)
    assert not any(isinstance(e.value, dict) and e.value.get("metric") == "tfsa_room" for e in res["evidence"].values())
    assert not any(g["limit"] == "tfsa_room" for g in check_guardrails(p, [], res["evidence"]))

    stated = GraphState(
        as_of_date=dt.date(2026, 11, 15), persona="custom",
        persona_data={**persona_data, "budget_cad": 120_000.0},
        request_text="Je veux évaluer mon allocation.",
    )
    res2 = profile_node(stated)
    p2 = res2["profile"]
    assert p2.budget_inferred is False
    assert any("78 000 $" in c and "120 000 $" in c for c in p2.conflicts)
    assert any(isinstance(e.value, dict) and e.value.get("metric") == "tfsa_room" for e in res2["evidence"].values())
    assert any(g["limit"] == "tfsa_room" and g["status"] == "breach" for g in check_guardrails(p2, [], res2["evidence"]))


@pytest.mark.parametrize(
    "text, expected",
    [
        ("je détiens 2 cryptos", None),
        ("j'ai 3 cryptos dans mon portefeuille", None),
        ("garder 50 % en crypto", {"crypto": 0.5}),
        ("20 % crypto", {"crypto": 0.2}),
        ("15 pour cent de crypto", {"crypto": 0.15}),
        ("mettre 10 en crypto", {"crypto": 0.1}),
    ],
)
def test_crypto_target_needs_a_weight_context(text, expected):
    """#186 item 10: a count of cryptos is not a crypto weight."""
    assert prof._regex_extract(text).requested_allocation == expected


def test_model_extraction_is_completed_by_the_deterministic_reading(monkeypatch):
    """Live bug: the model returned no allocation for '50 % en crypto', so 'as requested' ignored it."""
    from alphaforge import llm
    from alphaforge.nodes import profile as prof

    def fake_call_json(prompt, schema, **kw):
        return schema(request_type="build")  # the model extracted nothing

    monkeypatch.setattr(llm, "call_json", fake_call_json)
    res, used_fallback = prof.extract_profile("amira", "Je veux garder 50 % en crypto.")
    assert used_fallback is False
    assert res.requested_allocation == {"crypto": 0.5}

    res, _ = prof.extract_profile("amira", "Je veux mettre 15 % en Bitcoin via le FNB BTCC.B.")
    assert res.ticker == "BTC-USD" and res.requested_allocation == {"BTC-USD": 0.15}
    assert res.requested_vehicle == "BTCC.B" and res.request_type == "judge"

    res, _ = prof.extract_profile("amira", "Je veux un portfolio complet pour la retraite.")
    assert res.requested_allocation is None and res.ticker is None
