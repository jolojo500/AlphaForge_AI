"""Offline tests for per-user dossier in S3 / local storage (PRD C-16)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from alphaforge import config
from alphaforge.api.server import Run, _run_worker, app
from alphaforge.auth import User, create_dev_token
from alphaforge.user_dossier import (
    DossierExistsError,
    LocalUserDossierStore,
    S3UserDossierStore,
    append_decision,
    append_profile_update,
    create_dossier,
    get_dossier_s3_key,
    read_dossier,
    sanitize_username,
    set_dossier_store_override,
)


@pytest.fixture(autouse=True)
def clean_dossier_storage(tmp_path: Path):
    """Ensure each test runs with an isolated local dossier store."""
    store = LocalUserDossierStore(storage_dir=tmp_path)
    set_dossier_store_override(store)
    yield store
    set_dossier_store_override(None)


def test_dossier_creation_and_questionnaire_fields(clean_dossier_storage: LocalUserDossierStore):
    """create_dossier writes header, notice, and all 10 questionnaire fields."""
    profile = {
        "objective": "growth",
        "horizon_years": 15,
        "risk_tolerance": "high",
        "risk_capacity": "moderate",
        "budget_cad": 100000,
        "account_type": "CELI",
        "constraints": ["crypto_max_10", "no_tobacco"],
        "preferences": ["technology", "clean_energy"],
        "current_holdings": {"XIU": 0.5, "XBB": 0.5},
        "notes": "Intérêt marqué pour l'innovation technologique.",
    }

    content = create_dossier("amira", email="amira@alphaforge.demo", profile=profile)

    assert "# Dossier d'investisseur : amira" in content
    assert "simulation éducative, client fictif" in content.lower()
    assert "Date de création (UTC)" in content
    assert "amira@alphaforge.demo" in content

    # All questionnaire fields must be present
    assert "Objectif" in content and "growth" in content
    assert "Horizon" in content and "15 ans" in content
    assert "Tolérance au risque" in content and "high" in content
    assert "Capacité de risque" in content and "moderate" in content
    assert "Budget" in content and "100000 CAD" in content
    assert "Type de compte" in content and "CELI" in content
    assert "Contraintes" in content and "crypto_max_10" in content
    assert "Préférences" in content and "technology" in content
    assert "Avoirs actuels" in content and "XIU" in content
    assert "Notes" in content and "Intérêt marqué pour l'innovation" in content

    # Verify read_dossier returns the exact same content
    read_content = read_dossier("amira")
    assert read_content == content


def test_dossier_no_overwrite(clean_dossier_storage: LocalUserDossierStore):
    """create_dossier never overwrites an existing dossier."""
    initial_profile = {
        "objective": "capital_preservation",
        "horizon_years": 4,
        "risk_tolerance": "low",
        "risk_capacity": "low",
        "budget_cad": 500000,
    }
    original_content = create_dossier("robert", email="robert@alphaforge.demo", profile=initial_profile)
    assert "capital_preservation" in original_content

    # Attempt second create with different data
    new_profile = {
        "objective": "growth",
        "horizon_years": 20,
        "risk_tolerance": "high",
    }
    second_result = create_dossier("robert", email="hacker@alphaforge.demo", profile=new_profile)

    # Dossier on disk/store must not be overwritten
    current = read_dossier("robert")
    assert current == original_content
    assert "capital_preservation" in current
    assert "hacker@alphaforge.demo" not in current
    assert second_result == original_content

    # raise_if_exists=True raises DossierExistsError
    with pytest.raises(DossierExistsError):
        create_dossier("robert", email="other@demo.com", profile=new_profile, raise_if_exists=True)


def test_append_profile_update(clean_dossier_storage: LocalUserDossierStore):
    """append_profile_update adds dated update section with modified profile fields."""
    create_dossier("mateo", email="mateo@alphaforge.demo", profile={"objective": "balanced", "budget_cad": 80000})

    updated_profile = {
        "objective": "growth",
        "horizon_years": 12,
        "risk_tolerance": "moderate",
        "risk_capacity": "high",
        "budget_cad": 120000,
        "account_type": "REER",
        "constraints": ["ESG strict"],
        "preferences": ["water_etf"],
        "current_holdings": {"ESGV": 1.0},
        "notes": "Augmentation du capital d'apport.",
    }
    updated_dossier = append_profile_update("mateo", updated_profile)

    assert "## Profil à la création" in updated_dossier
    assert "## Mise à jour du profil" in updated_dossier
    assert "120000 CAD" in updated_dossier
    assert "ESG strict" in updated_dossier
    assert "Augmentation du capital d'apport" in updated_dossier


def test_append_decision_from_real_offline_run(clean_dossier_storage: LocalUserDossierStore):
    """append_decision from real golden run fixture verifies all required sections."""
    golden_path = config.REPO_ROOT / "tests" / "fixtures" / "golden_runs" / "robert_tsla.json"
    assert golden_path.is_file(), f"Fixture missing: {golden_path}"

    with open(golden_path, encoding="utf-8") as f:
        golden_run = json.load(f)

    final_state = golden_run["final_state"]
    run_id = golden_run.get("run_id", "golden_robert_tsla")

    # Call append_decision for robert
    dossier = append_decision("robert", final_state, run_id=run_id)

    # 1. Run metadata
    assert run_id in dossier
    assert final_state["request_text"] in dossier

    # 2. Resolved profile + conflicts
    assert "Profil résolu et cohérence" in dossier
    assert "Conflits identifiés" in dossier
    for conflict in final_state["profile"]["conflicts"]:
        assert conflict in dossier

    # 3. Scenarios (weights and key metrics with their evidence ids)
    assert "Scénarios comparés" in dossier
    for scenario in final_state["scenarios"]:
        s_name = scenario["name"]
        assert f"Scénario : `{s_name}`" in dossier
        for metric_name, ev_id in scenario["metrics"].items():
            assert metric_name in dossier
            assert ev_id in dossier

    # 4. Scenario judged most consistent
    most_consistent = final_state["explanation"].get("scenario_le_plus_coherent") or "profile_baseline"
    assert f"**Scénario :** `{most_consistent}`" in dossier

    # 5. Verified explanation resume
    resume = final_state["explanation"]["resume"]
    assert resume in dossier

    # 6. Exclusions
    assert "Exclusions de l'univers d'investissement" in dossier
    for ex in final_state["exclusions"]:
        assert ex["ticker"] in dossier
        assert ex["reason"] in dossier
        if ex.get("evidence_id"):
            assert ex["evidence_id"] in dossier

    # 7. Verifier result
    assert "Résultat du vérificateur formel déterministe" in dossier
    assert "Conforme" in dossier

    # 8. Test with advisor review appended
    reviewed_state = dict(final_state)
    reviewed_state["reviewed"] = True
    reviewed_state["reviewer_id"] = "advisor_claire"
    reviewed_state["reviewed_at"] = "2026-11-15T12:00:00Z"
    reviewed_state["chosen_scenario"] = "profile_baseline"
    reviewed_state["advisor_rationale"] = (
        "Le scénario de référence respecte rigoureusement la contrainte de préservation du capital."
    )
    reviewed_state["edited_assumptions"] = {"max_crypto_pct": 0.0}

    reviewed_dossier = append_decision("robert", reviewed_state, run_id=run_id)
    assert "Révision et signature du conseiller" in reviewed_dossier
    assert "advisor_claire" in reviewed_dossier
    assert "profile_baseline" in reviewed_dossier
    assert "Le scénario de référence respecte rigoureusement" in reviewed_dossier
    assert "max_crypto_pct" in reviewed_dossier


def test_sanitised_key():
    """Keys are strictly sanitised to [A-Za-z0-9._-] and never built from raw input."""
    assert sanitize_username("normal_user-123.test") == "normal_user-123.test"
    assert sanitize_username("user/with/slashes") == "user_with_slashes"
    assert sanitize_username("../../etc/passwd") == "etc_passwd"
    assert sanitize_username("john doe!@#$%^&*()") == "john_doe"
    assert sanitize_username("...leading.dots...") == "leading.dots"
    assert sanitize_username("") == "user"

    # Key format
    assert get_dossier_s3_key("amira") == "users/amira/dossier.md"
    assert get_dossier_s3_key("../unsafe/user") == "users/unsafe_user/dossier.md"


def test_endpoint_returns_only_callers_dossier(clean_dossier_storage: LocalUserDossierStore):
    """GET /users/me/dossier returns only the caller's dossier, 401 if unauthed, 404 if none."""
    create_dossier("user_alpha", email="alpha@alphaforge.demo", profile={"objective": "growth"})
    create_dossier("user_beta", email="beta@alphaforge.demo", profile={"objective": "balanced"})

    client = TestClient(app)

    # 1. Unauthenticated -> 401
    resp_unauth = client.get("/users/me/dossier")
    assert resp_unauth.status_code == 401

    # 2. Authenticated as user_alpha -> returns user_alpha's dossier
    token_alpha = create_dev_token(User(user_id="user_alpha", username="user_alpha", email="alpha@alphaforge.demo"))
    resp_alpha = client.get(
        "/users/me/dossier",
        headers={"Authorization": f"Bearer {token_alpha}"},
    )
    assert resp_alpha.status_code == 200
    assert "text/markdown" in resp_alpha.headers["content-type"]
    assert "user_alpha" in resp_alpha.text
    assert "user_beta" not in resp_alpha.text

    # 3. Authenticated as user_beta -> returns user_beta's dossier
    token_beta = create_dev_token(User(user_id="user_beta", username="user_beta", email="beta@alphaforge.demo"))
    resp_beta = client.get(
        "/users/me/dossier",
        headers={"Authorization": f"Bearer {token_beta}"},
    )
    assert resp_beta.status_code == 200
    assert "text/markdown" in resp_beta.headers["content-type"]
    assert "user_beta" in resp_beta.text
    assert "user_alpha" not in resp_beta.text

    # 4. Authenticated as user_gamma (no dossier exists) -> 404
    token_gamma = create_dev_token(User(user_id="user_gamma", username="user_gamma", email="gamma@alphaforge.demo"))
    resp_gamma = client.get(
        "/users/me/dossier",
        headers={"Authorization": f"Bearer {token_gamma}"},
    )
    assert resp_gamma.status_code == 404
    assert "Dossier introuvable" in resp_gamma.json()["detail"]


def test_anonymous_run_writes_nothing(clean_dossier_storage: LocalUserDossierStore, tmp_path: Path):
    """Anonymous runs (owner None or browser cid) write no dossier files."""
    golden_path = config.REPO_ROOT / "tests" / "fixtures" / "golden_runs" / "amira_build.json"
    with open(golden_path, encoding="utf-8") as f:
        golden_data = json.load(f)
    final_state = golden_data["final_state"]

    def dummy_gen():
        yield {"type": "final", "state": final_state}

    # Case 1: Anonymous run (cid)
    anon_run = Run(run_id="run_anon_1", persona="amira", request_text="Analyse anonyme")
    anon_run.owner = "c:session_xyz"
    _run_worker(anon_run, dummy_gen)

    # Verify no dossier was written
    assert read_dossier("session_xyz") is None
    assert read_dossier("c:session_xyz") is None
    assert read_dossier("amira") is None

    # Case 2: Authenticated run (u:amira)
    auth_state = dict(final_state, request_text="Analyse authentifiée")

    def auth_gen():
        yield {"type": "final", "state": auth_state}

    auth_run = Run(run_id="run_auth_1", persona="amira", request_text="Analyse authentifiée")
    auth_run.owner = "u:amira"
    _run_worker(auth_run, auth_gen)

    # Dossier for amira must now exist with the decision
    amira_dossier = read_dossier("amira")
    assert amira_dossier is not None
    assert "run_auth_1" in amira_dossier
    assert "Analyse authentifiée" in amira_dossier


class FakeS3Client:
    """In-memory stub S3 client for offline S3 testing."""

    def __init__(self, should_fail: bool = False):
        self.objects: dict[str, dict[str, Any]] = {}
        self.should_fail = should_fail

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str = "", Metadata: dict | None = None):
        if self.should_fail:
            raise RuntimeError("Simulated S3 network failure")
        self.objects[f"{Bucket}/{Key}"] = {
            "Body": Body,
            "ContentType": ContentType,
            "Metadata": Metadata or {},
        }
        return {"ETag": '"fake"'}

    def get_object(self, Bucket: str, Key: str):
        if self.should_fail:
            raise RuntimeError("Simulated S3 network failure")
        target = f"{Bucket}/{Key}"
        if target not in self.objects:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "Key not found"}}, "GetObject")
        body_bytes = self.objects[target]["Body"]

        class BodyStream:
            def read(self):
                return body_bytes

        return {"Body": BodyStream(), "ContentType": self.objects[target]["ContentType"]}

    def head_object(self, Bucket: str, Key: str):
        if self.should_fail:
            raise RuntimeError("Simulated S3 network failure")
        target = f"{Bucket}/{Key}"
        if target not in self.objects:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "404", "Message": "Not found"}}, "HeadObject")
        return {"ContentLength": len(self.objects[target]["Body"])}


def test_s3_backend_stub_client_and_transparent_fallback(tmp_path: Path):
    """S3 backend writes to S3 key users/<username>/dossier.md and falls back when S3 fails."""
    fake_s3 = FakeS3Client()
    local_store = LocalUserDossierStore(storage_dir=tmp_path)
    s3_store = S3UserDossierStore(
        bucket_name="alphaforge-test-bucket",
        s3_client=fake_s3,
        local_fallback=local_store,
    )
    set_dossier_store_override(s3_store)

    content = create_dossier("claire", email="claire@alphaforge.demo", profile={"objective": "growth"})

    # Must be stored in S3 at users/claire/dossier.md
    expected_s3_key = "alphaforge-test-bucket/users/claire/dossier.md"
    assert expected_s3_key in fake_s3.objects
    assert fake_s3.objects[expected_s3_key]["Body"].decode("utf-8") == content

    # read_dossier must read from S3
    assert read_dossier("claire") == content

    # Now simulate S3 failure: transparent fallback to local
    failing_s3 = FakeS3Client(should_fail=True)
    fallback_store = S3UserDossierStore(
        bucket_name="alphaforge-test-bucket",
        s3_client=failing_s3,
        local_fallback=local_store,
    )
    set_dossier_store_override(fallback_store)

    # Writing should not crash; it writes to local fallback
    fallback_content = create_dossier("david", email="david@alphaforge.demo", profile={"objective": "balanced"})
    assert local_store.dossier_exists("david")
    assert fallback_store.read_dossier("david") == fallback_content


def test_register_creates_dossier_via_api(clean_dossier_storage: LocalUserDossierStore):
    """Calling /auth/register creates a dossier for the newly registered user."""
    client = TestClient(app)
    resp = client.post(
        "/auth/register",
        json={"username": "newuser_1", "password": "Password123!", "email": "newuser1@alphaforge.demo"},
    )
    assert resp.status_code == 200

    dossier = read_dossier("newuser_1")
    assert dossier is not None
    assert "newuser_1" in dossier
    assert "newuser1@alphaforge.demo" in dossier
    assert "Profil à la création" in dossier


def test_update_profile_endpoint_appends_dossier_via_api(clean_dossier_storage: LocalUserDossierStore):
    """Calling PUT /user/profile appends a dated profile update to the user's dossier."""
    client = TestClient(app)
    # Register user first
    client.post(
        "/auth/register",
        json={"username": "profileuser", "password": "Password123!", "email": "profileuser@alphaforge.demo"},
    )

    token = create_dev_token(User(user_id="profileuser", username="profileuser", email="profileuser@alphaforge.demo"))
    update_resp = client.put(
        "/user/profile",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "profile": {
                "objective": "capital_preservation",
                "horizon_years": 5,
                "risk_tolerance": "low",
                "risk_capacity": "low",
                "budget_cad": 250000,
                "notes": "Plan de retraite révisé",
            },
            "account_type": "REER",
            "current_holdings": {"XBB": 1.0},
        },
    )
    assert update_resp.status_code == 200

    dossier = read_dossier("profileuser")
    assert dossier is not None
    assert "Mise à jour du profil" in dossier
    assert "capital_preservation" in dossier
    assert "250000 CAD" in dossier
    assert "Plan de retraite révisé" in dossier


def test_dossier_failure_never_breaks_registration_or_run(clean_dossier_storage: LocalUserDossierStore):
    """If dossier creation/append fails, registration and run completion still succeed."""
    # Custom failing store
    class CrashingStore(LocalUserDossierStore):
        def write_dossier(self, username: str, content: str) -> None:
            raise OSError("Disk full or permission denied")

    set_dossier_store_override(CrashingStore())

    client = TestClient(app)
    # 1. Registration must succeed even if dossier write raises
    reg_resp = client.post(
        "/auth/register",
        json={"username": "robust_user", "password": "Password123!", "email": "robust@alphaforge.demo"},
    )
    assert reg_resp.status_code == 200

    # 2. Run worker must succeed even if dossier write raises
    run = Run(run_id="run_failing_dossier", persona="amira", request_text="Test robustesse")
    run.owner = "u:robust_user"

    def gen():
        yield {"type": "final", "state": {"persona": "amira", "request_text": "Test robustesse"}}

    # Should not raise exception
    _run_worker(run, gen)
    assert run.status == "completed"

