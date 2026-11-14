"""End-to-end integration tests for the three datathon personas:
- Amira (High risk, growth & diversification)
- Mateo (Moderate risk, balanced & ESG)
- Robert (Low-to-moderate risk, capital preservation, TSLA test & capped alternative)
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

    def test_amira_pipeline(self, dataset):
        _, _, universe_df = dataset
        res = run_pipeline_for_persona("amira")

        weights = res["weights"]
        metrics = res["risk_metrics"]
        gov = res["governance"]
        ver = res["verification"]

        # Check weights sum to 1.0
        assert pytest.approx(sum(weights.values()), abs=1e-3) == 1.0

        # Check diversification constraints
        sector_map = dict(zip(universe_df["ticker"], universe_df["sector"]))
        class_map = dict(zip(universe_df["ticker"], universe_df["asset_class"]))

        tech_w = sum(w for t, w in weights.items() if sector_map.get(t) == "Information Technology")
        crypto_w = sum(w for t, w in weights.items() if class_map.get(t) == "crypto")

        # Tech <= 40% (not exclusively tech)
        assert tech_w <= 0.40 + 1e-3
        # Crypto <= 15%
        assert crypto_w <= 0.15 + 1e-3
        # All individual assets <= 10%
        for t, w in weights.items():
            assert w <= 0.10 + 1e-3

        # Risk metrics check
        assert metrics["annualized_volatility"] > 0.07  # Growth oriented vol
        assert metrics["active_assets_count"] >= 10  # Broadly diversified

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

        sector_map = dict(zip(universe_df["ticker"], universe_df["sector"]))
        class_map = dict(zip(universe_df["ticker"], universe_df["asset_class"]))

        # ESG core ETF present
        assert "ESGV" in weights
        assert weights["ESGV"] >= 0.15 - 1e-3

        # Crypto strictly 0%
        crypto_w = sum(w for t, w in weights.items() if class_map.get(t) == "crypto")
        assert crypto_w == 0.0

        # Controversial fossil fuel XOM excluded
        assert "XOM" not in weights

        # Energy sector <= 5%
        energy_w = sum(w for t, w in weights.items() if sector_map.get(t) == "Energy")
        assert energy_w <= 0.05 + 1e-3

        # Bonds floor >= 25%
        bond_w = sum(w for t, w in weights.items() if class_map.get(t) == "etf_bond")
        assert bond_w >= 0.25 - 1e-3

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

        # Bonds floor >= 50% for capital preservation
        bond_w = sum(w for t, w in weights.items() if class_map.get(t) == "etf_bond")
        assert bond_w >= 0.50 - 1e-3

        # Crypto strictly 0%
        assert "BTC-USD" not in weights
        assert "ETH-USD" not in weights

        # TSLA is not in baseline
        assert "TSLA" not in weights

        # Volatility is low (capital preservation)
        assert metrics["annualized_volatility"] < 0.05

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

        # Bonds still satisfy >= 50%
        class_map = dict(zip(universe_df["ticker"], universe_df["asset_class"]))
        bond_w = sum(w for t, w in weights.items() if class_map.get(t) == "etf_bond")
        assert bond_w >= 0.50 - 1e-3

        # Controlled volatility
        assert metrics["annualized_volatility"] <= 0.05

        # Governance passes with no blocking alerts
        assert gov.passed is True
        assert gov.has_blocking is False

        # Verifier confirms all numerical claims
        assert ver.is_valid is True
        assert len(ver.errors) == 0
