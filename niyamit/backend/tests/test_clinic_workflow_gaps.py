"""Connected patient/clinician workflows, clinical authorization and source provenance."""
import uuid
from datetime import timedelta

from sqlalchemy import select

from app.db import SessionLocal, utcnow
from app.models import Patient, TimelineEvent, ExtractedField
from app.ai.rules import classify
from tests.conftest import new_patient, patient_session, login
from tests.test_health_readings import document


def test_question_without_plan_reaches_clinic_and_reply_returns_to_patient(nurse):
    pid = new_patient(nurse, "Clinical Inbox QA", "+919000491001", plan_days=None)
    patient_session(nurse, "nurse@sunrise.demo", pid)
    words = "నా కాళ్ళలో వాపు ఉంది. డాక్టర్ తో మాట్లాడాలి"
    body = {"text": words, "client_key": "question-qa-1"}
    first = nurse.post("/v1/p/questions", json=body)
    assert first.status_code == 200, first.text
    assert nurse.post("/v1/p/questions", json=body).json()["id"] == first.json()["id"]
    login(nurse, "doctor@sunrise.demo")
    rows = nurse.get("/v1/tasks", params={"category": "CLINICAL_QUESTION", "patient_id": pid}).json()["tasks"]
    assert len(rows) == 1 and rows[0]["patient_statement"] == words
    tid = rows[0]["id"]
    reply = {"text": "మీ సందేశం అందింది. మేము మీకు ఫోన్ చేస్తాము."}
    assert nurse.post(f"/v1/tasks/{tid}/reply", json=reply).status_code == 200
    assert nurse.post(f"/v1/tasks/{tid}/reply", json=reply).status_code == 200
    assert nurse.get(f"/v1/tasks/{tid}").json()["status"] == "IN_PROGRESS"
    login(nurse, "doctor@lakeview.demo")
    assert nurse.post(f"/v1/tasks/{tid}/reply", json=reply).status_code == 404
    login(nurse, "admin@sunrise.demo")
    assert nurse.post(f"/v1/tasks/{tid}/reply", json=reply).status_code == 403
    patient_session(nurse, "nurse@sunrise.demo", pid)
    home = nurse.get("/v1/p/home").json()
    assert home["clinical_questions"][0]["question"] == words
    assert len(home["clinician_replies"]) == 1
    assert home["clinician_replies"][0]["text"] == reply["text"]
    assert home["clinician_replies"][0]["question"] == words
    other = new_patient_after_login(nurse, "Reply Isolation QA", "+919000491002")
    patient_session(nurse, "nurse@sunrise.demo", other)
    assert not nurse.get("/v1/p/home").json()["clinician_replies"]


def new_patient_after_login(client, name, phone):
    login(client, "nurse@sunrise.demo")
    return new_patient(client, name, phone, plan_days=None)


def test_swelling_is_clinical_and_urgent_signals_keep_their_existing_route(nurse):
    for text in ("My legs are swollen", "pair mein sujan hai", "కాళ్ళలో వాపు"):
        assert "CLINICAL_QUESTION" in classify(text).intents
    pid = new_patient(nurse, "Urgent Route QA", "+919000491003", plan_days=None)
    patient_session(nurse, "nurse@sunrise.demo", pid)
    response = nurse.post("/v1/p/questions", json={"text": "I cannot breathe", "client_key": "urgent-question"})
    assert response.status_code == 200
    login(nurse, "doctor@sunrise.demo")
    tasks = nurse.get("/v1/tasks", params={"patient_id": pid}).json()["tasks"]
    assert any(t["category"] == "URGENT_CONCERN" and t["priority"] == "URGENT" for t in tasks)


def missing_report(client, phone):
    pid = new_patient(client, "Missing Result QA", phone, plan_days=None)
    with SessionLocal() as db:
        patient = db.get(Patient, uuid.UUID(pid))
        _, proposal = document(db, patient, "synthetic-missed-result.png", utcnow().date().isoformat(),
                               "Fasting blood sugar 75 mg/dL")
        proposal_id = str(proposal.id)
        db.commit()
    return pid, proposal_id


def test_missing_glucose_addition_is_validated_audited_and_shared(nurse):
    pid, proposal_id = missing_report(nurse, "+919000491004")
    path = f"/v1/intake-proposals/{proposal_id}/fields"
    body = {"name": "fasting_glucose", "value": "75 mg/dL", "quote": "Fasting blood sugar 75 mg/dL",
            "page": 1, "reason": "Checked original; OCR omitted measurement"}
    login(nurse, "admin@sunrise.demo")
    assert nurse.post(path, json=body).status_code == 403
    login(nurse, "doctor@lakeview.demo")
    assert nurse.post(path, json=body).status_code == 404
    login(nurse, "doctor@sunrise.demo")
    assert nurse.post(path, json={**body, "value": "75"}).status_code == 422
    assert nurse.post(path, json={**body, "page": 2}).status_code == 422
    added = nurse.post(path, json=body)
    assert added.status_code == 201, added.text
    field = next(f for f in added.json()["fields"] if f["name"] == "fasting_glucose")
    assert field["status"] == "APPROVED" and field["proposed_value"] is None
    assert field["evidence"]["extraction_method"] == "CLINICIAN_TRANSCRIPTION"
    assert nurse.post(path, json=body).status_code == 409
    staff_readings = nurse.get(f"/v1/priorities/{pid}/health-readings").json()["readings"]
    assert any(r["key"] == "fasting_glucose" and r["value"] == "75 mg/dL" and r["clinic_reviewed"] for r in staff_readings)
    patient_session(nurse, "nurse@sunrise.demo", pid)
    readings = nurse.get("/v1/p/health-readings").json()["readings"]
    assert any(r["key"] == "fasting_glucose" and r["value"] == "75 mg/dL" and r["clinic_reviewed"] for r in readings)


def test_additional_observation_stays_in_reviewed_report_not_charts(nurse):
    pid, proposal_id = missing_report(nurse, "+919000491005")
    body = {"name": "clinical_observation", "label": "Serum sodium", "value": "140 mmol/L",
            "quote": "Na+ 140 mmol/L", "page": 1, "reason": "Original result checked"}
    response = nurse.post(f"/v1/intake-proposals/{proposal_id}/fields", json=body)
    assert response.status_code == 201, response.text
    assert any(f["label"] == "Serum sodium" for f in response.json()["fields"])
    patient_session(nurse, "nurse@sunrise.demo", pid)
    documents = nurse.get("/v1/p/documents").json()["documents"]
    assert any(f["label"] == "Serum sodium" and f["value"] == "140 mmol/L" for f in documents[0]["clinic_reviewed_fields"])
    assert not any(r["key"] == "clinical_observation" for r in nurse.get("/v1/p/health-readings").json()["readings"])


def test_staff_created_slot_booked_and_visible_to_patient(nurse):
    pid = new_patient(nurse, "Direct Booking QA", "+919000491006", plan_days=None)
    login(nurse, "doctor@sunrise.demo")
    start = (utcnow() + timedelta(days=3)).replace(hour=5, minute=30, second=0, microsecond=0)
    body = {"starts_at": start.isoformat(), "duration_minutes": 20, "provider_label": "QA clinic room"}
    assert nurse.post("/v1/availability", json={**body, "starts_at": (start-timedelta(minutes=20)).isoformat()}).status_code == 422
    assert nurse.post("/v1/availability", json={**body, "starts_at": (start+timedelta(hours=8,minutes=20)).isoformat()}).status_code == 422
    result = nurse.post("/v1/availability", json=body)
    assert result.status_code == 201, result.text
    slot = result.json()
    assert nurse.post("/v1/availability", json=body).status_code == 409
    assert nurse.post("/v1/availability", json={**body, "starts_at": (start + timedelta(minutes=10)).isoformat()}).status_code == 409
    assert nurse.post("/v1/availability", json={**body, "starts_at": (utcnow()-timedelta(days=1)).isoformat()}).status_code == 422
    booked = nurse.post("/v1/appointments", json={"patient_id": pid, "slot_id": slot["id"], "client_key": "staff-slot-qa"})
    assert booked.status_code == 200, booked.text
    assert booked.json()["appointment"]["reference"]
    patient_session(nurse, "nurse@sunrise.demo", pid)
    appointments = nurse.get("/v1/p/home").json()["appointments"]
    assert any(a["reference"] == booked.json()["appointment"]["reference"] for a in appointments)
    assert nurse.post("/v1/availability", json=body).status_code in (401, 403)
    appointment_id = next(a["id"] for a in appointments if a["reference"] == booked.json()["appointment"]["reference"])
    path = f"/v1/p/appointments/{appointment_id}/response"
    assert nurse.post(path, json={"choice": "CONFIRM"}).status_code == 200
    assert "confirmed attendance" in nurse.get("/v1/p/home").json()["appointments"][0]["patient_response"]
    assert nurse.post(path, json={"choice": "CANNOT_ATTEND"}).status_code == 422
    response = {"choice": "CANNOT_ATTEND", "reason": "TRANSPORT"}
    assert nurse.post(path, json=response).status_code == 200
    assert nurse.post(path, json=response).status_code == 200
    assert nurse.get("/v1/p/home").json()["appointments"]  # a concern does not silently cancel the booking
    login(nurse, "doctor@sunrise.demo")
    tasks = nurse.get("/v1/tasks", params={"patient_id": pid, "category": "BARRIER"}).json()["tasks"]
    assert len(tasks) == 1 and tasks[0]["barrier_category"] == "TRANSPORT"
    other = new_patient_after_login(nurse, "Attendance Isolation QA", "+919000491007")
    patient_session(nurse, "nurse@sunrise.demo", other)
    assert nurse.post(path, json={"choice": "CONFIRM"}).status_code == 404
