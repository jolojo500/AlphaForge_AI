"""Tests for Canadian account types, tax drag, and asset location (Issue #118 / PRD)."""

import datetime as dt

import pandas as pd
import pytest

from alphaforge.data.provider import get_provider
from alphaforge.nodes.profile import Extraction, build_profile
from alphaforge.nodes.scenarios import scenario_metrics, scenarios_node
from alphaforge.state import GraphState, Profile
from alphaforge.tax import (
    CANADIAN_ELIGIBLE_DIVIDEND_NET_RATE,
    FEDERAL_MIDDLE_RATE,
    US_WITHHOLDING_RATE,
    asset_tax_rate,
    scenario_tax_drag,
    tax_rules_evidence,
    trailing_yields,
)
from alphaforge.whatif import apply_change

AS_OF = dt.date(2026, 11, 12)


def test_sourced_tax_constants_and_urls():
    """Verify that every tax rate is sourced with a valid government URL and non-invented number."""
    rules = tax_rules_evidence(AS_OF, "non_registered")
    assert len(rules) == 3
    for r in rules:
        assert r["confidence"] == "assumption"
        assert r["url"].startswith("https://www.canada.ca/")
        assert r["source"]
        assert r["method"]

    # Verify rates
    assert US_WITHHOLDING_RATE == 0.15
    assert FEDERAL_MIDDLE_RATE == 0.205
    assert CANADIAN_ELIGIBLE_DIVIDEND_NET_RATE == pytest.approx(0.0756, abs=1e-4)


def test_trailing_dividend_yields():
    """Test that trailing dividend yields are calculated from corporate_actions.csv."""
    yields = trailing_yields(AS_OF)
    assert len(yields) == 31
    # ENB.TO pays a high dividend
    assert yields["ENB.TO"] > 0.04
    # XIU.TO and SPY pay dividends
    assert yields["XIU.TO"] > 0.015
    assert yields["SPY"] > 0.005
    # TSLA, GLD, BTC-USD have no dividends
    assert yields["TSLA"] == 0.0
    assert yields["GLD"] == 0.0
    assert yields["BTC-USD"] == 0.0


def test_asset_tax_rate_per_account():
    """Test tax rates for different asset types across accounts."""
    info = get_provider().asset_info()

    # RRSP: 0 tax on all assets
    assert asset_tax_rate("XIU.TO", "rrsp", info) == 0.0
    assert asset_tax_rate("SPY", "rrsp", info) == 0.0
    assert asset_tax_rate("XBB.TO", "rrsp", info) == 0.0
    assert asset_tax_rate("AGG", "rrsp", info) == 0.0

    # TFSA / FHSA: 0 on Canadian, 15% on US dividends
    assert asset_tax_rate("XIU.TO", "tfsa", info) == 0.0
    assert asset_tax_rate("XBB.TO", "tfsa", info) == 0.0
    assert asset_tax_rate("SPY", "tfsa", info) == 0.15
    assert asset_tax_rate("AAPL", "tfsa", info) == 0.15
    assert asset_tax_rate("SPY", "fhsa", info) == 0.15

    # Non-registered: 7.56% on Canadian dividend, 20.5% on interest and US dividends
    assert asset_tax_rate("XIU.TO", "non_registered", info) == pytest.approx(0.0756, abs=1e-4)
    assert asset_tax_rate("RY.TO", "non_registered", info) == pytest.approx(0.0756, abs=1e-4)
    assert asset_tax_rate("XBB.TO", "non_registered", info) == 0.205
    assert asset_tax_rate("SPY", "non_registered", info) == 0.205
    assert asset_tax_rate("AGG", "non_registered", info) == 0.205

    # Mixed (asset location): bonds and US equity in RRSP (0%), Canadian equity in taxable (7.56%)
    assert asset_tax_rate("XIU.TO", "mixed", info) == pytest.approx(0.0756, abs=1e-4)
    assert asset_tax_rate("SPY", "mixed", info) == 0.0
    assert asset_tax_rate("XBB.TO", "mixed", info) == 0.0
    assert asset_tax_rate("AGG", "mixed", info) == 0.0


def test_scenario_tax_drag_values():
    """Verify calculated scenario tax drag for different account types."""
    info = get_provider().asset_info()
    prices = get_provider().prices_cad(["XIU.TO", "SPY", "XBB.TO"], AS_OF)
    w = pd.Series({"XIU.TO": 0.5, "SPY": 0.3, "XBB.TO": 0.2})

    # In RRSP: drag must be 0
    drag_rrsp = scenario_tax_drag(w, "rrsp", AS_OF, info)
    assert drag_rrsp == 0.0

    # In TFSA: drag is only from US dividend withholding
    drag_tfsa = scenario_tax_drag(w, "tfsa", AS_OF, info)
    assert drag_tfsa > 0.0

    # In non-registered: drag includes Canadian dividend tax + bond interest tax + US dividend tax
    drag_nonreg = scenario_tax_drag(w, "non_registered", AS_OF, info)
    assert drag_nonreg > drag_tfsa

    # In mixed: drag is lower than non-registered because US and bonds are in RRSP
    drag_mixed = scenario_tax_drag(w, "mixed", AS_OF, info)
    assert 0.0 < drag_mixed < drag_nonreg

    # Check metrics dict
    metrics = scenario_metrics(w, prices, info, account_type="tfsa", as_of=AS_OF)
    assert "tax_drag" in metrics
    assert metrics["tax_drag"] == drag_tfsa


def test_mixed_account_asset_location_note_in_scenarios():
    """Verify that scenarios_node includes asset-location note for mixed accounts."""
    p = Profile(
        persona="mateo",
        objective="balanced",
        horizon_years=10,
        risk_tolerance="moderate",
        risk_capacity="moderate",
        account_type="mixed",
        preferences=["wants_balance"],
    )
    u = sorted(get_provider().universe()["ticker"])
    state = GraphState(as_of_date=AS_OF, persona="mateo", profile=p, eligible_universe=u)
    out = scenarios_node(state)

    for sc in out["scenarios"]:
        assert any("asset location" in n.lower() or "localisation" in n.lower() for n in sc.notes)
        assert "tax_drag" in sc.metrics
        eid = sc.metrics["tax_drag"]
        ev = out["evidence"][eid]
        assert ev.confidence == "assumption"
        assert ev.url is not None


def test_profile_account_type_extraction_and_whatif():
    """Verify account_type on Profile, in build_profile, and in What-If."""
    ext = Extraction(account_type="tfsa")
    p = build_profile("amira", ext, False)
    assert p.account_type == "tfsa"

    # What-If change account_type
    p2 = apply_change(p, "account_type", "rrsp")
    assert p2.account_type == "rrsp"

    with pytest.raises(ValueError):
        apply_change(p, "account_type", "invalid_type")


def test_tfsa_room_limits_and_age_band():
    """Issue #169: TFSA room calculation for age bands and budget excess check."""
    from alphaforge.tax import (
        tfsa_room_check,
        tfsa_room_evidence,
        tfsa_room_for_age,
        tfsa_room_for_band,
        tfsa_room_sentences,
    )

    # Age 29 in 2026: turned 18 in 2015 -> 78 000 $
    assert tfsa_room_for_age(29, 2026) == 78000
    assert tfsa_room_for_band("18-29", 2026) == 78000
    assert tfsa_room_for_band("18–29 ans", 2026) == 78000

    # Under 18 has 0 room
    assert tfsa_room_for_age(17, 2026) == 0

    # 100 000 $ budget in 18-29 band exceeds 78 000 $ by 22 000 $
    check = tfsa_room_check("tfsa", 100_000.0, "18-29")
    assert check is not None
    assert check["room"] == 78000.0
    assert check["budget"] == 100000.0
    assert check["excess"] == 22000.0
    assert check["age_band"] == "18-29"

    # Within room -> None
    assert tfsa_room_check("tfsa", 70_000.0, "18-29") is None

    # Non-registered -> None
    assert tfsa_room_check("non_registered", 100_000.0, "18-29") is None

    # Sourced assumption evidence
    ev = tfsa_room_evidence(check, AS_OF)
    assert ev["confidence"] == "assumption"
    assert ev["url"].startswith("https://www.canada.ca/")
    assert ev["value"]["metric"] == "tfsa_room"
    assert ev["value"]["room_cad"] == 78000.0

    fr, en = tfsa_room_sentences(check)
    assert "100 000 $" in fr and "78 000 $" in fr and "22 000 $" in fr
    assert "$100,000" in en and "$78,000" in en and "$22,000" in en


def test_tfsa_room_evidence_states_the_birthday_assumption():
    """#186 item 4: year - age + 18 assumes the birthday has passed; the EK evidence says so."""
    from alphaforge.tax import (
        TFSA_ROOM_ASSUMPTION_FR,
        tfsa_room_check,
        tfsa_room_evidence,
        tfsa_room_for_age,
    )

    assert tfsa_room_for_age(29, 2026) == 78000  # band 18-29 keeps 78 000 $
    assert "anniversaire" in TFSA_ROOM_ASSUMPTION_FR
    ev = tfsa_room_evidence(tfsa_room_check("tfsa", 100_000.0, "18-29"), AS_OF)
    assert "anniversaire" in ev["method"]
    assert ev["value"]["assumption"] == TFSA_ROOM_ASSUMPTION_FR
    assert "birthday" in (tfsa_room_for_age.__doc__ or "")


@pytest.mark.parametrize(
    "holdings, vehicle, expected",
    [
        ({"BTCC.B.TO": 0.3}, None, {"BTC-USD": ["BTCC.B.TO"]}),
        ({"IBIT": 1000, "ETHH.TO": 500, "AAPL": 200}, None, {"BTC-USD": ["IBIT"], "ETH-USD": ["ETHH.TO"]}),
        ({"btcc.b": 0.3}, None, {"BTC-USD": ["BTCC.B"]}),
        (None, "BTCC.B", {"BTC-USD": ["BTCC.B"]}),
        ({"BTC-USD": 0.3, "BTC": 0.1}, None, {}),  # spot, not a vehicle
        ({"VCN.TO": 0.5}, "VCN.TO", {}),  # a proxy that is not crypto
        (None, None, {}),
    ],
)
def test_listed_crypto_vehicles(holdings, vehicle, expected):
    """#186 item 2: crypto held or asked for through a listed ETF, keyed by its spot proxy."""
    from alphaforge.tax import listed_crypto_vehicles

    assert listed_crypto_vehicles(holdings, vehicle) == expected
