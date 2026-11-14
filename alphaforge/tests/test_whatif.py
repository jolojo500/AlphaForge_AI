"""Unit tests for AlphaForge what-if simulation and persona comparison engine."""

from __future__ import annotations

import pytest

from alphaforge.app.evidence import EvidenceRegistry
from alphaforge.app.personas import get_persona
from alphaforge.app.tools.prices import get_processed_dataset
from alphaforge.app.whatif import (
    WhatIfParams,
    build_whatif_sleeves,
    compute_2022_stress_curve,
    compute_diff_table,
    generate_whatif_explanation,
    run_persona_comparison,
    run_whatif_analysis,
)


class TestWhatIfModule:
    """Tests for pure functions and what-if simulation pipeline."""

    def test_build_whatif_sleeves_crypto_adjustment(self) -> None:
        """Test crypto cap adjustment on Amira (baseline 10%) and Robert (baseline 0%)."""
        amira = get_persona("amira")
        robert = get_persona("robert")

        # Amira reduce crypto to 0%
        sleeves_amira_no_crypto = build_whatif_sleeves(
            amira.constraints.strategic_sleeves,
            crypto_cap=0.0,
        )
        total_w = sum(s.target_weight for s in sleeves_amira_no_crypto)
        assert abs(total_w - 1.0) < 1e-4
        crypto_sleeve = next((s for s in sleeves_amira_no_crypto if s.name == "crypto"), None)
        assert crypto_sleeve is None or crypto_sleeve.target_weight < 1e-3

        # Robert add crypto 5%
        sleeves_robert_crypto = build_whatif_sleeves(
            robert.constraints.strategic_sleeves,
            crypto_cap=0.05,
        )
        total_w_r = sum(s.target_weight for s in sleeves_robert_crypto)
        assert abs(total_w_r - 1.0) < 1e-4
        r_crypto = next((s for s in sleeves_robert_crypto if s.name == "crypto"), None)
        assert r_crypto is not None
        assert abs(r_crypto.target_weight - 0.05) < 1e-3

    def test_build_whatif_sleeves_single_asset_cap(self) -> None:
        """Test single asset cap constraint scaling."""
        mateo = get_persona("mateo")
        sleeves = build_whatif_sleeves(
            mateo.constraints.strategic_sleeves,
            single_asset_cap=0.05,
        )
        eq_sleeve = next(s for s in sleeves if s.name == "equity")
        assert eq_sleeve.single_asset_cap is not None
        assert eq_sleeve.single_asset_cap <= 0.12  # intra-sleeve cap scaled down

    def test_build_whatif_sleeves_target_vol_and_horizon(self) -> None:
        """Test volatility target shifting equity vs bond ratio."""
        robert = get_persona("robert")
        sleeves_high_vol = build_whatif_sleeves(
            robert.constraints.strategic_sleeves,
            target_vol=0.15,
        )
        eq = next(s for s in sleeves_high_vol if s.name == "equity")
        bd = next(s for s in sleeves_high_vol if s.name == "bonds")
        assert eq.target_weight > bd.target_weight  # high vol demands higher equity

        sleeves_short_horizon = build_whatif_sleeves(
            robert.constraints.strategic_sleeves,
            horizon_years=3,
        )
        eq_short = next(s for s in sleeves_short_horizon if s.name == "equity")
        bd_short = next(s for s in sleeves_short_horizon if s.name == "bonds")
        assert bd_short.target_weight > eq_short.target_weight  # short horizon demands heavy bonds

    def test_diff_table_structure_and_evidence_tags(self) -> None:
        """Test diff table contains required categories, numbers, and evidence tags."""
        b_metrics = {
            "annualized_volatility": 0.1328,
            "max_drawdown": -0.1838,
            "cvar_95": 0.0185,
            "realized_annual_return": 0.1245,
            "beta_vs_benchmark": 0.8521,
            "active_assets_count": 14,
        }
        w_metrics = {
            "annualized_volatility": 0.0823,
            "max_drawdown": -0.1145,
            "cvar_95": 0.0120,
            "realized_annual_return": 0.0910,
            "beta_vs_benchmark": 0.5412,
            "active_assets_count": 12,
        }
        b_stress = {"portfolio": {"max_drawdown": -0.1838, "cumulative_return": -0.1343, "annualized_volatility": 0.1450}}
        w_stress = {"portfolio": {"max_drawdown": -0.0907, "cumulative_return": -0.0520, "annualized_volatility": 0.0890}}
        b_weights = {"NVDA": 0.06, "BTC-USD": 0.05, "GLD": 0.05}
        w_weights = {"NVDA": 0.04, "BTC-USD": 0.02, "GLD": 0.05}
        e_ids = {"opt": "E10", "risk": "E11", "stress": "E12"}

        rows = compute_diff_table(
            b_metrics, w_metrics, b_stress, w_stress, b_weights, w_weights, e_ids
        )
        assert len(rows) >= 7
        for r in rows:
            assert "category" in r
            assert "item" in r
            assert "baseline" in r
            assert "whatif" in r
            assert "diff" in r
            assert "evidence_id" in r
            assert r["evidence_id"] in ("E10", "E11", "E12")

    def test_deterministic_explanation_sentence_count_and_tags(self) -> None:
        """Test explanation is exactly 1-2 deterministic sentences with grounded [E#] tags."""
        params = WhatIfParams(crypto_cap=0.05, single_asset_cap=0.08, target_vol=0.09)
        b_metrics = {"annualized_volatility": 0.1328, "active_assets_count": 14}
        w_metrics = {"annualized_volatility": 0.0823, "active_assets_count": 12}
        b_stress = {"portfolio": {"max_drawdown": -0.1838}}
        w_stress = {"portfolio": {"max_drawdown": -0.0907}}
        e_ids = {"params": "E1", "opt": "E2", "risk": "E3", "stress": "E4"}

        expl = generate_whatif_explanation(params, b_metrics, w_metrics, b_stress, w_stress, e_ids)
        assert isinstance(expl, str)
        # Check sentences count by splitting on period followed by whitespace
        import re
        sentences = [s.strip() for s in re.split(r"\.\s+", expl) if s.strip()]
        assert len(sentences) == 2
        # Check evidence citations
        assert "[E1]" in expl
        assert "[E2]" in expl
        assert "[E3]" in expl
        assert "[E4]" in expl
        # Check specific numbers are present
        assert "8.23%" in expl
        assert "13.28%" in expl
        assert "-9.07%" in expl

    def test_run_whatif_analysis_end_to_end(self) -> None:
        """Test run_whatif_analysis on Robert with EvidenceRegistry."""
        reg = EvidenceRegistry()
        res = run_whatif_analysis(
            persona_or_profile="robert",
            capital=100000.0,
            crypto_cap=0.05,
            single_asset_cap=0.05,
            target_vol=0.07,
            registry=reg,
        )
        assert res.persona_id == "robert"
        assert len(res.whatif_weights) > 0
        assert sum(res.whatif_weights.values()) == pytest.approx(1.0, abs=1e-3)
        assert res.whatif_metrics["annualized_volatility"] > 0.04
        assert len(res.diff_table) > 0
        assert len(res.explanation) > 20
        # Check registered evidence in registry
        assert len(reg.list_all()) >= 4
        assert res.evidence_ids["params"] in reg.to_dict()
        assert res.evidence_ids["opt"] in reg.to_dict()

    def test_compute_2022_stress_curve(self) -> None:
        """Test 2022 stress curve overlay generation for persona comparison."""
        returns_cad, _, _ = get_processed_dataset()
        p_amira = get_persona("amira")
        p_robert = get_persona("robert")

        # Mock simple weights
        w_a = {"NVDA": 0.5, "GLD": 0.5}
        w_b = {"ZST.TO": 0.8, "GLD": 0.2}

        df_curve = compute_2022_stress_curve(
            portfolios={p_amira.name: w_a, p_robert.name: w_b},
            returns_df=returns_cad,
        )
        assert not df_curve.empty
        assert p_amira.name in df_curve.columns
        assert p_robert.name in df_curve.columns
        assert "TSX Composite (XIU.TO)" in df_curve.columns
        assert "Portefeuille 60/40 CAD" in df_curve.columns
        # Returns start around 0
        assert abs(df_curve.iloc[0, 0]) < 0.05

    def test_run_persona_comparison_side_by_side(self) -> None:
        """Test persona comparison between Amira and Robert for TSLA request."""
        comp = run_persona_comparison(
            persona_a_id="amira",
            persona_b_id="robert",
            question="Je souhaite ajouter 15 % d'actions Tesla (TSLA).",
        )
        assert comp["persona_a"].name == "Amira"
        assert comp["persona_b"].name == "Robert"
        assert len(comp["weights_a"]) > 0
        assert len(comp["weights_b"]) > 0
        assert comp["metrics_a"]["annualized_volatility"] > comp["metrics_b"]["annualized_volatility"]

        # Robert has attention/blocking alert for TSLA
        gov_b = comp["gov_b"]
        tsla_alert = any("TSLA" in a.message or "Tesla" in a.message for a in gov_b.alerts)
        assert tsla_alert
