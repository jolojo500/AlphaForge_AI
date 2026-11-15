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


# --- #114: adversarial cases ------------------------------------------------------------
def _ev114():
    import datetime as dt

    from alphaforge.state import Evidence

    def e(i, val):
        return Evidence(id=i, value={"metric": "m", "value": val}, source="t",
                        date=dt.date(2026, 1, 1), method="t")
    return {"EP3": e("EP3", -0.232), "EP9": e("EP9", -0.061)}


def _doc114(**kw):
    base = {"resume": "Comparaison.", "incertitude": "Historique.",
            "quelles_donnees": [{"claim": "Perte maximale de -23,2 %.", "evidence": ["EP3"]}],
            "pourquoi_ce_choix": [], "limites": [], "ce_qui_changerait_la_reponse": []}
    return base | kw


def test_invented_number_in_resume_fails():
    errs = v.check_numbers(_doc114(resume="Une perte maximale de -12 % en 2022."), _ev114())
    assert errs and errs[0].startswith("resume")


def test_number_in_resume_with_inline_id_passes():
    assert v.check_numbers(_doc114(resume="Une perte maximale de -23,2 % [EP3]."), _ev114()) == []


def test_percentage_equal_to_an_unrelated_weight_fails():
    weights = {"capped": [0.20, 0.05], "as_requested": [0.25]}
    doc = _doc114(quelles_donnees=[{"claim": "Une perte de 20 % au pire.", "evidence": ["EP3"]}])
    assert v.check_numbers(doc, _ev114(), [], weights)


def test_weight_of_the_named_scenario_passes():
    weights = {"capped": [0.20, 0.05], "as_requested": [0.25]}
    doc = _doc114(quelles_donnees=[{"claim": "Le scénario plafonné garde TSLA à 5 %.", "evidence": ["EP9"]}])
    assert v.check_numbers(doc, _ev114(), [], weights) == []


def test_points_are_checked_and_differences_allowed():
    ok = _doc114(quelles_donnees=[{"claim": "Un écart de 17,1 points.", "evidence": ["EP3", "EP9"]}])
    bad = _doc114(quelles_donnees=[{"claim": "Un écart de 47 points.", "evidence": ["EP3", "EP9"]}])
    assert v.check_numbers(ok, _ev114()) == []
    assert v.check_numbers(bad, _ev114())


# ---- English & French wording and i18n tests (#123)
@pytest.mark.parametrize(
    "en_forbidden",
    [
        "You should buy more technology equities.",
        "We recommend allocating 25% to this asset.",
        "I advise that you prioritize short-term notes.",
        "A guaranteed return of 6% each year.",
        "This is a risk-free investment opportunity.",
        "Expected return for this strategy is 10%.",
        "The portfolio will return double digits.",
        "This asset will grow faster than inflation.",
        "The fund will yield steady monthly profits.",
        "The price will outperform the benchmark index.",
    ],
)
def test_verifier_forbidden_wording_english(evidence, en_forbidden):
    doc = mutate(resume=en_forbidden)
    errs = v.check_wording(doc)
    assert len(errs) > 0
    assert any("formulation interdite" in err for err in errs)


@pytest.mark.parametrize(
    "en_clean",
    [
        "Educational simulation. No personalized advice.",
        "No guaranteed return; past metrics do not forecast future performance.",
        "The version adjusted to your limits is most consistent with the declared risk tolerance.",
        "Historical statistics show a maximum drawdown of 15.2% without indicating future returns.",
        "The comparison illustrates differences in volatility and diversification.",
    ],
)
def test_verifier_clean_wording_english(evidence, en_clean):
    doc = mutate(
        resume=en_clean,
        incertitude="No return is guaranteed; historical data does not predict the future.",
        avertissement="Educational simulation. No personalized advice.",
    )
    assert v.check_wording(doc) == []


def test_verifier_english_section_keys(evidence):
    doc_en = {
        "summary": "Comparison of three simulated scenarios.",
        "what_data": [{"claim": "Volatilité de 18,5 %.", "evidence": ["EQ2"]}],
        "why_this_choice": [{"claim": "Perte de 38,2 %.", "evidence": ["EQ1"]}],
        "limits": [{"claim": "Statistiques historiques.", "evidence": []}],
        "what_would_change": [{"claim": "Un autre horizon.", "evidence": []}],
        "uncertainty": "No future guarantee.",
        "most_consistent_scenario": "capped",
        "disclaimer": "Educational simulation. No personalized advice.",
    }
    assert v.check_sections(doc_en) == []
    assert v.check_wording(doc_en) == []
    assert v.check_eids(doc_en, evidence) == []


@pytest.mark.parametrize(
    "internal_id_text",
    [
        "Le scénario as_requested dépasse les limites déclarées.",
        "Le scénario capped réduit le risque du portefeuille.",
        "Le scénario profile_baseline sert de référence.",
        "Selon votre persona Robert.",
        "Le policy_rate_ca est de 2,25 %.",
        "Le policy_rate_us est de 4,5 %.",
        "L'indicateur cpi_yoy_ca augmente.",
        "You should hold this equity.",
        "ACHAT de 10 000 $",
        "VENTE de 5 000 $",
        "BUY 5 shares",
        "SELL 10 shares",
        "HOLD 2 shares",
    ],
)
def test_verifier_blocks_internal_identifiers_hold_and_orders(evidence, internal_id_text):
    doc = mutate(resume=internal_id_text)
    errs = v.check_wording(doc)
    assert len(errs) > 0
    assert any("formulation interdite" in err for err in errs)



@pytest.mark.parametrize(
    "text",
    [
        "Exposure is capped at 5 % in the adjusted version.",
        "US equity exposure was capped at 40 %.",
        "Single positions are capped to 10 % each.",
        "The assets you currently hold are mostly Canadian.",
        "The positions you hold in a TFSA are listed ETFs.",
        "What you hold today is concentrated in one market.",
        "This is a buy-and-hold simulation, not a forecast.",
    ],
)
def test_english_capped_and_hold_as_plain_verbs_pass(text):
    """#186 item 6: the plain verbs are not the scenario name or a hold recommendation."""
    assert v.check_text_wording([("resume", text)]) == []


@pytest.mark.parametrize(
    "text",
    [
        "Hold TSLA until the next quarter.",
        "A hold recommendation applies to this position.",
        "We suggest you hold this equity.",
        "Scenario capped reduces the risk.",
        "The capped scenario reduces the risk.",
        "Compare capped and profile_baseline.",
        "Le scénario capped réduit le risque.",
    ],
)
def test_english_capped_name_and_hold_recommendation_still_fail(text):
    errs = v.check_text_wording([("resume", text)])
    assert errs and all("formulation interdite" in e for e in errs)
