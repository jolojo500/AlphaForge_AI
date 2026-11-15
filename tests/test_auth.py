"""Unit tests for authentication and Cognito JWT verification (PRD C-14, #128)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from alphaforge.auth import (
    User,
    authenticate_user,
    create_dev_token,
    is_auth_enabled,
    require_advisor,
    verify_token,
)


def test_auth_mode_disabled_in_tests():
    # In tests, is_auth_enabled() should default to False (no external AWS calls)
    assert not is_auth_enabled()


def test_dev_token_creation_and_verification():
    user = User(
        user_id="test-123",
        username="tester",
        email="tester@alphaforge.demo",
        groups=["advisor"],
    )
    token = create_dev_token(user)
    assert token is not None

    verified = verify_token(token)
    assert verified.user_id == "test-123"
    assert verified.username == "tester"
    assert verified.email == "tester@alphaforge.demo"
    assert verified.is_advisor is True


def test_verify_empty_or_invalid_token():
    with pytest.raises(HTTPException) as exc:
        verify_token("")
    assert exc.value.status_code == 401

    with pytest.raises(HTTPException) as exc2:
        verify_token("invalid.token.here")
    assert exc2.value.status_code == 401


def test_authenticate_user_dev_mode():
    res = authenticate_user("amira", "AlphaForge2026!")
    assert "access_token" in res
    assert "user" in res
    assert res["user"]["username"] == "amira"
    assert res["user"]["email"] == "amira@alphaforge.demo"

    # Advisor
    adv_res = authenticate_user("advisor", "AlphaForge2026!")
    assert "advisor" in adv_res["user"]["groups"]


def test_require_advisor_dependency():
    advisor_user = User(
        user_id="adv-1",
        username="advisor",
        groups=["advisor"],
    )
    assert require_advisor(advisor_user) == advisor_user

    regular_user = User(
        user_id="reg-1",
        username="amira",
        groups=[],
    )
    with pytest.raises(HTTPException) as exc:
        require_advisor(regular_user)
    assert exc.value.status_code == 403
