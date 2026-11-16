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

    demo_u = verify_token("demo-amira")
    assert demo_u.username == "Amira"
    assert demo_u.user_id == "demo-amira"
    assert demo_u.groups == [] and demo_u.is_advisor is False


@pytest.mark.parametrize("token", ["demo-advisor", "demo-wilson", "demo-", "demo-Amira", "demo-amira ", "demo-amira2"])
def test_demo_tokens_are_only_the_three_personas(token, monkeypatch):
    """A fixed demo token exists for amira, mateo and robert only; nothing else is accepted
    and nothing starting with "demo-" ever grants a group, with authentication off or on."""
    from alphaforge import auth

    with pytest.raises(HTTPException) as exc:
        verify_token(token)
    assert exc.value.status_code == 401

    monkeypatch.setattr(auth, "is_auth_enabled", lambda: True)
    monkeypatch.setattr(auth, "get_jwks_client", lambda: (_ for _ in ()).throw(AssertionError("no network")))
    with pytest.raises(HTTPException) as exc_on:
        verify_token(token)
    assert exc_on.value.status_code == 401
    for ok in ("amira", "mateo", "robert"):
        u = verify_token(f"demo-{ok}")
        assert u.user_id == f"demo-{ok}" and u.groups == [] and not u.is_advisor


def test_demo_token_rejected_by_the_api(monkeypatch):
    from fastapi.testclient import TestClient

    from alphaforge.api.server import app

    client = TestClient(app)
    for token in ("demo-advisor", "demo-wilson", "demo-"):
        res = client.get("/user/profile", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 401, (token, res.status_code, res.text)


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


def test_dev_token_is_rejected_when_auth_is_on(monkeypatch):
    # The dev signing secret is in the repository: a locally signed token must never pass in prod.
    token = create_dev_token(User(user_id="x", username="advisor", groups=["advisor"]))
    monkeypatch.setenv("AF_AUTH", "on")
    with pytest.raises(HTTPException) as exc:
        verify_token(token)
    assert exc.value.status_code == 401


def test_register_dev_mode_never_grants_a_group():
    from alphaforge.auth import register_user

    res = register_user("advisor", "longenough1")
    assert res["user"]["groups"] == []
    for bad in ("ab", "a b c", "x" * 65):
        with pytest.raises(HTTPException) as exc:
            register_user(bad, "longenough1")
        assert exc.value.status_code == 400
    with pytest.raises(HTTPException):
        register_user("newuser", "short")


def test_register_existing_cognito_user_is_a_conflict_not_a_session(monkeypatch):
    import alphaforge.auth as auth

    class Exists(Exception):
        pass

    class Other(Exception):
        pass

    class FakeClient:
        class exceptions:  # noqa: N801
            UsernameExistsException = Exists
            InvalidPasswordException = Other
            InvalidParameterException = Other

        def sign_up(self, **kw):
            raise Exists()

    class FakeSession:
        def __init__(self, **kw):
            pass

        def client(self, *a, **kw):
            return FakeClient()

    monkeypatch.setenv("AF_AUTH", "on")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setattr(auth.boto3, "Session", FakeSession)
    with pytest.raises(HTTPException) as exc:
        auth.register_user("advisor", "Longenough1!")
    assert exc.value.status_code == 409


def test_register_confirms_the_account_then_logs_in(monkeypatch):
    import alphaforge.auth as auth

    calls = []

    class E(Exception):
        pass

    class FakeClient:
        class exceptions:  # noqa: N801
            UsernameExistsException = E
            InvalidPasswordException = E
            InvalidParameterException = E

        def sign_up(self, **kw):
            calls.append("sign_up")
            return {"UserConfirmed": False}

        def admin_confirm_sign_up(self, **kw):
            calls.append(("confirm", kw["Username"]))

    class FakeSession:
        def __init__(self, **kw):
            pass

        def client(self, *a, **kw):
            return FakeClient()

    monkeypatch.setenv("AF_AUTH", "on")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setattr(auth.boto3, "Session", FakeSession)
    monkeypatch.setattr(auth, "authenticate_user", lambda u, p: {"user": {"username": u}})
    assert auth.register_user("newbie", "Longenough1!") == {"user": {"username": "newbie"}}
    assert calls == ["sign_up", ("confirm", "newbie")]
