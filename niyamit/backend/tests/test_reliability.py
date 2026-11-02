"""PRD section 15 — reliability and abuse cases, state machines, and the built-in test panel."""
from __future__ import annotations

import threading
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal, utcnow
from app.enums import InvalidTransition, MessageStatus, PlanStatus, TaskStatus, check_transition
from app.models import Appointment, AvailabilitySlot, CareTask, Clinic, Patient, PatientReply
from app.services import booking
from tests.conftest import login, new_patient, patient_session


def test_state_machines_reject_illegal_moves():
    check_transition(PlanStatus, "NEEDS_REVIEW", "APPROVED")
    check_transition(MessageStatus, "SENT_TO_PROVIDER", "DELIVERED")
    for enum_cls, a, b in [(PlanStatus, "ACTIVE", "NEEDS_REVIEW"), (PlanStatus, "DRAFT", "ACTIVE"),
                           (MessageStatus, "DELIVERED", "QUEUED"), (MessageStatus, "FAILED", "DELIVERED"),
                           (MessageStatus, "SUPPRESSED", "QUEUED"), (TaskStatus, "RESOLVED", "IN_PROGRESS")]:
        with pytest.raises(InvalidTransition):
            check_transition(enum_cls, a, b)


@pytest.mark.parametrize("name", ["duplicate_webhook", "duplicate_confirmation", "low_confidence", "failed_booking",
                                  "slot_taken", "provider_timeout", "opt_out_queued", "cross_tenant",
                                  "clinical_routing", "prompt_injection_document", "channel_failure"])
def test_test_panel_scenarios_pass(client, seeded, name):
    login(client, "doctor@sunrise.demo")
    result = client.post(f"/v1/demo/scenarios/{name}").json()
    assert result["passed"], result
    assert result["ran_in"].startswith("Test Panel sandbox")


def test_test_panel_never_pollutes_the_clinic_worklist(client, seeded):
    login(client, "doctor@sunrise.demo")
    client.post("/v1/demo/scenarios/duplicate_webhook")
    names = [p["name"] for p in client.get("/v1/patients").json()["patients"]]
    assert not any(n.startswith("Test Panel") for n in names)
    assert all(u["email"].endswith(".demo") for u in client.get("/v1/auth/demo-users").json()["users"])


def test_concurrent_bookings_for_one_slot_commit_once(client, seeded):
    login(client, "nurse@sunrise.demo")
    pids = [new_patient(client, f"Race {i}", f"+91900020000{i}") for i in range(4)]
    with SessionLocal() as db:
        slot = db.scalar(select(AvailabilitySlot).where(AvailabilitySlot.status == "OPEN",
                                                        AvailabilitySlot.clinic_id == uuid.UUID(seeded["clinic_a"]),
                                                        AvailabilitySlot.starts_at > utcnow())
                         .order_by(AvailabilitySlot.starts_at.desc()).offset(5))
        slot_id = slot.id
    results = []

    def book(pid: str) -> None:
        with SessionLocal() as db:
            clinic = db.get(Clinic, uuid.UUID(seeded["clinic_a"]))
            patient = db.get(Patient, uuid.UUID(pid))
            res = booking.commit_booking(db, clinic, patient, slot_id=slot_id, request_id=None,
                                         idempotency_key=f"race:{pid}", created_by="PATIENT")
            db.commit()
            results.append(res.booked)

    threads = [threading.Thread(target=book, args=(p,)) for p in pids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Appointment).where(Appointment.slot_id == slot_id)) == 1


def test_cancelled_appointment_frees_the_slot_and_reopens_the_follow_up(client, seeded):
    login(client, "nurse@sunrise.demo")
    pid = new_patient(client, "Cancel Me", "+919000200010")
    slot = client.get("/v1/availability").json()["slots"][3]["id"]
    appt = client.post("/v1/appointments", json={"patient_id": pid, "slot_id": slot}).json()["appointment"]
    assert client.get(f"/v1/patients/{pid}").json()["plans"][0]["items"][0]["status"] == "BOOKED"
    assert client.post(f"/v1/appointments/{appt['id']}/cancel", json={"reason": ""}).status_code == 422
    assert client.post(f"/v1/appointments/{appt['id']}/cancel", json={"reason": "Patient travelling"}).json()["status"] == "CANCELLED"
    assert client.get(f"/v1/patients/{pid}").json()["plans"][0]["items"][0]["status"] == "PENDING"
    assert any(s["id"] == slot for s in client.get("/v1/availability").json()["slots"])


def test_revoked_caregiver_is_rejected_immediately(client, seeded):
    from fastapi.testclient import TestClient

    from app.main import app
    from tests.conftest import HEADERS

    login(client, "nurse@sunrise.demo")
    pid = new_patient(client, "Caregiver Case", "+919000200011")
    patient_session(client, "nurse@sunrise.demo", pid)
    invite = client.post("/v1/p/caregivers", json={"name": "Son", "phone": "9000200099",
                                                   "scopes": ["VIEW_APPOINTMENTS", "REQUEST_RESCHEDULE"]}).json()
    with TestClient(app, headers=HEADERS) as caregiver:  # the caregiver's own phone
        assert caregiver.post("/v1/c/session", json={"token": invite["link"].rsplit("/c/", 1)[1]}).status_code == 200
        offered = caregiver.post("/v1/c/reschedule", json={"day_text": "Saturday"}).json()
        assert offered["request"]["requested_by"] == "CAREGIVER" and offered["request"]["status"] != "BOOKED"
        assert client.delete(f"/v1/p/caregivers/{invite['id']}").status_code == 200  # patient revokes
        assert caregiver.get("/v1/c/home").status_code == 403  # the open session stops working at once
        assert caregiver.post("/v1/c/reschedule", json={"day_text": "Monday"}).status_code == 403


def test_unprocessed_reply_is_retried_then_handed_to_staff(client, seeded):
    from app.services import recovery

    login(client, "nurse@sunrise.demo")
    pid = new_patient(client, "Stuck Reply", "+919000200012")
    with SessionLocal() as db:
        reply = PatientReply(clinic_id=uuid.UUID(seeded["clinic_a"]), patient_id=uuid.UUID(pid), channel="SIMULATED",
                             input_mode="TEXT", idempotency_key=f"stuck:{uuid.uuid4()}", text="Please call me back",
                             status="RECEIVED", created_at=utcnow() - timedelta(minutes=45))
        db.add(reply)
        db.commit()
        rid = reply.id
        assert recovery.recover(db) >= 1
        db.commit()
        reply = db.get(PatientReply, rid, populate_existing=True)
        assert reply.status == "ACTION_FAILED" and reply.error_code == "PROCESSING_TIMEOUT"
        task = db.scalar(select(CareTask).where(CareTask.dedupe_key == f"stuck:{rid}"))
        assert task is not None and task.status == "OPEN"


def test_rate_limit_blocks_password_guessing(client, seeded, monkeypatch):
    from app.security import _local_counters

    monkeypatch.setattr(settings, "rate_limits_enabled", True)
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")  # force the in-process fallback
    from app.redis_client import get_redis

    get_redis.cache_clear()
    _local_counters.clear()
    try:
        codes = [client.post("/v1/auth/login", json={"email": "admin@lakeview.demo", "password": "wrong"}).status_code
                 for _ in range(12)]
        assert codes[:10] == [401] * 10 and codes[-1] == 429
    finally:
        get_redis.cache_clear()
        _local_counters.clear()


def test_patient_link_needs_birth_year_and_locks_after_failures(client, seeded):
    login(client, "nurse@sunrise.demo")
    pid = new_patient(client, "Link Lock", "+919000200013")
    token = client.post(f"/v1/patients/{pid}/access-link").json()["link"].rsplit("/p/", 1)[1]
    client.cookies.clear()
    info = client.post("/v1/p/link", json={"token": token}).json()
    assert "Link Lock" not in str(info) and info["require_verification"]
    for _ in range(5):
        assert client.post("/v1/p/verify", json={"token": token, "birth_year": 1999}).status_code == 401
    assert client.post("/v1/p/verify", json={"token": token, "birth_year": 1970}).status_code == 429
    assert client.post("/v1/p/verify", json={"token": "x" * 32, "birth_year": 1970}).status_code == 401


def test_csrf_header_is_required_for_changes(client, seeded):
    login(client, "nurse@sunrise.demo")
    pid = new_patient(client, "Csrf Case", "+919000200014")
    r = client.post(f"/v1/patients/{pid}/opt-out", headers={"X-Niyamit-Client": ""})
    assert r.status_code == 403
    assert client.get(f"/v1/patients/{pid}").json()["patient"]["opted_out"] is False


def test_plan_changes_create_versions_not_overwrites(client, seeded):
    login(client, "doctor@sunrise.demo")
    pid = new_patient(client, "Versioned Plan", "+919000200015", plan_days=10)
    today = client.get("/v1/dashboard").json()["today"]
    r = client.post("/v1/follow-up-plans", json={"patient_id": pid, "items": [{"kind": "HBA1C_TEST", "due_date": today}]})
    plans = client.get(f"/v1/patients/{pid}").json()["plans"]
    assert [p["status"] for p in plans] == ["ACTIVE", "SUPERSEDED"] and plans[0]["version"] == 2
    assert r.json()["version"] == 2
    login(client, "reception@sunrise.demo")  # reception can draft a plan but cannot make it active
    draft = client.post("/v1/follow-up-plans", json={"patient_id": pid, "items": [{"kind": "EYE_EXAM", "due_date": today}]}).json()
    assert draft["status"] == "NEEDS_REVIEW"
    assert client.post(f"/v1/follow-up-plans/{draft['id']}/approve").status_code == 403
