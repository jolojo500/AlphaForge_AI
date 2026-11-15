import json
from pathlib import Path

import pytest

from alphaforge import llm
from alphaforge.graph import run
from alphaforge.nodes import explain as ex
from alphaforge.personas import PERSONAS
from alphaforge.state import SCENARIO_NAMES


class FakeMsg:
    def __init__(self, content):
        self.content = content


class FakeLLM:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def invoke(self, messages):
        self.prompts.append(messages[-1][1] if messages[-1][0] == "human" else "")
        r = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return FakeMsg(r if isinstance(r, str) else json.dumps(r))


@pytest.fixture
def state():
    return run("robert", PERSONAS["robert"]["example_request"])


def good(state):
    e = ex.template_explanation(state)
    e["limites"] = [{"claim": "Le passé ne prédit pas l'avenir.", "evidence": []}]
    return e


def test_schema_validates_and_disclaimer_is_forced(state):
    reply = good(state) | {"avertissement": "autre texte"}
    out, template = ex.generate_explanation(state, FakeLLM(reply))
    assert template is False
    assert out["avertissement"] == ex.DISCLAIMER
    assert set(out) == {
        "resume", "quelles_donnees", "pourquoi_ce_choix", "limites",
        "ce_qui_changerait_la_reponse", "incertitude", "scenario_le_plus_coherent", "avertissement",
    }
    assert out["scenario_le_plus_coherent"] in SCENARIO_NAMES


def test_malformed_reply_is_repaired(state):
    fake = FakeLLM("pas du json", good(state))
    out, template = ex.generate_explanation(state, fake)
    assert template is False and len(fake.prompts) == 2 and out["resume"]


def test_unusable_reply_falls_back_to_template(state):
    out, template = ex.generate_explanation(state, FakeLLM("nope"))
    assert template is True
    assert any("gabarit" in c["claim"] for c in out["limites"])
    assert all(e in state.evidence for sec in ("quelles_donnees", "pourquoi_ce_choix")
               for c in out[sec] for e in c["evidence"])


def test_invalid_scenario_name_is_rejected_then_template(state):
    bad = good(state) | {"scenario_le_plus_coherent": "best"}
    _, template = ex.generate_explanation(state, FakeLLM(bad))
    assert template is True


def test_prompt_has_evidence_ids_scenarios_and_no_retry_block(state):
    prompt = ex.build_prompt(state)
    for sc in state.scenarios:
        assert sc.name in prompt
        for eid in sc.metrics.values():
            assert eid in prompt
    assert "rejetée" not in prompt


def test_retry_prompt_includes_verifier_errors(state):
    retry = state.model_copy(
        update={
            "retries": {**state.retries, "explain": 1},
            "verification": {"passed": False, "errors": ["limites: preuve inconnue EQ99"]},
        }
    )
    prompt = ex.build_prompt(retry)
    assert "rejetée" in prompt and "EQ99" in prompt


def test_template_is_consistent_with_evidence(state):
    e = ex.template_explanation(state)
    assert e["scenario_le_plus_coherent"] in SCENARIO_NAMES
    assert e["avertissement"] == ex.DISCLAIMER
    for sec in ("quelles_donnees", "pourquoi_ce_choix", "limites", "ce_qui_changerait_la_reponse"):
        assert e[sec]


def test_node_offline_uses_template_and_traces(state):
    out = ex.explain_node(state)
    assert out["explanation"]["scenario_le_plus_coherent"] in SCENARIO_NAMES
    assert out["trace"][0]["node"] == "explain" and "gabarit" in out["trace"][0]["summary"]


def test_describe_evidence_line(state):
    line = ex.describe_evidence(state.evidence[state.scenarios[0].metrics["max_drawdown"]])
    assert line.startswith("EP") and "max_drawdown" in line and "fictional" in line


FIXTURES = Path(__file__).parent / "fixtures" / "llm"


def fx(name):
    return (FIXTURES / f"explain_{name}.json").read_text(encoding="utf-8")


class ExplainOnly:
    """Override answering only the explanation schema; other LLM nodes get invalid JSON."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def __call__(self, messages, kind):
        if "scenario_le_plus_coherent" not in messages[0][1]:
            return "not json"
        self.prompts.append(messages[1][1])
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


def test_fixture_reply_passes_the_verifier():
    fake = ExplainOnly(fx("robert"))
    llm.set_llm_override(fake)
    s = run("robert", PERSONAS["robert"]["example_request"])
    assert s.verification == {"passed": True, "errors": []}
    assert s.explanation["scenario_le_plus_coherent"] == "capped"
    assert [t["node"] for t in s.trace].count("explain") == 1


def test_unknown_id_is_caught_and_regenerated_once():
    fake = ExplainOnly(fx("unknown_id"), fx("robert"))
    llm.set_llm_override(fake)
    s = run("robert", PERSONAS["robert"]["example_request"])
    assert [t["node"] for t in s.trace].count("explain") == 2
    assert len(fake.prompts) == 2
    assert "EP999" not in fake.prompts[0] and "EP999" in fake.prompts[1]  # errors fed back
    assert s.verification["passed"] is True and s.retries["explain"] == 1


def test_two_failures_end_with_visible_failure():
    llm.set_llm_override(ExplainOnly(fx("unknown_id")))
    s = run("robert", PERSONAS["robert"]["example_request"])
    assert [t["node"] for t in s.trace].count("explain") == 2
    assert s.verification["passed"] is False
    assert any("EP999" in e for e in s.verification["errors"])


def test_printable_formats_match_the_verifier(state):
    from alphaforge.nodes.verifier import check_numbers

    for sc in state.scenarios:
        for eid in sc.metrics.values():
            text = ex.printable(state.evidence[eid])
            claim = {"quelles_donnees": [{"claim": f"Valeur : {text}.", "evidence": [eid]}]}
            assert check_numbers(claim, state.evidence) == [], (eid, text)


@pytest.mark.live
def test_live_robert_explanation():
    s = run("robert", PERSONAS["robert"]["example_request"])
    assert s.verification["passed"] is True
    assert [t["node"] for t in s.trace].count("explain") <= 2
    assert s.explanation["avertissement"] == ex.DISCLAIMER
    assert s.explanation["scenario_le_plus_coherent"] in SCENARIO_NAMES
    assert s.explanation["quelles_donnees"] and s.explanation["pourquoi_ce_choix"]
