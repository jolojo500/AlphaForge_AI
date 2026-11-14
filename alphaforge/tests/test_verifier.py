"""Tests for deterministic verifier and anti-hallucination engine:
- test_verifier.py
"""

from __future__ import annotations

import pytest

from alphaforge.app.evidence import EvidenceRegistry
from alphaforge.app.verifier import (
    extract_numbers_from_text,
    is_number_supported,
    verify_explanation,
)


@pytest.fixture
def evidence_registry():
    reg = EvidenceRegistry()
    # E1: Risk metrics
    reg.register(
        tool="risk.portfolio_risk_metrics",
        args={"weights": {"ZST.TO": 0.50, "XBB.TO": 0.50}},
        result={"annualized_volatility": 0.0356, "max_drawdown": -0.0548, "active_assets_count": 2},
        description="Low risk portfolio metrics",
    )
    # E2: 2022 Stress test
    reg.register(
        tool="stress.stress_test_2022_episode",
        args={},
        result={"portfolio": {"cumulative_return": -0.0851, "max_drawdown": -0.1301}},
        description="2022 episode replay",
    )
    # E3: Optimization result
    reg.register(
        tool="optimize.optimize_min_variance",
        args={},
        result={"active_assets": 13, "weights": {"TSLA": 0.03, "ZST.TO": 0.35}},
        description="Constrained weights",
    )
    return reg


class TestVerifier:
    def test_number_extraction(self):
        text = "Portfolio vol is 3.56% and max drawdown reached -5.48% across 13 assets in 2022."
        tokens = extract_numbers_from_text(text)
        assert "3.56%" in tokens
        assert "-5.48%" in tokens
        assert "13" in tokens
        assert "2022" in tokens

    def test_percentage_and_sign_equivalence(self):
        pool = {0.0356, -0.0548, 0.1301}
        # Percentage token matches decimal in pool
        assert is_number_supported("3.56%", pool)
        # Decimal token matches
        assert is_number_supported("0.0356", pool)
        # Positive representation of drawdown matches negative value
        assert is_number_supported("5.48%", pool)
        assert is_number_supported("-5.48%", pool)
        # Fake number fails
        assert not is_number_supported("99.9%", pool)

    def test_valid_explanation_passes(self, evidence_registry):
        payload = {
            "quelles_donnees": [
                {
                    "claim": "Le portefeuille présente une volatilité de 3.56% et un drawdown de -5.48%.",
                    "evidence_ids": ["E1"],
                },
                {
                    "claim": "Lors de la crise de 2022, le recul maximal a été de -13.01%.",
                    "evidence_ids": ["E2"],
                },
            ],
            "pourquoi_ce_choix": [
                {
                    "claim": "L'optimiseur a sélectionné 13 actifs avec 3.0% pour TSLA.",
                    "evidence_ids": ["E3"],
                }
            ],
            "alertes_gouvernance": [],
        }
        report = verify_explanation(payload, evidence_registry)
        assert report.is_valid is True
        assert len(report.errors) == 0
        assert report.total_claims_checked == 3
        assert report.total_numbers_verified >= 4

    def test_deliberate_error_non_existent_evidence_id(self, evidence_registry):
        payload = {
            "quelles_donnees": [
                {
                    "claim": "Le portefeuille présente une volatilité de 3.56%.",
                    "evidence_ids": ["E999"],  # Non-existent ID
                }
            ]
        }
        report = verify_explanation(payload, evidence_registry)
        assert report.is_valid is False
        assert len(report.errors) >= 1
        assert "E999" in report.missing_evidence_ids
        assert any("does not exist" in e.reason for e in report.errors)

    def test_deliberate_error_hallucinated_number(self, evidence_registry):
        payload = {
            "quelles_donnees": [
                {
                    "claim": "Le portefeuille a produit un rendement fabuleux de 45.8%.",
                    "evidence_ids": ["E1"],
                }
            ]
        }
        report = verify_explanation(payload, evidence_registry)
        assert report.is_valid is False
        assert len(report.errors) == 1
        assert "45.8%" in report.errors[0].missing_value
        assert "not supported by cited evidence" in report.errors[0].reason

    def test_deliberate_error_number_without_evidence_citation(self, evidence_registry):
        payload = {
            "quelles_donnees": [
                {
                    "claim": "Le portefeuille a une volatilité de 3.56%.",
                    "evidence_ids": [],  # Empty citations
                }
            ]
        }
        report = verify_explanation(payload, evidence_registry)
        assert report.is_valid is False
        assert len(report.errors) == 1
        assert "without citing any Evidence ID" in report.errors[0].reason

    def test_deliberate_error_wrong_evidence_cited(self, evidence_registry):
        # Claiming stress test stats (13.01%) but citing E1 (which only has 3.56% and -5.48%)
        payload = {
            "quelles_donnees": [
                {
                    "claim": "Le recul en 2022 a été de 13.01%.",
                    "evidence_ids": ["E1"],  # Wrong evidence! E2 contains 13.01%, not E1
                }
            ]
        }
        report = verify_explanation(payload, evidence_registry)
        assert report.is_valid is False
        assert len(report.errors) == 1
        assert "13.01%" in report.errors[0].missing_value
