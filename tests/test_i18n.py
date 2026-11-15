"""Tests for language detection and i18n support (#123)."""
import datetime as dt

from alphaforge.i18n import detect_language
from alphaforge.nodes.explain import template_explanation
from alphaforge.nodes.profile import (
    Extraction,
    _regex_extract,
    detect_conflict,
    needs_clarification,
)
from alphaforge.nodes.scenarios import _template_notes
from alphaforge.state import Evidence, GraphState, Profile, Scenario


def test_detect_language_french():
    assert detect_language("Je voudrais investir dans les actions tech avec un horizon de 5 ans.") == "fr"
    assert detect_language("Bonjour, quel est le portefeuille recommandé ?") == "fr"
    assert detect_language("Allocation d'actifs équilibrée avec FNB et obligations.") == "fr"


def test_detect_language_english():
    assert detect_language("I want to invest 25% of my portfolio in TSLA with a 10 year horizon.") == "en"
    assert detect_language("Hello, please evaluate my retirement portfolio and growth strategy.") == "en"
    assert detect_language("Build an allocation with balanced ETFs and conservative bonds.") == "en"


def test_detect_language_empty_and_default():
    assert detect_language("") == "fr"
    assert detect_language("   ") == "fr"
    assert detect_language("", default="en") == "en"


def test_detect_conflict_english():
    conflicts_crypto = detect_conflict(
        tolerance="low",
        horizon_years=3,
        constraints=["no_crypto"],
        idea={"ticker": "BTC-USD", "weight": 0.25},
        capacity="low",
        language="en",
    )
    assert any("crypto" in c.lower() for c in conflicts_crypto)

    conflicts_equity = detect_conflict(
        tolerance="low",
        horizon_years=3,
        constraints=[],
        idea={"ticker": "TSLA", "weight": 0.25},
        capacity="low",
        language="en",
    )
    assert any("ceiling" in c.lower() or "exceeds" in c.lower() for c in conflicts_equity)


def test_needs_clarification_english():
    ext_no_weight = Extraction(request_type="judge", ticker="TSLA", weight_pct=None)
    q = needs_clarification("I want TSLA", ext_no_weight, language="en")
    assert "What share of your portfolio" in q
    assert "TSLA" in q

    ext_empty = Extraction(request_type="build")
    q_goal = needs_clarification("", ext_empty, language="en")
    assert "What would you like to do" in q_goal


def test_template_notes_english():
    weights = {"XIU.TO": 0.5, "ZST.TO": 0.5}
    values = {"volatility_ann": 0.08, "max_drawdown": -0.05}
    ids = {"volatility_ann": "EP1", "max_drawdown": "EP2"}
    notes_en = _template_notes("as_requested", weights, values, ids, "EP0", None, False, language="en")
    assert any("Annualized volatility" in n for n in notes_en)
    assert any("historical maximum loss" in n for n in notes_en)


def test_template_explanation_english():
    sc1 = Scenario(
        name="profile_baseline",
        weights={"XIU.TO": 1.0},
        metrics={"volatility_ann": "EP1", "max_drawdown": "EP2"},
    )
    profile = Profile(
        persona="robert",
        objective="capital_preservation",
        horizon_years=5,
        risk_tolerance="low",
        risk_capacity="low",
        language="en",
    )
    ev1 = Evidence(id="EP1", value={"metric": "volatility_ann", "value": 0.08, "unit": "%"}, source="test", date=dt.date(2026, 11, 15), method="test")
    ev2 = Evidence(id="EP2", value={"metric": "max_drawdown", "value": -0.05, "unit": "%"}, source="test", date=dt.date(2026, 11, 15), method="test")
    state = GraphState(
        as_of_date=dt.date(2026, 11, 15),
        persona="robert",
        profile=profile,
        scenarios=[sc1],
        evidence={"EP1": ev1, "EP2": ev2},
        language="en",
    )
    exp = template_explanation(state)
    assert "reference profile" in exp["resume"]
    assert "Educational simulation. No personalized advice." == exp["avertissement"]
    assert "Historical statistics do not describe the future." == exp["incertitude"]


def test_demo_personas_no_clarification_both_languages():
    from alphaforge.personas import PERSONAS

    for persona_id, p in PERSONAS.items():
        req_fr = p.get("example_request", "")
        if req_fr:
            q_fr = needs_clarification(req_fr, _regex_extract(req_fr), language="fr")
            assert q_fr is None, f"Persona {persona_id} asked question in French: {q_fr}"

    en_requests = {
        "amira": "I want to invest $100,000 with a focus on tech and crypto for a 15-year horizon.",
        "mateo": "I want to build a balanced ESG portfolio with a 10-year horizon.",
        "robert": "I want to preserve my capital with a 4-year horizon before retirement.",
    }
    for persona_id, req_en in en_requests.items():
        q_en = needs_clarification(req_en, _regex_extract(req_en), language="en")
        assert q_en is None, f"Persona {persona_id} asked question in English: {q_en}"

