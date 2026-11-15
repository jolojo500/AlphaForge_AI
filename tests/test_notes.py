import json

import pytest

from alphaforge import llm
from alphaforge.graph import run
from alphaforge.nodes.notes import draft_notes
from alphaforge.personas import PERSONAS


@pytest.fixture
def base():
    s = run("robert", PERSONAS["robert"]["example_request"])
    return s.scenarios, s.evidence, s.profile


def reply(**by_scenario):
    return json.dumps({k: v for k, v in by_scenario.items()})


def ids(scenarios):
    return {sc.name: sc.metrics for sc in scenarios}


def test_one_call_for_three_scenarios_and_valid_notes_replace_templates(base):
    scenarios, ev, p = base
    m = ids(scenarios)
    calls = []

    def fake(messages, kind):
        calls.append(kind)
        return reply(
            as_requested=[{"claim": "Perte maximale historique de 23,0 %, la plus forte des trois.", "evidence": [m["as_requested"]["max_drawdown"]]}],
            capped=[{"claim": "Le plafond réduit la perte historique à 6,1 %.", "evidence": [m["capped"]["max_drawdown"]]}],
            profile_baseline=[{"claim": "La volatilité historique la plus basse du comparatif.", "evidence": [m["profile_baseline"]["volatility_ann"]]}],
        )

    llm.set_llm_override(fake)
    out = draft_notes(scenarios, ev, p)
    assert calls == ["fast"]
    assert [sc.name for sc in out] == [sc.name for sc in scenarios]
    assert out[0].notes == [f"Perte maximale historique de 23,0 %, la plus forte des trois. [{m['as_requested']['max_drawdown']}]"]
    assert all(sc.notes != orig.notes for sc, orig in zip(out, scenarios, strict=True))
    assert out[0].weights == scenarios[0].weights and out[0].metrics == scenarios[0].metrics


def test_draft_notes_single_scenario_signature(base):
    scenarios, ev, _ = base
    sc = scenarios[0]
    m = sc.metrics
    llm.set_llm_override(
        lambda msgs, k: reply(
            as_requested=[
                {
                    "claim": "Perte maximale historique de 23,0 %, la plus forte des trois.",
                    "evidence": [m["max_drawdown"]],
                }
            ]
        )
    )
    notes = draft_notes(sc, ev)
    assert isinstance(notes, list)
    assert notes == [
        f"Perte maximale historique de 23,0 %, la plus forte des trois. [{m['max_drawdown']}]"
    ]


def test_draft_notes_importable_from_llm():
    from alphaforge.llm import draft_notes as llm_draft_notes

    assert callable(llm_draft_notes)


@pytest.mark.parametrize(
    "bad",
    [
        [{"claim": "Sans aucune citation.", "evidence": []}],
        [{"claim": "Preuve inventée.", "evidence": ["EP999"]}],
        [{"claim": "Perte de 52,0 %.", "evidence": ["EP2"]}],  # number not in the evidence
        [{"claim": "Vous devriez acheter ce scénario.", "evidence": ["EP2"]}],
        [{"claim": "Cite une preuve d'un autre scénario.", "evidence": ["EP8"]}],
        [{"claim": "a", "evidence": ["EP2"]}] * 3,  # too many notes
    ],
)
def test_invalid_notes_keep_the_templates(base, bad):
    scenarios, ev, p = base
    llm.set_llm_override(lambda m, k: reply(as_requested=bad))
    out = draft_notes(scenarios, ev, p)
    assert out[0].notes == scenarios[0].notes


def test_model_failure_falls_back_silently(base):
    scenarios, ev, p = base
    llm.set_llm_override(lambda m, k: "not json")
    assert draft_notes(scenarios, ev, p) == scenarios
    llm.set_llm_override(None)
    assert draft_notes(scenarios, ev, p) == scenarios  # offline in unit tests
    assert draft_notes([], ev, p) == []


def test_prompt_lists_each_scenario_with_its_ids(base):
    scenarios, ev, p = base
    prompts = []
    llm.set_llm_override(lambda m, k: prompts.append(m[1][1]) or "{}")
    draft_notes(scenarios, ev, p)
    for sc in scenarios:
        assert f"Scénario {sc.name}" in prompts[0]
        assert all(eid in prompts[0] for eid in sc.metrics.values())


@pytest.mark.live
def test_live_notes_cite_evidence(base):
    scenarios, ev, p = base
    out = draft_notes(scenarios, ev, p)
    assert sum(sc.notes != o.notes for sc, o in zip(out, scenarios, strict=True)) >= 2
    assert all("[EP" in n for sc in out for n in sc.notes if sc.notes != [f"Scénario {sc.name} [stub]."])
