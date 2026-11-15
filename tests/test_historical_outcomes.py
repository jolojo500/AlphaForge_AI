import datetime as dt

import numpy as np
import pandas as pd

from alphaforge.nodes.quant import rolling_returns_stats
from alphaforge.nodes.scenarios import scenarios_node
from alphaforge.nodes.verifier import check_wording
from alphaforge.state import GraphState, Profile


def test_rolling_returns_stats_calculation():
    # 500 trading days
    dates = pd.date_range("2022-01-01", periods=500, freq="B")
    # Steady upward drift
    prices = pd.DataFrame({"A": np.linspace(100.0, 150.0, 500)}, index=dates)

    # 1-year window (252 days)
    stats = rolling_returns_stats(prices, "A", window_years=1, trading_days_per_year=252)
    assert stats is not None
    assert stats["window_years"] == 1
    assert stats["windows_count"] == 500 - 252
    assert stats["worst"] > 0.0  # all positive in steady uptrend
    assert stats["median"] > 0.0
    assert stats["best"] >= stats["worst"]
    assert stats["loss_share"] == 0.0


def test_rolling_returns_stats_insufficient_history():
    dates = pd.date_range("2024-01-01", periods=100, freq="B")
    prices = pd.DataFrame({"A": np.linspace(100.0, 110.0, 100)}, index=dates)
    # 100 days is shorter than 252 days
    assert rolling_returns_stats(prices, "A", window_years=1, trading_days_per_year=252) is None


def test_verifier_allow_list_for_historique_pas_une_prevision():
    # The required label is allowed
    explanation_clean = {
        "resume": "Rendement historique sur 1 an : pire -12 %, médiane +8 % (historique, pas une prévision).",
        "incertitude": "Les résultats passés ne constituent pas une prévision.",
        "quelles_donnees": [{"claim": "Perte maximale observée de 15,2 %.", "evidence": ["EQ1"]}],
        "pourquoi_ce_choix": [{"claim": "Moindre variance constatée.", "evidence": ["EQ1"]}],
        "limites": [{"claim": "Historique, pas de prévision.", "evidence": []}],
        "ce_qui_changerait_la_reponse": [{"claim": "Un changement de données.", "evidence": []}],
        "scenario_le_plus_coherent": "capped",
        "avertissement": "Simulation éducative.",
    }
    assert check_wording(explanation_clean) == []

    # Un-negated forecast wording is strictly blocked
    explanation_forecast = {
        "resume": "Nos prévisions indiquent une surperformance certaine.",
        "incertitude": "Incertitude minimale.",
        "quelles_donnees": [{"claim": "Preuve", "evidence": ["EQ1"]}],
        "pourquoi_ce_choix": [{"claim": "Choix", "evidence": ["EQ1"]}],
        "limites": [],
        "ce_qui_changerait_la_reponse": [],
        "scenario_le_plus_coherent": "capped",
        "avertissement": "Simulation éducative.",
    }
    errors = check_wording(explanation_forecast)
    assert any("prévision" in err or "surperformance" in err for err in errors)


def test_scenarios_node_includes_historical_outcomes():
    profile = Profile(
        persona="amira",
        objective="growth",
        horizon_years=15,  # Horizon > 3 years: should trigger note that longer horizon is not covered
        risk_tolerance="high",
        risk_capacity="high",
    )
    state = GraphState(
        as_of_date=dt.date(2026, 11, 15),
        persona="amira",
        profile=profile,
        eligible_universe=["SPY", "QQQ", "XIU.TO", "ZST.TO"],
    )

    out = scenarios_node(state)
    scenarios = out["scenarios"]
    assert len(scenarios) == 3

    for sc in scenarios:
        assert sc.historical_outcomes is not None
        assert "1y" in sc.historical_outcomes
        assert "3y" in sc.historical_outcomes
        assert sc.historical_outcomes["horizon_covered"] is False  # 15 years > 3 years
        assert sc.historical_outcomes["disclaimer"] == "historique, pas une prévision"

        # Check notes mention the label and limitation
        notes_str = " ".join(sc.notes)
        assert "historique, pas une prévision" in notes_str
        assert "n'est pas couvert" in notes_str or "pas couvert" in notes_str
