"""Unit tests for user profile persistence (PRD C-14, #128)."""

from __future__ import annotations

from decimal import Decimal

from alphaforge.personas import PERSONAS
from alphaforge.users import (
    LocalUserStore,
    _from_dynamodb_friendly,
    _to_dynamodb_friendly,
)


def test_dynamodb_friendly_conversion():
    data = {"num": 42.5, "nested": {"val": 10.0, "int": 5}, "list": [1.2, 3.4]}
    converted = _to_dynamodb_friendly(data)
    assert isinstance(converted["num"], Decimal)
    assert isinstance(converted["nested"]["val"], Decimal)

    restored = _from_dynamodb_friendly(converted)
    assert restored["num"] == 42.5
    assert restored["nested"]["val"] == 10.0
    assert restored["nested"]["int"] == 5


def test_local_user_store_seeded_personas():
    store = LocalUserStore()
    for persona_name in ("amira", "mateo", "robert"):
        user = store.get_user_profile(persona_name)
        assert user is not None
        assert user["username"] == persona_name
        assert user["profile"]["objective"] == PERSONAS[persona_name]["objective"]


def test_local_user_store_save_and_retrieve():
    store = LocalUserStore()
    profile = {
        "objective": "growth",
        "horizon_years": 20,
        "risk_tolerance": "high",
        "risk_capacity": "high",
    }
    saved = store.save_user_profile(
        user_id="user-999",
        profile=profile,
        account_type="CELI",
        username="john_doe",
        email="john@example.com",
    )
    assert saved["user_id"] == "user-999"
    assert saved["account_type"] == "CELI"

    retrieved = store.get_user_profile("user-999")
    assert retrieved is not None
    assert retrieved["profile"]["horizon_years"] == 20

    # Also lookup by username
    retrieved_by_name = store.get_user_profile("john_doe")
    assert retrieved_by_name is not None
    assert retrieved_by_name["user_id"] == "user-999"
