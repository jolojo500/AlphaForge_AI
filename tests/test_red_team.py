import json

import pytest

from alphaforge import llm
from alphaforge.graph import run
from alphaforge.nodes import red_team as rt
from alphaforge.personas import PERSONAS


class FakeLLM:
    def __init__(self, *payloads):
        self.payloads = list(payloads)

    def invoke(self, messages):
        p = self.payloads.pop(0) if len(self.payloads) > 1 else self.payloads[0]
        return type("M", (), {"content": json.dumps(p)})()


@pytest.fixture
def use_llm():
    """Answer only the red-team schema; the other LLM nodes get invalid JSON and fall back."""

    def _use(*payloads):
        fake = FakeLLM(*payloads)

        def route(messages, kind):
            if '"severity"' not in messages[0][1]:
                return "not json"
            return fake.invoke(messages).content

        llm.set_llm_override(route)

    return _use


def obj(severity="blocking", evidence=("EP1",), scenario="capped"):
    return {"scenario": scenario, "objection": "Concentration américaine élevée.",
            "evidence": list(evidence), "severity": severity}


def test_offline_is_a_pass_through_with_counter():
    s = run("robert", PERSONAS["robert"]["example_request"])
    assert s.objections == [] and s.retries["red_team"] == 1


def test_objections_must_cite_existing_evidence(use_llm):
    use_llm({"objections": [obj(evidence=["EP999"]), obj("warning", ["EP1"])]})
    s = run("amira", PERSONAS["amira"]["example_request"])
    assert [o["evidence"] for o in s.objections] == [["EP1"]]


def test_blocking_loops_back_then_is_downgraded(use_llm):
    use_llm({"objections": [obj("blocking")]})
    s = run("amira", PERSONAS["amira"]["example_request"])
    # first pass blocks and sends the run back once; the second pass is downgraded to a warning
    assert s.retries["red_team"] == 2
    assert [o["severity"] for o in s.objections] == ["warning"]
    assert [t["node"] for t in s.trace].count("scenarios") == 2


def test_warning_does_not_loop(use_llm):
    use_llm({"objections": [obj("warning")]})
    s = run("amira", PERSONAS["amira"]["example_request"])
    assert s.retries["red_team"] == 1 and len(s.objections) == 1


def test_objection_count_is_capped(use_llm):
    use_llm({"objections": [obj("warning") for _ in range(9)]})
    s = run("amira", PERSONAS["amira"]["example_request"])
    assert len(s.objections) == rt.MAX_OBJECTIONS


def test_model_failure_does_not_block_the_run(use_llm):
    use_llm("not json")
    s = run("amira", PERSONAS["amira"]["example_request"])
    assert s.objections == [] and s.verification["passed"] is True


@pytest.mark.live
@pytest.mark.parametrize("persona", sorted(PERSONAS))
def test_live_red_team(persona):
    s = run(persona, PERSONAS[persona]["example_request"])
    assert all(o["evidence"] and o["evidence"][0] in s.evidence for o in s.objections)
    assert s.retries["red_team"] <= 3


def test_default_second_pass_makes_no_model_call(use_llm):
    calls = []
    use_llm({"objections": [obj("blocking")]})
    route = llm._override

    def counting(messages, kind):
        if '"severity"' in messages[0][1]:
            calls.append(kind)
        return route(messages, kind)

    llm.set_llm_override(counting)
    s = run("amira", PERSONAS["amira"]["example_request"])
    assert s.retries["red_team"] == 2
    assert len(calls) == 1  # default AF_RED_TEAM_RECHECK=off: no model call on second pass


def test_second_pass_blocking_twice_escalates_to_opus_tie_break(use_llm, monkeypatch):
    monkeypatch.setattr(rt.config, "RED_TEAM_RECHECK", True)
    calls = []
    use_llm({"objections": [obj("blocking")]})
    route = llm._override

    def counting(messages, kind):
        if '"severity"' in messages[0][1]:
            calls.append(kind)
        return route(messages, kind)

    llm.set_llm_override(counting)
    s = run("amira", PERSONAS["amira"]["example_request"])
    assert s.retries["red_team"] == 2
    assert calls == ["main", "main", "review"]
    assert all(o["severity"] == "warning" for o in s.objections)


def test_second_pass_non_blocking_does_not_call_opus(use_llm, monkeypatch):
    monkeypatch.setattr(rt.config, "RED_TEAM_RECHECK", True)
    calls = []
    use_llm(
        {"objections": [obj("blocking")]},
        {"objections": [obj("warning")]},
    )
    route = llm._override

    def counting(messages, kind):
        if '"severity"' in messages[0][1]:
            calls.append(kind)
        return route(messages, kind)

    llm.set_llm_override(counting)
    s = run("amira", PERSONAS["amira"]["example_request"])
    assert s.retries["red_team"] == 2
    assert calls == ["main", "main"]


@pytest.mark.live
def test_live_red_team_opus_tie_break():
    state = run("robert", PERSONAS["robert"]["example_request"])
    review = llm.call_json(rt._prompt(state), rt.Review, kind="review", system=rt.SYSTEM)
    objections = rt.clean_objections(review, state, first_pass=False)
    assert all(o["severity"] == "warning" for o in objections)


def test_objection_with_invented_number_is_dropped(use_llm):
    bad = obj("warning") | {"objection": "Perte maximale de -99,9 % sur ce scénario."}
    use_llm({"objections": [bad, obj("warning")]})
    s = run("amira", PERSONAS["amira"]["example_request"])
    assert [o["objection"] for o in s.objections] == ["Concentration américaine élevée."]


def test_objection_with_advice_wording_is_dropped_with_a_log_line(use_llm, caplog):
    """#186 item 5: a forbidden word in an objection must not reach the verifier."""
    import logging

    bad = obj("blocking") | {"objection": "Nous recommandons de vendre TSLA."}
    use_llm({"objections": [bad, obj("warning")]})
    with caplog.at_level(logging.WARNING, logger="alphaforge.nodes.red_team"):
        s = run("amira", PERSONAS["amira"]["example_request"])
    assert [o["objection"] for o in s.objections] == ["Concentration américaine élevée."]
    assert s.retries["red_team"] == 1  # the dropped objection was blocking: no loop
    assert s.verification["passed"] is True
    assert any("objection dropped" in r.message and "vendre TSLA" in r.message for r in caplog.records)


def test_objection_with_internal_term_is_reworded_not_dropped(use_llm):
    """#186 item 5: a plain-term substitution comes first; the objection is kept."""
    from alphaforge.nodes.verifier import check_text_wording

    bad = obj("warning") | {"objection": "Concentration élevée dans capped sur un seul marché."}
    use_llm({"objections": [bad]})
    s = run("amira", PERSONAS["amira"]["example_request"])
    assert len(s.objections) == 1
    text = s.objections[0]["objection"]
    assert "capped" not in text and "la version ajustée à vos limites" in text
    assert check_text_wording([("objection", text)]) == []
    assert s.verification["passed"] is True


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Concentration élevée (EP1).", "Concentration élevée (EP1)."),
        ("Le scénario profile_baseline est concentré.", "Le scénario le profil de référence est concentré."),
        ("Nous recommandons de vendre TSLA.", None),
        ("Vous devriez vendre TSLA.", None),
    ],
)
def test_reword_objection(text, expected):
    assert rt.reword_objection(text, "fr") == expected
