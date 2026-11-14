"""End-to-end integration tests for the three datathon personas (Phase 1b):
- Amira (High risk, growth & diversification, AI/NVDA exposure)
- Mateo (Moderate risk, balanced & provisional ESG exclusions)
- Robert (Low-to-moderate risk, capital preservation, TSLA test & capped alternative)

Validates strict persona differentiation:
- Vol_Amira > Vol_Mateo > Vol_Robert
- Target volatility band adherence
- Strategic sleeve and preference constraints
"""

from __future__ import annotations

import pytest

from alphaforge.app.governance import check_governance_rules
from alphaforge.app.personas import get_persona
from alphaforge.app.tools.prices import get_processed_dataset
from alphaforge.app.tools.risk import asset_summary_metrics
from alphaforge.scripts.run_personas import run_pipeline_for_persona


@pytest.fixture(scope="module")
def shared_dataset():
    return get_processed_dataset()


class TestPersonasEndToEnd:
    @pytest.fixture
    def dataset(self, shared_dataset):
        return shared_dataset

    def test_persona_volatility_ordering(self, dataset):
        """Confirm strict persona differentiation: Amira vol > Mateo vol > Robert vol."""
        res_amira = run_pipeline_for_persona("amira")
        res_mateo = run_pipeline_for_persona("mateo")
        res_robert = run_pipeline_for_persona("robert")

        vol_amira = res_amira["risk_metrics"]["annualized_volatility"]
        vol_mateo = res_mateo["risk_metrics"]["annualized_volatility"]
        vol_robert = res_robert["risk_metrics"]["annualized_volatility"]

        # Strict ordering
        assert vol_amira > vol_mateo > vol_robert

        # Target bands adherence
        assert 0.12 <= vol_amira <= 0.20
        assert 0.06 <= vol_mateo <= 0.11
        assert 0.035 <= vol_robert <= 0.060

        assert res_amira["vol_band_audit"]["within_band"] is True
        assert res_mateo["vol_band_audit"]["within_band"] is True
        assert res_robert["vol_band_audit"]["within_band"] is True

    def test_amira_pipeline(self, dataset):
        _, _, universe_df = dataset
        res = run_pipeline_for_persona("amira")

        weights = res["weights"]
        metrics = res["risk_metrics"]
        gov = res["governance"]
        ver = res["verification"]

        # Check weights sum to 1.0
        assert pytest.approx(sum(weights.values()), abs=1e-3) == 1.0

        sector_map = dict(zip(universe_df["ticker"], universe_df["sector"]))
        class_map = dict(zip(universe_df["ticker"], universe_df["asset_class"]))

        tech_w = sum(w for t, w in weights.items() if sector_map.get(t) == "Information Technology")
        crypto_w = sum(w for t, w in weights.items() if class_map.get(t) == "crypto")

        # Amira has meaningful tech exposure and specifically NVDA
        assert "NVDA" in weights
        assert weights["NVDA"] >= 0.04
        assert tech_w >= 0.25
        assert tech_w <= 0.40 + 1e-3

        # Crypto between 5% and 10%
        assert crypto_w >= 0.05 - 1e-3
        assert crypto_w <= 0.10 + 1e-3

        # Individual equities capped at 10%
        for t, w in weights.items():
            if class_map.get(t) == "equity":
                assert w <= 0.10 + 1e-3

        # High growth volatility profile
        assert metrics["annualized_volatility"] >= 0.12
        assert metrics["active_assets_count"] >= 10

        # Governance and Verifier
        assert gov.passed is True
        assert ver.is_valid is True
        assert len(ver.errors) == 0

    def test_mateo_pipeline(self, dataset):
        _, _, universe_df = dataset
        res = run_pipeline_for_persona("mateo")

        weights = res["weights"]
        metrics = res["risk_metrics"]
        gov = res["governance"]
        ver = res["verification"]

        # Check weights sum to 1.0
        assert pytest.approx(sum(weights.values()), abs=1e-3) == 1.0

        class_map = dict(zip(universe_df["ticker"], universe_df["asset_class"]))

        # ESG core ETF present
        assert "ESGV" in weights
        assert weights["ESGV"] >= 0.15 - 1e-3

        # Crypto strictly 0%
        crypto_w = sum(w for t, w in weights.items() if class_map.get(t) == "crypto")
        assert crypto_w == 0.0

        # Provisional ESG exclusions: CNQ.TO, ENB.TO, XOM completely absent
        assert "CNQ.TO" not in weights
        assert "ENB.TO" not in weights
        assert "XOM" not in weights

        # Bonds sleeve represents ~35%
        bond_w = sum(w for t, w in weights.items() if class_map.get(t) == "etf_bond")
        assert bond_w >= 0.30

        # Governance has provisional ESG info alert
        assert any(a.rule_name == "provisional_esg_screening_mateo" and a.level == "info" for a in gov.alerts)

        # Governance and Verifier
        assert gov.passed is True
        assert ver.is_valid is True
        assert len(ver.errors) == 0

    def test_robert_baseline_pipeline(self, dataset):
        _, _, universe_df = dataset
        res = run_pipeline_for_persona("robert")

        weights = res["weights"]
        metrics = res["risk_metrics"]
        gov = res["governance"]
        ver = res["verification"]

        # Check weights sum to 1.0
        assert pytest.approx(sum(weights.values()), abs=1e-3) == 1.0

        class_map = dict(zip(universe_df["ticker"], universe_df["asset_class"]))

        # Bonds sleeve >= 55% for retirement capital preservation
        bond_w = sum(w for t, w in weights.items() if class_map.get(t) == "etf_bond")
        assert bond_w >= 0.55

        # Crypto strictly 0%
        assert "BTC-USD" not in weights
        assert "ETH-USD" not in weights

        # TSLA is not in baseline
        assert "TSLA" not in weights

        # Volatility is low (capital preservation)
        assert metrics["annualized_volatility"] < 0.045

        # Governance and Verifier
        assert gov.passed is True
        assert ver.is_valid is True
        assert len(ver.errors) == 0

    def test_robert_reality_check_governance_block(self, dataset):
        returns_df, _, universe_df = dataset
        robert = get_persona("robert")
        summary = asset_summary_metrics(returns_df)

        # Robert aggressively requesting 20% TSLA and 5% Crypto
        gov_rep = check_governance_rules(
            persona=robert,
            proposed_weights={"TSLA": 0.20, "BTC-USD": 0.05, "ZST.TO": 0.40, "XBB.TO": 0.35},
            universe_df=universe_df,
            risk_summary_df=summary,
            user_requests=["Give me 20% TSLA and 5% Bitcoin!"],
        )

        # Must fail due to blocking crypto rule
        assert gov_rep.passed is False
        assert gov_rep.has_blocking is True
        assert gov_rep.has_attention is True

        # Check blocking alert on crypto
        assert any(a.rule_name == "crypto_prohibition_robert" and a.level == "bloquant" for a in gov_rep.alerts)

        # Check incoherence alert on TSLA
        assert any(a.rule_name == "robert_tsla_incoherence" and a.level == "attention" for a in gov_rep.alerts)

        # Capped alternative must propose capping TSLA at 0.03
        assert gov_rep.capped_alternatives.get("TSLA") == 0.03

    def test_robert_capped_alternative_pipeline(self, dataset):
        _, _, universe_df = dataset
        # Running Robert with capped alternative: TSLA forced to 3% satellite
        res = run_pipeline_for_persona("robert", user_requests=["TSLA"], force_tsla_weight=0.03)

        weights = res["weights"]
        metrics = res["risk_metrics"]
        gov = res["governance"]
        ver = res["verification"]

        assert pytest.approx(weights.get("TSLA", 0.0), abs=1e-3) == 0.03

        # Bonds still satisfy >= 55%
        class_map = dict(zip(universe_df["ticker"], universe_df["asset_class"]))
        bond_w = sum(w for t, w in weights.items() if class_map.get(t) == "etf_bond")
        assert bond_w >= 0.55

        # Controlled volatility
        assert metrics["annualized_volatility"] <= 0.05

        # Governance passes with no blocking alerts
        assert gov.passed is True
        assert gov.has_blocking is False

        # Verifier confirms all numerical claims
        assert ver.is_valid is True
        assert len(ver.errors) == 0
