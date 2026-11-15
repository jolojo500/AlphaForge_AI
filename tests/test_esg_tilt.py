"""Tests for ESG tilt as a soft preference (Track A, PRD A-12).

Verifies:
1. Detection FR/EN (soft vs strict).
2. Evidence content: proxy item with date, URL, eligible tickers, methodology limits.
3. Tilt raises esg_proxy_share for capped/baseline vs without tilt.
4. Caps and floors still hold for all personas.
5. Unchanged weights without tilt.
6. Questionnaire path accepts esg_tilt.
7. Full e2e offline run passes the verifier.
"""

from __future__ import annotations

import datetime as dt

import pytest

from alphaforge.graph import run
from alphaforge.nodes.profile import _regex_extract, profile_node
from alphaforge.nodes.scenarios import (
    CAPS,
    EQUITY_CLASSES,
    calculate_esg_proxy_share,
    scenarios_node,
)
from alphaforge.nodes.screening import screening_node
from alphaforge.personas import PERSONAS
from alphaforge.state import SCENARIO_METRICS, SCENARIO_NAMES, GraphState, Profile, effective_risk

AS_OF = dt.date(2026, 11, 12)


# --- 1. Detection tests FR / EN (soft vs strict) ---


@pytest.mark.parametrize(
    "text",
    [
        "Je veux un portefeuille avec un meilleur profil ESG",
        "Je souhaite une allocation plus responsable",
        "Construire un portefeuille plus durable sur 10 ans",
        "Je préfère favoriser l'ESG",
        "Biais ESG souhaité pour mon épargne",
    ],
)
def test_esg_detection_soft_fr(text):
    ext = _regex_extract(text)
    assert "esg_tilt" in ext.extra_preferences
    assert "esg_only" not in ext.extra_constraints

    p = profile_node(GraphState(as_of_date=AS_OF, persona="amira", request_text=text))["profile"]
    assert "esg_tilt" in p.preferences
    assert "esg_only" not in p.constraints


@pytest.mark.parametrize(
    "text",
    [
        "I want a portfolio with better ESG",
        "Build a more responsible portfolio over 10 years",
        "I want a more sustainable allocation",
        "Prefer ESG tilt for my retirement",
        "Favour ESG investments in my portfolio",
    ],
)
def test_esg_detection_soft_en(text):
    ext = _regex_extract(text)
    assert "esg_tilt" in ext.extra_preferences
    assert "esg_only" not in ext.extra_constraints

    p = profile_node(GraphState(as_of_date=AS_OF, persona="amira", request_text=text, language="en"))["profile"]
    assert "esg_tilt" in p.preferences
    assert "esg_only" not in p.constraints


@pytest.mark.parametrize(
    "text",
    [
        "Je veux un portefeuille sans énergies fossiles",
        "Allocation uniquement ESG",
        "Exclure les titres pétroliers et non-ESG",
        "Portefeuille strictement ESG",
    ],
)
def test_esg_detection_strict_fr(text):
    ext = _regex_extract(text)
    assert "esg_only" in ext.extra_constraints
    assert "esg_tilt" not in ext.extra_preferences

    p = profile_node(GraphState(as_of_date=AS_OF, persona="amira", request_text=text))["profile"]
    assert "esg_only" in p.constraints
    assert "esg_tilt" not in p.preferences


@pytest.mark.parametrize(
    "text",
    [
        "I want a fossil-free portfolio",
        "Only ESG assets allowed",
        "Exclude non-ESG and fossil fuel companies",
        "Strictly ESG allocation",
    ],
)
def test_esg_detection_strict_en(text):
    ext = _regex_extract(text)
    assert "esg_only" in ext.extra_constraints
    assert "esg_tilt" not in ext.extra_preferences

    p = profile_node(GraphState(as_of_date=AS_OF, persona="amira", request_text=text, language="en"))["profile"]
    assert "esg_only" in p.constraints
    assert "esg_tilt" not in p.preferences


def test_questionnaire_path_accepts_esg_tilt():
    persona_data = {
        "objective": "growth",
        "horizon_years": 10,
        "risk_tolerance": "high",
        "risk_capacity": "high",
        "preferences": ["esg_tilt", "likes_tech"],
    }
    state = GraphState(
        as_of_date=AS_OF,
        persona="custom",
        persona_data=persona_data,
        request_text="Construire une allocation diversifiée",
    )
    res = profile_node(state)
    p = res["profile"]
    assert "esg_tilt" in p.preferences
    assert "likes_tech" in p.preferences


# --- 2. Evidence content tests ---


def test_esg_tilt_evidence_content():
    """Verify evidence item prefix EP, confidence assumption, date, URL, proxy tickers, limits."""
    state = GraphState(as_of_date=AS_OF, persona="amira", request_text="Construire une allocation avec un meilleur profil ESG")
    state = state.model_copy(update=profile_node(state))
    state = state.model_copy(update=screening_node(state))
    res = scenarios_node(state)

    ev_dict = res["evidence"]
    # Check proxy assumption evidence item
    proxy_items = [
        ev for ev in ev_dict.values()
        if ev.id.startswith("EP") and "Proxy ESG" in str(ev.value)
    ]
    assert len(proxy_items) == 1, "Expected exactly one proxy assumption evidence item"
    proxy_ev = proxy_items[0]
    assert proxy_ev.confidence == "assumption"
    assert proxy_ev.source == "Vanguard ESGV holdings"
    assert proxy_ev.url == "https://investor.vanguard.com/investment-products/etfs/profile/esgv"
    assert "2026-09-30" in str(proxy_ev.value)
    # Check limits stated in text
    val_str = str(proxy_ev.value)
    assert "actions américaines uniquement" in val_str
    assert "score" in val_str
    assert "canadiennes" in val_str

    # Check scenario metric evidence items for all three scenarios
    scenarios = res["scenarios"]
    assert len(scenarios) == 3
    for sc in scenarios:
        assert "esg_proxy_share" in sc.metrics
        metric_eid = sc.metrics["esg_proxy_share"]
        assert metric_eid in ev_dict
        m_ev = ev_dict[metric_eid]
        assert m_ev.confidence == "assumption"
        assert m_ev.value["metric"] == "esg_proxy_share"
        assert m_ev.value["unit"] == "ratio"
        assert m_ev.value["scenario"] == sc.name
        assert 0.0 <= m_ev.value["value"] <= 1.0


# --- 3. Tilt effect: raises esg_proxy_share ---


@pytest.mark.parametrize("persona", ["amira", "mateo", "robert"])
def test_esg_tilt_raises_esg_proxy_share_for_capped_and_baseline(persona):
    """Verify tilt raises esg_proxy_share for capped & baseline vs same request without tilt."""
    req_base = PERSONAS[persona]["example_request"]
    # Run without tilt
    s_without = run(persona, req_base)
    by_name_without = {sc.name: sc for sc in s_without.scenarios}

    # Run with tilt
    p_tilt = s_without.profile.model_copy(
        update={"preferences": list(s_without.profile.preferences) + ["esg_tilt"]}
    )
    st = GraphState(as_of_date=AS_OF, persona=persona, request_text=req_base, profile=p_tilt)
    st = st.model_copy(update=screening_node(st))
    res_tilt = scenarios_node(st)
    by_name_tilt = {sc.name: sc for sc in res_tilt["scenarios"]}

    # esg_proxy_share in capped and baseline must be strictly greater with tilt
    esg_capped_without = calculate_esg_proxy_share(by_name_without["capped"].weights)
    esg_capped_with = calculate_esg_proxy_share(by_name_tilt["capped"].weights)
    assert esg_capped_with > esg_capped_without, (
        f"{persona} capped: with_tilt ({esg_capped_with:.2%}) should be > without ({esg_capped_without:.2%})"
    )

    esg_base_without = calculate_esg_proxy_share(by_name_without["profile_baseline"].weights)
    esg_base_with = calculate_esg_proxy_share(by_name_tilt["profile_baseline"].weights)
    assert esg_base_with > esg_base_without, (
        f"{persona} baseline: with_tilt ({esg_base_with:.2%}) should be > without ({esg_base_without:.2%})"
    )

    # as_requested must be bit-for-bit unchanged
    assert by_name_tilt["as_requested"].weights == by_name_without["as_requested"].weights


# --- 4. Caps and floors hold for all personas with tilt ---


@pytest.mark.parametrize("persona", ["amira", "mateo", "robert"])
def test_caps_and_floors_hold_with_esg_tilt(persona):
    p_base = PERSONAS[persona]
    req = p_base["example_request"]
    p_tilt = Profile(
        persona=persona,
        objective=p_base["objective"],
        horizon_years=p_base["horizon_years"],
        risk_tolerance=p_base["risk_tolerance"],
        risk_capacity=p_base["risk_capacity"],
        constraints=list(p_base.get("constraints", [])),
        preferences=list(p_base.get("preferences", [])) + ["esg_tilt"],
        account_type=p_base.get("account_type", "non_registered"),
    )
    st = GraphState(as_of_date=AS_OF, persona=persona, request_text=req, profile=p_tilt)
    st = st.model_copy(update=screening_node(st))
    res = scenarios_node(st)

    effective_lvl = effective_risk(p_tilt.risk_tolerance, p_tilt.risk_capacity)
    caps = CAPS[effective_lvl]
    from alphaforge.data.provider import get_provider

    info = get_provider().asset_info()

    for sc in res["scenarios"]:
        w = sc.weights
        assert sum(w.values()) == pytest.approx(1.0, abs=1e-5)
        assert all(v >= 0 for v in w.values())

        if sc.name in ("capped", "profile_baseline"):
            # Single-stock caps
            for ticker, weight in w.items():
                cls = info.at[ticker, "asset_class"]
                if cls == "equity":
                    assert weight <= caps["single_stock"] + 1e-5, f"{ticker} exceeds single_stock cap"
                elif cls == "crypto":
                    assert weight <= caps["crypto_total"] + 1e-5
                else:
                    assert weight <= caps["etf"] + 1e-5

            # Equity bounds
            eq_weight = sum(w.get(t, 0.0) for t in w if info.at[t, "asset_class"] in EQUITY_CLASSES)
            assert eq_weight <= caps["equity_max"] + 1e-5
            if sc.name == "profile_baseline":
                assert eq_weight >= caps["equity_min"] - 1e-5


# --- 5. Unchanged weights without esg_tilt ---


def test_unchanged_weights_without_esg_tilt():
    """Verify bit-for-bit unchanged weights and metrics when esg_tilt is inactive."""
    for persona in ("amira", "mateo", "robert"):
        s = run(persona, PERSONAS[persona]["example_request"])
        for sc in s.scenarios:
            assert "esg_proxy_share" not in sc.metrics
            assert set(sc.metrics) == set(SCENARIO_METRICS)


# --- 6. Full end-to-end run passes verifier ---


def test_e2e_offline_run_passes_verifier():
    """Verify complete end-to-end run with esg_tilt passes the verifier without errors."""
    req = "Je veux un portefeuille diversifié avec un meilleur profil ESG"
    s = run("amira", req)

    assert "esg_tilt" in s.profile.preferences
    assert s.verification is not None
    assert s.verification["passed"] is True, f"Verifier failed with errors: {s.verification.get('errors')}"
    assert not s.verification["errors"]

    # Check explanation contents
    exp = s.explanation
    assert exp is not None
    assert exp["scenario_le_plus_coherent"] in SCENARIO_NAMES

    # Check that donnees mentions esg proxy share with its evidence id
    donnees_claims = [c for c in exp["quelles_donnees"] if "fonds ESGV" in c["claim"]]
    assert len(donnees_claims) >= 1
    assert any(c["evidence"] for c in donnees_claims)

    # Check that limites states the proxy limit in one sentence
    limites_claims = [c for c in exp["limites"] if "fonds ESGV" in c["claim"]]
    assert len(limites_claims) >= 1
