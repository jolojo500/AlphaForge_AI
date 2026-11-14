"""Unit tests for the evaluation suite and benchmark metric functions."""

import pytest

from alphaforge.app.personas import get_persona
from alphaforge.scripts.eval import (
    compute_allocation_stability,
    compute_citation_coverage,
    compute_constraint_violations,
    compute_governance_match,
    compute_numeric_fidelity,
)


def test_compute_numeric_fidelity_valid():
    """Verify fidelity computation on fully validated verification report."""
    raw_result = {
        "verification": {
            "is_valid": True,
            "total_numbers_verified": 35,
            "total_claims_checked": 8,
            "errors": [],
        }
    }
    metrics = compute_numeric_fidelity(raw_result)
    assert metrics["is_valid"] is True
    assert metrics["numbers_verified"] == 35
    assert metrics["claims_checked"] == 8
    assert metrics["errors_count"] == 0
    assert metrics["fidelity_ratio"] == 1.0


def test_compute_numeric_fidelity_with_errors():
    """Verify fidelity computation when verifier detected numerical errors."""
    raw_result = {
        "verification": {
            "is_valid": False,
            "total_numbers_verified": 30,
            "total_claims_checked": 10,
            "errors": [{"section": "quelles_donnees", "reason": "hallucination", "claim": "99%"}],
        }
    }
    metrics = compute_numeric_fidelity(raw_result)
    assert metrics["is_valid"] is False
    assert metrics["numbers_verified"] == 30
    assert metrics["errors_count"] == 1
    assert round(metrics["fidelity_ratio"], 4) == round(30 / 31, 4)


def test_compute_constraint_violations_compliant():
    """Verify clean allocation returns 0 violations."""
    persona = get_persona("robert")
    raw_result = {
        "allocation": {
            "ZST.TO": 0.50,
            "XBB.TO": 0.30,
            "XIU.TO": 0.20,
        }
    }
    metrics = compute_constraint_violations(raw_result, persona=persona)
    assert metrics["violation_count"] == 0
    assert len(metrics["violations"]) == 0


def test_compute_constraint_violations_with_breaches():
    """Verify constraint breaches (sum != 1, negative weights, cap breaches) are captured."""
    persona = get_persona("robert")
    raw_result = {
        "allocation": {
            "TSLA": 0.40,  # Breaches single asset cap (8%)
            "BTC-USD": 0.20,  # Breaches crypto cap (0% for Robert)
            "XIU.TO": -0.05,  # Negative weight
            "ZST.TO": 0.20,  # Total sum = 0.75 != 1.0
        }
    }
    metrics = compute_constraint_violations(raw_result, persona=persona)
    assert metrics["violation_count"] >= 3
    viol_str = " ".join(metrics["violations"])
    assert "sum" in viol_str.lower()
    assert "negative" in viol_str.lower()
    assert "cap" in viol_str.lower()


def test_compute_citation_coverage_full():
    """Verify citation coverage is 1.0 when all claims have evidence citations."""
    raw_result = {
        "explanation": {
            "quelles_donnees": [{"claim": "Data CAD", "evidence_ids": ["E1"]}],
            "pourquoi_ce_choix": [{"claim": "Vol 4%", "evidence_ids": ["E2", "E3"]}],
            "alertes_gouvernance": [{"message": "Attention TSLA", "evidence_ids": ["E2"]}],
        }
    }
    metrics = compute_citation_coverage(raw_result)
    assert metrics["total_claims"] == 3
    assert metrics["cited_claims"] == 3
    assert metrics["coverage_ratio"] == 1.0


def test_compute_citation_coverage_partial():
    """Verify citation coverage correctly flags ungrounded claims."""
    raw_result = {
        "explanation": {
            "quelles_donnees": [{"claim": "Data CAD", "evidence_ids": ["E1"]}],
            "pourquoi_ce_choix": [{"claim": "Uncited claim", "evidence_ids": []}],
            "alertes_gouvernance": [{"message": "Alert without evidence", "evidence_ids": None}],
        }
    }
    metrics = compute_citation_coverage(raw_result)
    assert metrics["total_claims"] == 3
    assert metrics["cited_claims"] == 1
    assert metrics["coverage_ratio"] == round(1 / 3, 4)


def test_compute_governance_match_levels_and_rules():
    """Verify governance level matching, priority ordering, and specific rule presence."""
    # Priority: bloquant > attention > info
    raw_result = {
        "alerts": [
            {"level": "info", "rule_name": "simulation_boundary_notice", "message": "Simulation"},
            {"level": "attention", "rule_name": "incoherence_horizon_robert_tsla", "message": "TSLA vol"},
        ]
    }
    m1 = compute_governance_match(raw_result, expected_level="attention", expected_rule="incoherence_horizon_robert_tsla")
    assert m1["level_matched"] is True
    assert m1["rule_matched"] is True
    assert m1["highest_level"] == "attention"

    # Blocking alert takes highest priority
    raw_result_blocking = {
        "alerts": [
            {"level": "info", "rule_name": "simulation_boundary_notice"},
            {"level": "attention", "rule_name": "concentration_warning"},
            {"level": "bloquant", "rule_name": "crypto_prohibition_robert"},
        ]
    }
    m2 = compute_governance_match(raw_result_blocking, expected_level="bloquant", expected_rule="crypto_prohibition_robert")
    assert m2["highest_level"] == "bloquant"
    assert m2["level_matched"] is True
    assert m2["rule_matched"] is True


def test_compute_allocation_stability():
    """Verify allocation stability diff computation."""
    alloc_a = {"ZST.TO": 0.4500, "XBB.TO": 0.3500, "XIU.TO": 0.2000}
    alloc_b = {"ZST.TO": 0.4500, "XBB.TO": 0.3500, "XIU.TO": 0.2000}
    alloc_c = {"ZST.TO": 0.4600, "XBB.TO": 0.3400, "XIU.TO": 0.2000}

    s_identical = compute_allocation_stability(alloc_a, alloc_b, tolerance=1e-5)
    assert s_identical["is_identical"] is True
    assert s_identical["max_diff"] == 0.0

    s_diff = compute_allocation_stability(alloc_a, alloc_c, tolerance=1e-5)
    assert s_diff["is_identical"] is False
    assert round(s_diff["max_diff"], 4) == 0.0100
