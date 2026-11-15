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
    "resume": "Comparaison de trois scénarios fictifs pour le profil déclaré [EQ1].",
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
    "incertitude": "Les statistiques historiques ne décrivent pas l'avenir [EQ3].",
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


def test_resume_and_incertitude_require_inline_evidence(evidence):
    e = mutate(
        resume="Comparaison de trois scénarios fictifs pour le profil déclaré.",
        incertitude="Les statistiques historiques ne décrivent pas l'avenir.",
    )
    errs = v.check_eids(e, evidence)
    assert "resume: aucune preuve citée" in errs
    assert "incertitude: aucune preuve citée" in errs


def test_unknown_id_in_resume_is_caught(evidence):
    e = mutate(resume="La perte maximale historique est de 38,2 % [EQ99].")
    assert any("EQ99" in m for m in v.check_eids(e, evidence))


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


@pytest.mark.parametrize("text", ["47 points", "47 point", "47 pts"])
def test_integers_followed_by_a_unit_are_checked(evidence, text):
    e = mutate(limites=[{"claim": f"La perte atteint {text}.", "evidence": ["EQ1"]}])
    errs = v.check_numbers(e, evidence)
    assert len(errs) == 1 and "47" in errs[0]


def test_invented_number_in_resume_fails(evidence):
    e = mutate(resume="Le scénario plafonné limiterait la perte maximale à 12 % [EQ1].")
    errs = v.check_numbers(e, evidence)
    assert any("resume" in m and "12 %" in m for m in errs)


def test_resume_number_matches_its_cited_evidence(evidence):
    e = mutate(resume="La perte maximale historique est de 38,2 % [EQ1].")
    assert v.check_numbers(e, evidence) == []


def _state_with_scenarios(evidence, explanation, scenarios):
    profile = Profile(
        persona="robert", objective="x", horizon_years=4, risk_tolerance="low_moderate",
        risk_capacity="low",
    )
    return GraphState(
        as_of_date=D, persona="robert", profile=profile, evidence=evidence,
        explanation=explanation, scenarios=scenarios,
    )


def _weights(name, tsla, spy):
    return Scenario(name=name, weights={"TSLA": tsla, "SPY": spy})


def test_weight_from_another_scenario_is_not_allowed(evidence):
    scenarios = [
        _weights("as_requested", 0.20, 0.80),
        _weights("capped", 0.05, 0.95),
        _weights("profile_baseline", 0.0, 1.0),
    ]
    e = mutate(
        quelles_donnees=[{"claim": "Le scénario plafonné place 20 % dans TSLA.", "evidence": ["EQ1"]}]
    )
    assert any("20 %" in m for m in v.verify(_state_with_scenarios(evidence, e, scenarios)))


def test_weight_of_the_named_scenario_is_allowed(evidence):
    scenarios = [
        _weights("as_requested", 0.20, 0.80),
        _weights("capped", 0.05, 0.95),
        _weights("profile_baseline", 0.0, 1.0),
    ]
    e = mutate(
        quelles_donnees=[{"claim": "Le scénario plafonné place 5 % dans TSLA.", "evidence": ["EQ1"]}]
    )
    assert not any("5 %" in m for m in v.verify(_state_with_scenarios(evidence, e, scenarios)))


def test_made_up_percentage_equal_to_some_weight_fails(evidence):
    scenarios = [
        _weights("as_requested", 0.04, 0.96),
        _weights("capped", 0.05, 0.95),
        _weights("profile_baseline", 0.0, 1.0),
    ]
    e = mutate(
        quelles_donnees=[{"claim": "La perte maximale historique est de 4 %.", "evidence": ["EQ1"]}]
    )
    assert any("4 %" in m for m in v.verify(_state_with_scenarios(evidence, e, scenarios)))


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
        "Le portefeuille rapportera 8 % par an.",
        "Nous recommandons ce scénario.",
        "Ce placement générera des gains.",
        "Cette option produira des gains.",
        "Le titre atteindra un sommet.",
        "The fund will yield a good return.",
        "The ETF will generate profit.",
        "The price will reach new highs.",
        "Le rendement espéré est élevé.",
        "Le rendement prévu est stable.",
        "Expected return is positive.",
        "We recommend this allocation.",
        "You should choose this.",
        "Je conseille cette approche.",
    ],
)
def test_forbidden_wording_fails_only_wording(evidence, text):
    e = mutate(resume=f"{text} [EQ1]")
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


# ---- acceptance case from issue #54
@pytest.fixture
def ev042():
    reg = EvidenceRegistry("EP")
    reg.add({"metric": "max_drawdown", "scenario": "capped", "value": 0.42}, "p.csv", D, "m")
    return reg.items()


@pytest.mark.parametrize("text", ["42%", "42 %", "0,42", "42,0 %", "0.42", "42.0%"])
def test_issue_42_formats_pass(ev042, text):
    e = mutate(quelles_donnees=[{"claim": f"Perte maximale de {text}.", "evidence": ["EP1"]}])
    assert v.check_numbers(e, ev042) == []


def test_issue_35_against_042_fails(ev042):
    e = mutate(quelles_donnees=[{"claim": "Perte maximale de 35 %.", "evidence": ["EP1"]}])
    assert len(v.check_numbers(e, ev042)) == 1


def test_years_and_scenario_counts_are_ignored(ev042):
    e = mutate(quelles_donnees=[{"claim": "Les 3 scénarios, sur 2022 et 2026, citent EP1.", "evidence": ["EP1"]}])
    assert v.check_numbers(e, ev042) == []
