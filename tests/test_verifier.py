import copy
import datetime as dt

import pytest

from alphaforge.evidence import EvidenceRegistry
from alphaforge.nodes import verifier as v
from alphaforge.state import GraphState, Profile, Scenario

D = dt.date(2026, 11, 12)


@pytest.fixture
def evidence():
    reg = EvidenceRegistry("EQ")
    reg.add({"metric": "max_drawdown", "ticker": "TSLA", "value": -0.382}, "p.csv", D, "m")  # EQ1
    reg.add({"metric": "volatility_ann", "ticker": "SPY", "value": 0.1845}, "p.csv", D, "m")  # EQ2
    reg.add({"metric": "policy_rate_ca", "value": 2.25, "unit": "%"}, "m.csv", D, "m")  # EQ3
    return reg.items()


CLEAN = {
    "resume": "Comparaison de trois scénarios fictifs pour le profil déclaré.",
    "quelles_donnees": [
        {"claim": "La perte maximale historique de TSLA est de 38,2 %.", "evidence": ["EQ1"]},
        {"claim": "La volatilité annualisée de SPY est de 0,18.", "evidence": ["EQ2"]},
        {"claim": "Le taux directeur est de 2,25 %.", "evidence": ["EQ3"]},
    ],
    "pourquoi_ce_choix": [
        {"claim": "Le scénario plafonné limite la perte historique.", "evidence": ["EQ1"]}
    ],
    "limites": [{"claim": "Le passé ne prédit pas l'avenir.", "evidence": []}],
    "ce_qui_changerait_la_reponse": [{"claim": "Un horizon plus long.", "evidence": []}],
    "incertitude": "Les statistiques historiques ne décrivent pas l'avenir.",
    "scenario_le_plus_coherent": "capped",
    "avertissement": "Simulation éducative. Aucun conseil personnalisé.",
}


def mutate(**changes):
    e = copy.deepcopy(CLEAN)
    e.update(changes)
    return e


def test_clean_explanation_passes_every_check(evidence):
    assert v.check_sections(CLEAN) == []
    assert v.check_eids(CLEAN, evidence) == []
    assert v.check_numbers(CLEAN, evidence) == []
    assert v.check_wording(CLEAN) == []


# ---- eids: one fixture that fails for exactly this reason
def test_unknown_evidence_id_fails_only_eids(evidence):
    e = mutate(pourquoi_ce_choix=[{"claim": "Le plafond réduit le risque.", "evidence": ["EQ99"]}])
    assert v.check_eids(e, evidence) == ["pourquoi_ce_choix: preuve inconnue EQ99"]
    assert v.check_sections(e) == [] and v.check_wording(e) == []
    assert v.check_numbers(e, evidence) == []


def test_unknown_id_inside_claim_text(evidence):
    e = mutate(limites=[{"claim": "Voir EP7 pour le détail.", "evidence": []}])
    assert any("EP7" in m for m in v.check_eids(e, evidence))


def test_fact_claim_without_evidence_fails(evidence):
    e = mutate(quelles_donnees=[{"claim": "Les actions sont volatiles.", "evidence": []}])
    assert any("sans preuve" in m for m in v.check_eids(e, evidence))


# ---- numbers
def test_wrong_number_fails_only_numbers(evidence):
    e = mutate(
        quelles_donnees=[{"claim": "La perte maximale de TSLA est de 52,0 %.", "evidence": ["EQ1"]}]
    )
    errs = v.check_numbers(e, evidence)
    assert len(errs) == 1 and "52 %" in errs[0]
    assert v.check_sections(e) == [] and v.check_wording(e) == []
    assert v.check_eids(e, evidence) == []


def test_number_without_any_citation_fails(evidence):
    e = mutate(limites=[{"claim": "La volatilité est de 0,18.", "evidence": []}])
    assert "aucune preuve" in v.check_numbers(e, evidence)[0]


@pytest.mark.parametrize(
    "claim,eid",
    [
        ("Perte de 38,2 %.", "EQ1"),  # ratio -> percent
        ("Perte de 38 %.", "EQ1"),  # rounded
        ("Perte de 0,38.", "EQ1"),  # kept as ratio
        ("Volatilité de 18,5 %.", "EQ2"),
        ("Volatilité de 18 %.", "EQ2"),  # 18.45 rounded to the digits shown
        ("Taux de 2,25 %.", "EQ3"),  # already a percent
        ("Taux de 2.25 %.", "EQ3"),  # dot decimal
    ],
)
def test_number_conversions_are_accepted(evidence, claim, eid):
    e = mutate(quelles_donnees=[{"claim": claim, "evidence": [eid]}])
    assert v.check_numbers(e, evidence) == []


def test_numbers_ignore_ids_dates_and_bare_integers(evidence):
    claim = "Sur 5 ans, au 2026-11-12, avec 100 000 $ (EQ12) en 2022."
    assert v.extract_numbers(claim) == []


def test_context_numbers_allow_user_and_scenario_values(evidence):
    e = mutate(
        quelles_donnees=[{"claim": "Vous proposez 25 % dans TSLA.", "evidence": ["EQ1"]}]
    )
    assert v.check_numbers(e, evidence)
    assert v.check_numbers(e, evidence, context=[0.25]) == []


# ---- wording
@pytest.mark.parametrize(
    "text",
    [
        "Vous devriez acheter ce titre.",
        "You should buy this ETF.",
        "Rendement garanti sur dix ans.",
        "This fund will return 8% a year.",
        "Le rendement attendu est élevé.",
        "Un placement sans risque.",
    ],
)
def test_forbidden_wording_fails_only_wording(evidence, text):
    e = mutate(resume=text)
    assert v.check_wording(e)
    assert v.check_sections(e) == [] and v.check_eids(e, evidence) == []


def test_negated_phrase_and_disclaimer_are_allowed():
    e = mutate(incertitude="Aucun rendement garanti ; ce n'est pas un conseil.")
    assert v.check_wording(e) == []
    assert "conseil" in CLEAN["avertissement"]


# ---- sections
@pytest.mark.parametrize(
    "key", ["quelles_donnees", "pourquoi_ce_choix", "limites", "ce_qui_changerait_la_reponse"]
)
def test_missing_section_fails_only_sections(evidence, key):
    e = mutate(**{key: []})
    errs = v.check_sections(e)
    assert errs == [f"{key}: section manquante ou vide"]
    assert v.check_wording(e) == [] and v.check_numbers(e, evidence) == []


@pytest.mark.parametrize("key", ["incertitude", "avertissement", "resume"])
def test_empty_text_field_fails(key):
    assert any(key in m for m in v.check_sections(mutate(**{key: " "})))


def test_disclaimer_must_mention_simulation_and_scenario_valid():
    assert v.check_sections(mutate(avertissement="Merci."))
    assert v.check_sections(mutate(scenario_le_plus_coherent="best"))


# ---- node
def _state(evidence, explanation):
    sc = [Scenario(name=n, weights={"SPY": 1.0}) for n in v.SCENARIO_NAMES]
    profile = Profile(
        persona="robert", objective="x", horizon_years=4, risk_tolerance="low_moderate",
        risk_capacity="low",
    )
    return GraphState(
        as_of_date=D, persona="robert", profile=profile, evidence=evidence,
        explanation=explanation, scenarios=sc,
    )


def test_node_passes_clean(evidence):
    out = v.verifier_node(_state(evidence, CLEAN))
    assert out["verification"] == {"passed": True, "errors": []}
    assert "retries" not in out and out["trace"][0]["node"] == "verifier"


def test_node_fails_and_counts_retry(evidence):
    out = v.verifier_node(_state(evidence, mutate(resume="Vous devriez acheter.")))
    assert out["verification"]["passed"] is False
    assert out["retries"] == {"explain": 1}


def test_node_without_explanation_fails(evidence):
    out = v.verifier_node(_state(evidence, None))
    assert out["verification"]["passed"] is False
