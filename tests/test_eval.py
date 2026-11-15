"""Unit tests for the evaluation script (scripts/eval.py).

Owned by Track B (B-10). Tests metric calculations, markdown formatting,
and case definitions without running long e2e graphs.
"""
from __future__ import annotations

import pytest

from alphaforge.state import Evidence, GraphState, Profile, Scenario
from scripts.eval import (
    CASES,
    CaseResult,
    compute_citation_coverage,
    compute_constraint_violations,
    compute_numeric_fidelity,
    compute_stability,
    format_markdown_section,
    format_markdown_table,
)


def test_cases_cover_all_requirements():
    ids = [c["id"] for c in CASES]
    assert "amira_base" in ids
    assert "mateo_base" in ids
    assert "robert_base" in ids
    assert "robert_tsla" in ids
    assert "amira_crypto" in ids
    assert "mateo_enb" in ids
    assert "contradictory" in ids
    assert len(CASES) == 7


def test_compute_numeric_fidelity_no_errors():
    ev = {
        "E1": Evidence(
            id="E1",
            source="s",
            date="2026-11-12",
            method="m",
            value={"value": 15.0, "unit": "ratio"},
            confidence="fact",
        )
    }
    explanation = {
        "quelles_donnees": [{"claim": "Allocation de 15,0 %", "evidence": ["E1"]}],
        "pourquoi_ce_choix": [],
        "limites": [],
        "ce_qui_changerait_la_reponse": [],
    }
    state = GraphState(as_of_date="2026-11-12", persona="amira", request_text="", evidence=ev, explanation=explanation)
    display, errs, total = compute_numeric_fidelity(state)
    assert errs == 0
    assert "100 %" in display
    assert total >= 1


def test_compute_citation_coverage():
    ev = {
        "E1": Evidence(
            id="E1",
            source="s",
            date="2026-11-12",
            method="m",
            value="test",
            confidence="fact",
        )
    }
    explanation = {
        "quelles_donnees": [{"claim": "Claim 1", "evidence": ["E1"]}],
        "pourquoi_ce_choix": [{"claim": "Claim 2", "evidence": ["E1"]}],
        "limites": [],
        "ce_qui_changerait_la_reponse": [],
    }
    state = GraphState(as_of_date="2026-11-12", persona="amira", request_text="", evidence=ev, explanation=explanation)
    display, cited, total = compute_citation_coverage(state)
    assert cited == 2
    assert total == 2
    assert display == "100 % (2/2)"


def test_compute_stability_identical():
    sc1 = [Scenario(name="capped", weights={"SPY": 0.5, "AGG": 0.5})]
    sc2 = [Scenario(name="capped", weights={"SPY": 0.5, "AGG": 0.5})]
    ev = {
        "E1": Evidence(
            id="E1",
            source="s",
            date="2026-11-12",
            method="m",
            value="v",
            confidence="fact",
        )
    }
    s1 = GraphState(as_of_date="2026-11-12", persona="amira", request_text="", scenarios=sc1, evidence=ev)
    s2 = GraphState(as_of_date="2026-11-12", persona="amira", request_text="", scenarios=sc2, evidence=ev)
    display, max_diff = compute_stability(s1, s2)
    assert max_diff == pytest.approx(0.0)
    assert "100 %" in display


def test_compute_constraint_violations():
    prof = Profile(
        persona="robert",
        objective="capital_preservation",
        horizon_years=4,
        risk_tolerance="low_moderate",
        risk_capacity="low",
        constraints=["no_crypto"],
        preferences=[],
        budget_cad=None,
        request_type="build",
        requested_idea=None,
        conflicts=[],
    )
    sc = [
        Scenario(name="capped", weights={"SPY": 0.05, "AGG": 0.95}),
        Scenario(name="profile_baseline", weights={"SPY": 0.05, "AGG": 0.95}),
    ]
    s = GraphState(as_of_date="2026-11-12", persona="robert", request_text="", profile=prof, scenarios=sc)
    count, details = compute_constraint_violations(s)
    assert count == 0
    assert details == []


def test_markdown_table_formatting():
    dummy = [
        CaseResult(
            case_id="c1",
            name="Test Case",
            persona="amira",
            request_summary="Summary",
            request_text="text",
            numeric_fidelity="100 % (5/5)",
            numeric_errors=0,
            total_numbers=5,
            constraint_violations=0,
            violations_detail=[],
            citation_coverage="100 % (4/4)",
            cited_claims=4,
            total_claims=4,
            stability="100 % (Δ=0,0)",
            max_weight_diff=0.0,
            whatif_coherence="Cohérent (excl. SPY)",
            verifier_status="Conforme",
            interrupted_resolved=False,
        )
    ]
    table = format_markdown_table(dummy)
    assert "| **Test Case** |" in table
    assert "100 % (5/5)" in table

    section = format_markdown_section(dummy)
    assert "### 10.1 Évaluation globale du graphe et cas adverses" in section
    assert "| **Test Case** |" in section
