import json

import pytest

from alphaforge.graph import run
from alphaforge.notes import MAX_NOTES, draft_notes, template_notes
from alphaforge.personas import PERSONAS


class FakeLLM:
    def __init__(self, notes):
        self.notes = notes

    def invoke(self, messages):
        return type("M", (), {"content": json.dumps({"notes": self.notes})})()


@pytest.fixture
def stub():
    s = run("robert", PERSONAS["robert"]["example_request"])
    return next(sc for sc in s.scenarios if sc.name == "as_requested"), s.evidence, s.profile


def test_valid_model_notes_are_kept(stub):
    sc, ev, p = stub
    mdd = sc.metrics["max_drawdown"]
    notes = [f"La perte maximale historique est la plus marquée du comparatif [{mdd}]."]
    assert draft_notes(sc, ev, p, llm_client=FakeLLM(notes)) == notes


def test_notes_are_capped(stub):
    sc, ev, p = stub
    eid = sc.metrics["volatility_ann"]
    many = [f"Observation historique sur le risque [{eid}]." for _ in range(7)]
    assert len(draft_notes(sc, ev, p, llm_client=FakeLLM(many))) == MAX_NOTES


@pytest.mark.parametrize(
    "bad",
    [
        ["Sans aucune citation."],
        ["Preuve inventée [EP999]."],
        ["La volatilité est de 31 % [EP1]."],  # the model must not write numbers
    ],
)
def test_invalid_notes_fall_back_to_template(stub, bad):
    sc, ev, p = stub
    assert draft_notes(sc, ev, p, llm_client=FakeLLM(bad)) == template_notes(sc, ev)


def test_advice_wording_falls_back_to_template(stub):
    verifier = pytest.importorskip("alphaforge.nodes.verifier")
    if not hasattr(verifier, "check_wording"):
        pytest.skip("needs the B-3 verifier")
    sc, ev, p = stub
    bad = ["Vous devriez acheter ce scénario [EP1]."]
    assert draft_notes(sc, ev, p, llm_client=FakeLLM(bad)) == template_notes(sc, ev)


def test_template_cites_every_metric_with_its_value(stub):
    sc, ev, _ = stub
    notes = template_notes(sc, ev)
    for metric in ("volatility_ann", "max_drawdown"):
        assert any(f"[{sc.metrics[metric]}]" in n for n in notes)
    assert "31.0%" in " ".join(notes)
    assert notes[-1].startswith("Scénario fictif")


def test_offline_model_gives_template(stub):
    sc, ev, p = stub
    assert draft_notes(sc, ev, p) == template_notes(sc, ev)


@pytest.mark.live
def test_live_notes_cite_evidence(stub):
    sc, ev, p = stub
    notes = draft_notes(sc, ev, p)
    assert 1 <= len(notes) <= MAX_NOTES and all("[EP" in n for n in notes)
