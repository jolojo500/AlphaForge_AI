"""Unit tests for advisor review, sign-off and suitability records (PRD B-14, #121)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from alphaforge.api.server import InMemoryRunStore, Run, app, set_store
from alphaforge.auth import User, create_dev_token
from alphaforge.state import GraphState, Profile, Scenario
from alphaforge.suitability import LocalSuitabilityStore, set_suitability_store_override
from alphaforge.suitability_pdf import generate_suitability_pdf


def setup_function():
    set_store(InMemoryRunStore())
    set_suitability_store_override(LocalSuitabilityStore(Path("/tmp/af_test_suitability")))


def teardown_function():
    set_suitability_store_override(None)
    trace_file = Path("data/traces/test-workflow-run-001.json")
    if trace_file.is_file():
        trace_file.unlink()


def test_generate_suitability_pdf_validity():
    record = {
        "run_id": "test-run-pdf-001",
        "reviewer_id": "advisor_demo",
        "reviewed_at": dt.datetime.now(dt.UTC).isoformat(),
        "chosen_scenario": "capped",
        "rationale": "Le profil de l'investisseur nécessite une maîtrise stricte de la volatilité et une conformité ESG.",
        "kyc_snapshot": {
            "persona": "amira",
            "objective": "growth",
            "horizon_years": 15,
            "risk_tolerance": "moderate",
            "risk_capacity": "high",
            "account_type": "CELI",
            "budget_cad": 100000.0,
            "constraints": ["exclusion_armes", "exclusion_tabac"],
        },
        "scenarios": [
            {
                "name": "capped",
                "weights": {"XEQT.TO": 0.45, "VFV.TO": 0.35, "CASH.TO": 0.20},
            }
        ],
        "model_ids": {"main": "global.anthropic.claude-sonnet-5-5"},
        "data_dates": {"as_of_date": "2026-03-01"},
        "verifier_result": {"passed": True},
    }

    pdf_bytes = generate_suitability_pdf(record)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert b"%%EOF" in pdf_bytes
    assert len(pdf_bytes) > 800
    assert b"/Helvetica" in pdf_bytes


def test_local_suitability_store(tmp_path: Path):
    store = LocalSuitabilityStore(tmp_path)
    record = {
        "run_id": "run-xyz",
        "reviewer_id": "advisor",
        "chosen_scenario": "balanced",
        "rationale": "Adéquat pour les objectifs déclarés.",
    }

    saved = store.save_record("run-xyz", record)
    assert saved["run_id"] == "run-xyz"

    retrieved = store.get_record("run-xyz")
    assert retrieved is not None
    assert retrieved["reviewer_id"] == "advisor"
    assert retrieved["chosen_scenario"] == "balanced"

    pdf = store.get_pdf("run-xyz")
    assert pdf is not None
    assert pdf.startswith(b"%PDF-1.4")

    assert store.get_record("nonexistent") is None
    assert store.get_pdf("nonexistent") is None


def test_advisor_review_unauthorized_user():
    client = TestClient(app)
    # Regular user without advisor group
    reg_user = User(user_id="reg-1", username="client_user", groups=[])
    token = create_dev_token(reg_user)

    resp = client.post(
        "/runs/any-run/review",
        json={"chosen_scenario": "capped", "rationale": "Justification d'essai"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert "conseillers" in resp.json()["detail"].lower()


def test_advisor_review_full_workflow():
    client_store = InMemoryRunStore()
    set_store(client_store)

    import uuid

    run_id = f"test-workflow-{uuid.uuid4().hex[:8]}"  # records are write-once (#121)
    state = GraphState(
        as_of_date=dt.date(2026, 3, 1),
        persona="amira",
        profile=Profile(
            persona="amira",
            objective="growth",
            horizon_years=15,
            risk_tolerance="moderate",
            risk_capacity="high",
            budget_cad=75000.0,
        ),
        scenarios=[
            Scenario(name="capped", weights={"XEQT.TO": 0.6, "CASH.TO": 0.4}, expected_return=0.07, volatility=0.12),
            Scenario(name="profile_baseline", weights={"CASH.TO": 1.0}, expected_return=0.03, volatility=0.01),
        ],
        verification={"passed": True, "errors": []},
        owner="u:client_user",
    )

    run = Run(
        run_id=run_id,
        persona="amira",
        request_text="Quel est le portefeuille optimal ?",
        as_of_date=dt.date(2026, 3, 1),
    )
    run.status = "completed"
    run.state = state
    run.owner = "u:client_user"
    client_store.save(run)

    client = TestClient(app)

    # 1. Non-advisor user cannot review
    client_token = create_dev_token(User(user_id="reg-1", username="client_user", groups=[]))
    resp_fail = client.post(
        f"/runs/{run_id}/review",
        json={"chosen_scenario": "capped", "rationale": "Ma justification"},
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert resp_fail.status_code == 403

    # 2. Advisor reviews with invalid scenario name -> 400
    advisor_token = create_dev_token(User(user_id="adv-1", username="advisor", groups=["advisor"]))
    resp_inv = client.post(
        f"/runs/{run_id}/review",
        json={"chosen_scenario": "nonexistent_scenario", "rationale": "Ma justification de convenance"},
        headers={"Authorization": f"Bearer {advisor_token}"},
    )
    assert resp_inv.status_code == 400
    assert "Invalid chosen_scenario" in resp_inv.json()["detail"]

    # 3. Advisor reviews with valid scenario -> 200
    resp_ok = client.post(
        f"/runs/{run_id}/review",
        json={
            "chosen_scenario": "capped",
            "rationale": "Portefeuille équilibré et diversifié convenant parfaitement au profil de croissance 15 ans.",
            "edited_assumptions": {"horizon_years": 15, "risk_tolerance": "moderate"},
        },
        headers={"Authorization": f"Bearer {advisor_token}"},
    )
    assert resp_ok.status_code == 200
    data = resp_ok.json()
    assert data["status"] == "reviewed"
    assert data["reviewer_id"] == "advisor"
    assert data["chosen_scenario"] == "capped"

    # 4. Check run state endpoint reflects review
    resp_state = client.get(
        f"/runs/{run_id}",
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert resp_state.status_code == 200
    state_data = resp_state.json()
    assert state_data["reviewed"] is True
    assert state_data["reviewer_id"] == "advisor"
    assert state_data["chosen_scenario"] == "capped"
    assert "Portefeuille équilibré" in state_data["advisor_rationale"]

    # 5. Fetch suitability record JSON
    resp_rec = client.get(
        f"/runs/{run_id}/suitability",
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert resp_rec.status_code == 200
    rec_data = resp_rec.json()
    assert rec_data["run_id"] == run_id
    assert rec_data["reviewer_id"] == "advisor"
    assert rec_data["chosen_scenario"] == "capped"

    # 6. Fetch suitability PDF
    resp_pdf = client.get(
        f"/runs/{run_id}/suitability/pdf",
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert resp_pdf.status_code == 200
    assert resp_pdf.headers["content-type"] == "application/pdf"
    assert resp_pdf.content.startswith(b"%PDF-1.4")


def test_record_is_write_once(tmp_path):
    from alphaforge.suitability import LocalSuitabilityStore, RecordExistsError

    store = LocalSuitabilityStore(storage_dir=tmp_path)
    rec = {"run_id": "r1", "reviewer_id": "advisor", "chosen_scenario": "capped",
           "rationale": "Cohérent avec la capacité faible du client.", "scenarios": [], "kyc_snapshot": {}}
    store.save_record("r1", rec)
    with pytest.raises(RecordExistsError):
        store.save_record("r1", rec | {"chosen_scenario": "as_requested"})


def test_pdf_is_labelled_as_a_fictional_simulation_and_not_bank_branded():
    from alphaforge.suitability_pdf import generate_suitability_pdf

    pdf = generate_suitability_pdf({"run_id": "r1", "chosen_scenario": "capped", "rationale": "x" * 30})
    text = pdf.decode("latin-1")
    assert "SIMULATION EDUCATIVE" in text and "fictif" in text
    assert "BANQUE NATIONALE" not in text.upper()
