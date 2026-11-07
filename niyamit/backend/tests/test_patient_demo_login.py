import pytest
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import AuditEvent, Clinic, Patient
from app.services import patient_otp


def demo_patient(db):
    return db.scalar(select(Patient).join(Clinic).where(
        Clinic.name == "Sunrise Diabetes Clinic (Synthetic)", Patient.external_ref == "SDC-1001"))


def test_demo_login_needs_no_phone_or_otp_and_is_patient_only(client, monkeypatch):
    def no_sms(*args, **kwargs):
        pytest.fail("Demo login must never request or verify SMS")
    monkeypatch.setattr(patient_otp, "request_code", no_sms)
    monkeypatch.setattr(patient_otp, "verify_code", no_sms)
    assert client.get("/v1/p/otp/config").json()["demo_available"] is True
    # Client-supplied identifiers cannot choose an arbitrary patient or clinic.
    result = client.post("/v1/p/demo-login", json={"phone": "+919999999999", "patient_id": "arbitrary"})
    assert result.status_code == 200 and result.json()["authenticated"] is True
    assert "HttpOnly" in result.headers["set-cookie"]
    home = client.get("/v1/p/home").json()
    assert home["patient"]["first_name"] == "Ramesh"
    assert home["clinic"]["short_name"] == "Sunrise Clinic"
    assert home["demo_session"] is True
    assert client.get("/v1/patients").status_code == 401
    with SessionLocal() as db:
        patient = demo_patient(db)
        assert db.scalar(select(AuditEvent).where(
            AuditEvent.action == "PATIENT_DEMO_LOGIN", AuditEvent.patient_id == patient.id))
    client.post("/v1/p/logout")
    assert client.get("/v1/p/home").status_code == 401


@pytest.mark.parametrize("setting,value", [("demo_mode", False), ("app_env", "production")])
def test_demo_disabled_and_existing_sessions_revoked(client, monkeypatch, setting, value):
    assert client.post("/v1/p/demo-login").status_code == 200
    monkeypatch.setattr(settings, setting, value)
    assert client.get("/v1/p/otp/config").json()["demo_available"] is False
    assert client.post("/v1/p/demo-login").status_code == 404
    assert client.get("/v1/p/home").status_code == 401


@pytest.mark.parametrize("target", ["patient", "clinic"])
def test_demo_never_opens_non_synthetic_records(client, target):
    assert client.post("/v1/p/demo-login").status_code == 200
    with SessionLocal() as db:
        patient = demo_patient(db)
        record = patient if target == "patient" else db.get(Clinic, patient.clinic_id)
        saved = record.is_synthetic
        record.is_synthetic = False
        db.commit()
        try:
            assert client.post("/v1/p/demo-login").status_code == 409
            assert client.get("/v1/p/home").status_code == 401
        finally:
            record.is_synthetic = saved
            db.commit()


def test_demo_does_not_fall_back_to_other_patients(client):
    with SessionLocal() as db:
        patient = demo_patient(db)
        saved = patient.external_ref
        patient.external_ref = "not-the-public-demo"
        db.commit()
        try:
            assert client.post("/v1/p/demo-login").status_code == 409
            assert client.get("/v1/p/home").status_code == 401
        finally:
            patient.external_ref = saved
            db.commit()


def test_demo_login_requires_csrf_client_header(client):
    assert client.post("/v1/p/demo-login", headers={"X-Niyamit-Client": ""}).status_code == 403
    assert client.get("/v1/p/home").status_code == 401
