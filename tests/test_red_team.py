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
