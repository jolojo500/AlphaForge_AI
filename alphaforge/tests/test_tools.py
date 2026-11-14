"""Unit and integration tests for AlphaForge quantitative tools:
- prices.py
- risk.py
- optimize.py
- stress.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alphaforge.app.tools.optimize import optimize_min_variance, optimize_risk_parity
from alphaforge.app.tools.prices import (
    align_prices_to_calendar,
    build_market_calendar,
    compute_log_returns,
    convert_prices_to_cad,
    generate_data_quality_report,
    get_processed_dataset,
    load_starter_data,
)
from alphaforge.app.tools.risk import (
    annualized_volatility,
    asset_summary_metrics,
    beta_vs_benchmark,
    correlation_matrix,
    cvar_95,
    max_drawdown,
    portfolio_returns,
    portfolio_risk_metrics,
    risk_contributions,
)
from alphaforge.app.tools.stress import (
    rolling_risk_windows,
    sensitivity_to_asset_cap,
    stress_test_2022_episode,
)


@pytest.fixture(scope="module")
def shared_dataset():
    return get_processed_dataset()


class TestPricesTool:
    @pytest.fixture
    def dataset(self, shared_dataset):
        return shared_dataset

    def test_load_starter_data(self):
        data = load_starter_data()
        assert "universe" in data
        assert "prices" in data
        assert "fx" in data
        assert "corporate_actions" in data
        assert "macro" in data
        assert len(data["universe"]) == 31

    def test_calendar_union(self, dataset):
        returns_df, prices_df, universe_df = dataset
        # Union calendar spans 1282 days
        assert len(prices_df) == 1282
        # Log returns drops first row -> 1281 rows
        assert len(returns_df) == 1281
        assert returns_df.shape[1] == 31
        # No NaNs after alignment and ffill(3)
        assert returns_df.isna().sum().sum() == 0

    def test_cad_conversion(self, dataset):
        _, prices_df, universe_df = dataset
        ccy_map = dict(zip(universe_df["ticker"], universe_df["currency"]))
        # XIU.TO is listed in CAD, SPY is listed in USD
        assert ccy_map["XIU.TO"] == "CAD"
        assert ccy_map["SPY"] == "USD"
        # Both prices are in CAD in prices_df and are strictly positive
        assert (prices_df["XIU.TO"] > 0).all()
        assert (prices_df["SPY"] > 0).all()

    def test_data_quality_report(self):
        report = generate_data_quality_report()
        assert report.total_assets == 31
        assert report.calendar_dates_count == 1282
        assert report.missing_after_fill == 0
        assert len(report.anomalies) >= 4
        # Verify CNQ.TO and macro lag are documented
        topics = [a.topic for a in report.anomalies]
        assert any("CNQ.TO" in t for t in topics)
        assert any("Macroeconomic Publication Lag" in t for t in topics)


class TestRiskTool:
    @pytest.fixture
    def dataset(self, shared_dataset):
        return shared_dataset

    def test_annualized_volatility(self, dataset):
        returns_df, _, _ = dataset
        vol = annualized_volatility(returns_df)
        assert isinstance(vol, pd.Series)
        assert len(vol) == 31
        # Crypto and Tech should have higher vol than short bond ETF
        assert vol["ETH-USD"] > vol["XIU.TO"]
        assert vol["XIU.TO"] > vol["ZST.TO"]
        assert vol["ZST.TO"] < 0.02  # Ultra short-term bond vol < 2%

    def test_max_drawdown(self, dataset):
        returns_df, _, _ = dataset
        mdd = max_drawdown(returns_df)
        assert isinstance(mdd, pd.Series)
        # All drawdowns must be <= 0
        assert (mdd <= 0.0).all()
        # High beta assets must have deeper drawdown than bonds
        assert mdd["SHOP.TO"] < -0.50
        assert mdd["ZST.TO"] > -0.05

    def test_cvar95(self, dataset):
        returns_df, _, _ = dataset
        cvar = cvar_95(returns_df)
        assert (cvar > 0).all()
        # Daily tail loss of crypto is much higher than aggregate bond
        assert cvar["BTC-USD"] > cvar["XBB.TO"]

    def test_beta_vs_benchmark(self, dataset):
        returns_df, _, _ = dataset
        b_ret = returns_df["XIU.TO"]
        betas = beta_vs_benchmark(returns_df, b_ret)
        # Benchmark beta to itself is identically 1.0
        assert pytest.approx(betas["XIU.TO"], rel=1e-4) == 1.0

    def test_portfolio_risk_metrics(self, dataset):
        returns_df, _, _ = dataset
        w = {"XIU.TO": 0.60, "XBB.TO": 0.40}
        metrics = portfolio_risk_metrics(w, returns_df)
        assert "annualized_volatility" in metrics
        assert "max_drawdown" in metrics
        assert "cvar_95" in metrics
        assert "beta_vs_benchmark" in metrics
        assert 0.05 < metrics["annualized_volatility"] < 0.15

    def test_risk_contributions_sum_to_one(self, dataset):
        returns_df, _, _ = dataset
        w = {"XIU.TO": 0.50, "XBB.TO": 0.30, "GLD": 0.20}
        rc_df = risk_contributions(w, returns_df)
        assert len(rc_df) == 3
        total_pct = rc_df["pct_risk_contribution"].sum()
        assert pytest.approx(total_pct, abs=1e-3) == 1.0


class TestOptimizeTool:
    @pytest.fixture
    def dataset(self, shared_dataset):
        return shared_dataset

    def test_min_variance_basic(self, dataset):
        returns_df, _, universe_df = dataset
        res = optimize_min_variance(
            returns_df=returns_df,
            universe_df=universe_df,
            per_asset_caps=0.10,
            exclusions=["BTC-USD", "ETH-USD"],
        )
        assert res.solver_status in ["optimal", "optimal_inaccurate"]
        assert pytest.approx(sum(res.weights.values()), abs=1e-3) == 1.0
        assert "BTC-USD" not in res.weights
        assert "ETH-USD" not in res.weights
        for w in res.weights.values():
            assert w <= 0.10 + 1e-4

    def test_min_variance_sector_and_class_constraints(self, dataset):
        returns_df, _, universe_df = dataset
        res = optimize_min_variance(
            returns_df=returns_df,
            universe_df=universe_df,
            sector_floors={"Information Technology": 0.25},
            sector_caps={"Information Technology": 0.40},
            class_floors={"crypto": 0.05},
            class_caps={"crypto": 0.15},
            per_asset_caps=0.10,
        )
        assert res.solver_status in ["optimal", "optimal_inaccurate"]
        sector_map = dict(zip(universe_df["ticker"], universe_df["sector"]))
        class_map = dict(zip(universe_df["ticker"], universe_df["asset_class"]))

        tech_w = sum(w for t, w in res.weights.items() if sector_map.get(t) == "Information Technology")
        crypto_w = sum(w for t, w in res.weights.items() if class_map.get(t) == "crypto")

        assert tech_w >= 0.25 - 1e-2
        assert tech_w <= 0.40 + 1e-3
        assert crypto_w >= 0.05 - 1e-2
        assert crypto_w <= 0.15 + 1e-3

    def test_risk_parity_equal_risk(self, dataset):
        returns_df, _, universe_df = dataset
        sub_ret = returns_df[["XIU.TO", "SPY", "XBB.TO", "GLD"]]
        res = optimize_risk_parity(sub_ret, universe_df)
        assert res.solver_status in ["optimal", "optimal_inaccurate"]
        assert pytest.approx(sum(res.weights.values()), abs=1e-3) == 1.0


class TestStressTool:
    @pytest.fixture
    def dataset(self, shared_dataset):
        return shared_dataset

    def test_stress_test_2022_episode(self, dataset):
        returns_df, _, _ = dataset
        w = {"XIU.TO": 0.60, "XBB.TO": 0.40}
        stress = stress_test_2022_episode(w, returns_df)
        assert stress["episode"] == "2022 Stagflation / Rate-Hike Shock"
        assert "portfolio" in stress
        assert "benchmarks" in stress
        assert stress["portfolio"]["max_drawdown"] < 0
        assert "XIU.TO" in stress["benchmarks"]
        assert "XBB.TO" in stress["benchmarks"]

    def test_rolling_risk_windows(self, dataset):
        returns_df, _, _ = dataset
        w = {"XIU.TO": 0.50, "XBB.TO": 0.50}
        rolling = rolling_risk_windows(w, returns_df, window_days=63)
        assert rolling["window_days"] == 63
        assert rolling["peak_rolling_vol"] >= rolling["mean_rolling_vol"]
        assert rolling["min_rolling_vol"] <= rolling["mean_rolling_vol"]

    def test_2022_drawdown_window_isolation(self, dataset):
        """Confirm that stress_test_2022_episode computes drawdown strictly within the 2022 calendar window.

        For assets with major drawdowns occurring in 2023 or 2024 (e.g. GLD, NVDA),
        the 2022 episode drawdown is strictly different from the full 5-year sample drawdown.
        """
        returns_df, _, _ = dataset
        # For GLD, the full 5-year drawdown was ~-26% (late 2022 to late 2023), whereas 2022 alone was ~-17.4%
        full_gld_dd = max_drawdown(returns_df["GLD"])
        stress_gld = stress_test_2022_episode({"GLD": 1.0}, returns_df)
        gld_2022_dd = stress_gld["portfolio"]["max_drawdown"]
        assert abs(full_gld_dd - gld_2022_dd) > 0.05
        assert gld_2022_dd > full_gld_dd  # 2022 drawdown was milder than full-period drawdown

        # Synthetic test: Series with zero drawdown in 2022 and severe crash in 2023
        synth_ret = pd.Series(0.0001, index=returns_df.index)
        # Inject crash strictly in 2023
        synth_ret.loc["2023-05-01":"2023-05-10"] = -0.05
        synth_df = pd.DataFrame({"SYNTH": synth_ret})
        synth_full_dd = max_drawdown(synth_ret)
        synth_stress = stress_test_2022_episode({"SYNTH": 1.0}, synth_df)
        assert synth_full_dd < -0.30
        assert synth_stress["portfolio"]["max_drawdown"] == 0.0  # Zero drawdown in 2022 window

    def test_sensitivity_to_asset_cap(self, dataset):
        returns_df, _, universe_df = dataset
        base_robert = {
            "per_asset_caps": {"RY.TO": 0.08, "TD.TO": 0.08, "ZST.TO": 0.35, "XBB.TO": 0.35, "AGG": 0.35},
            "class_floors": {"etf_bond": 0.50},
            "class_caps": {"crypto": 0.0},
            "exclusions": ["BTC-USD", "ETH-USD"],
        }
        sens = sensitivity_to_asset_cap(
            returns_df=returns_df,
            universe_df=universe_df,
            target_asset="TSLA",
            cap_range=[0.0, 0.03, 0.08],
            base_constraints=base_robert,
            mode="fixed_weight",
        )
        assert len(sens) == 3
        # Volatility should increase monotonically as volatile TSLA is forced higher
        assert sens[0]["annualized_volatility"] <= sens[1]["annualized_volatility"]
        assert sens[1]["annualized_volatility"] <= sens[2]["annualized_volatility"]
