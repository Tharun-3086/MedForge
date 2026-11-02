"""PRD section 20 — acceptance gates. The MVP is demo-ready only when every test here passes."""
from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path

from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal
from app.models import (
    Appointment,
    AuditEvent,
    CareTask,
    OutboundMessage,
    PatientReply,
    ProviderEvent,
    SourceArtifact,
)
from app.services.inbound import sign_simulated
from tests.conftest import login, new_patient, patient_id, patient_session

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def _count(model, *where) -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(model).where(*where)) or 0


def _upload(c, pid: str, name: str, source_type: str = "PRESCRIPTION") -> dict:
    with open(SAMPLES / name, "rb") as f:
        r = c.post("/v1/intake-artifacts", files={"file": (name, f)}, data={"patient_id": pid, "source_type": source_type})
    assert r.status_code == 201, r.text
    return c.get(f"/v1/intake-proposals/{r.json()['id']}").json()


def _sim_event(c, payload: dict):
    body = json.dumps(payload).encode()
    return c.post("/v1/webhooks/simulated", content=body,
                  headers={"X-Niyamit-Signature": sign_simulated(body), "Content-Type": "application/json"})


# 1 ---------------------------------------------------------------------------------------------
def test_gate_01_unauthenticated_cannot_view_patient_data(client, seeded):
    login(client, "nurse@sunrise.demo")
    pid = patient_id(client, "Harish")
    proposal = client.get("/v1/intake-proposals").json()["proposals"][0]
    content_url = proposal["artifact"]["content_url"]
    client.cookies.clear()
    for path in ["/v1/patients", f"/v1/patients/{pid}", f"/v1/patients/{pid}/timeline", f"/v1/patients/{pid}/capsule",
                 "/v1/tasks", "/v1/worklists/attention", "/v1/messages", f"/v1/intake-proposals/{proposal['id']}",
                 content_url, "/v1/p/home", "/v1/p/passport", "/v1/c/home"]:
        assert client.get(path).status_code == 401, path


# 2 ---------------------------------------------------------------------------------------------
def test_gate_02_clinic_a_cannot_reach_clinic_b_records(client, seeded):
    login(client, "nurse@sunrise.demo")
    pid = patient_id(client, "Venkat Rao")
    task_id = client.get("/v1/tasks").json()["tasks"][0]["id"]
    prop = client.get("/v1/intake-proposals").json()["proposals"][0]
    slot_id = client.get("/v1/availability").json()["slots"][0]["id"]
    before = _count(AuditEvent, AuditEvent.action == "ACCESS_DENIED")

    login(client, "doctor@lakeview.demo")
    attempts = [
        client.get(f"/v1/patients/{pid}"),
        client.patch(f"/v1/patients/{pid}", json={"display_name": "changed"}),
        client.get(f"/v1/patients/{pid}/timeline"),
        client.post(f"/v1/patients/{pid}/opt-out"),
        client.get(f"/v1/tasks/{task_id}"),
        client.post(f"/v1/tasks/{task_id}/resolve", json={"outcome": "OTHER", "note": "x"}),
        client.get(f"/v1/intake-proposals/{prop['id']}"),
        client.post(f"/v1/intake-proposals/{prop['id']}/reject", json={"reason": "not mine"}),
        client.get(prop["artifact"]["content_url"]),
        client.post("/v1/appointments", json={"patient_id": pid, "slot_id": slot_id}),
        client.post("/v1/follow-up-plans", json={"patient_id": pid, "items": [{"kind": "OTHER", "due_date": "2027-01-01"}]}),
    ]
    for r in attempts:
        assert r.status_code == 404, (r.request.method, r.request.url, r.status_code, r.text)
        assert "Venkat" not in r.text
    assert client.get("/v1/patients", params={"q": "Venkat"}).json()["patients"] == []
    assert _count(AuditEvent, AuditEvent.action == "ACCESS_DENIED") >= before + len(attempts)
    login(client, "nurse@sunrise.demo")
    assert client.get(f"/v1/patients/{pid}").json()["patient"]["name"] == "Venkat Rao"  # nothing was modified


# 3 ---------------------------------------------------------------------------------------------
def test_gate_03_extracted_date_stays_unverified_until_authorised_approval(client, seeded):
    login(client, "nurse@sunrise.demo")
    pid = new_patient(client, "Gate Three", "+919000100003", plan_days=None)
    prop = _upload(client, pid, "prescription_review.png")
    assert prop["status"] == "NEEDS_REVIEW" and prop["plan_id"] is None
    assert all(f["status"] in ("UNVERIFIED", "NEEDS_REVIEW") for f in prop["fields"])
    assert all(f["provenance"] == "AI_PROPOSED" for f in prop["fields"])
    review = next(f for f in prop["fields"] if f["name"] == "next_review_date")

    # Approving the plan before the field itself is approved is refused.
    r = client.post(f"/v1/intake-proposals/{prop['id']}/approve", json={"field_ids": [review["id"]]})
    assert r.status_code == 422
    # Reception staff may review fields but cannot approve a plan (clinic setting: doctors and nurses).
    login(client, "reception@sunrise.demo")
    client.patch(f"/v1/intake-proposals/{prop['id']}/fields/{review['id']}", json={"action": "APPROVE"})
    r = client.post(f"/v1/intake-proposals/{prop['id']}/approve", json={"field_ids": [review["id"]]})
    assert r.status_code == 403
    assert client.get(f"/v1/patients/{pid}").json()["plans"] == []

    login(client, "nurse@sunrise.demo")
    r = client.post(f"/v1/intake-proposals/{prop['id']}/approve", json={"field_ids": [review["id"]]})
    assert r.status_code == 200, r.text
    assert r.json()["plan"]["status"] == "ACTIVE"
    assert r.json()["plan"]["items"][0]["due_date"] == review["value"]


# 4 ---------------------------------------------------------------------------------------------
def test_gate_04_approved_fields_link_to_their_source(client, seeded):
    login(client, "nurse@sunrise.demo")
    pid = new_patient(client, "Gate Four", "+919000100004", plan_days=None)
    prop = _upload(client, pid, "prescription_review.png")
    fields = {f["name"]: f for f in prop["fields"]}
    chosen = [fields[n] for n in ("next_review_date", "eye_exam_due_date")]
    for f in chosen:
        assert f["evidence"]["block_ids"], f
        assert f["evidence"]["bboxes"] and f["evidence"]["page"] == 1, f
        block_text = " ".join(b["text"] for b in prop["blocks"] if b["id"] in f["evidence"]["block_ids"])
        assert f["extracted_value"].split()[0].lower() in block_text.lower()
        client.patch(f"/v1/intake-proposals/{prop['id']}/fields/{f['id']}", json={"action": "APPROVE"})
    plan = client.post(f"/v1/intake-proposals/{prop['id']}/approve",
                       json={"field_ids": [f["id"] for f in chosen]}).json()["plan"]
    assert plan["source"] == "ARTIFACT" and plan["proposal_id"] == prop["id"]
    assert {i["source_field_id"] for i in plan["items"]} == {f["id"] for f in chosen}
    page = client.get(prop["artifact"]["page_url"].replace("{page}", "1"))
    assert page.status_code == 200 and page.headers["content-type"].startswith("image/")


# 5 ---------------------------------------------------------------------------------------------
def test_gate_05_conflicting_or_uncertain_dates_trigger_review(client, seeded):
    login(client, "nurse@sunrise.demo")
    pid = new_patient(client, "Gate Five", "+919000100005")
    prop = _upload(client, pid, "prescription_conflicting_dates.png")
    reviews = [f for f in prop["fields"] if f["name"] == "next_review_date"]
    assert len(reviews) >= 2
    assert all(f["status"] == "NEEDS_REVIEW" and "CONFLICTING_VALUES" in f["review_reasons"] for f in reviews)

    patient_session(client, "nurse@sunrise.demo", pid)
    vague = client.post("/v1/p/replies", json={"text": "Next week vastanu", "client_key": str(uuid.uuid4())}).json()
    assert vague["status"] == "NEEDS_CONFIRMATION", vague  # "I'll come next week" is not a confirmed date
    assert vague["actions"][0]["status"] == "AWAITING_CONFIRMATION" and "next week" in vague["actions"][0]["question"]
    moved = client.post("/v1/p/replies", json={"text": "Monday raalenu, next week vastanu",
                                               "client_key": str(uuid.uuid4())}).json()
    act = next(a for a in moved["actions"] if a["intent"] == "RESCHEDULE_REQUEST")
    assert act["status"] == "AWAITING_SLOT_CHOICE" and "candidate_date" not in act and act["question"]
    hedged = client.post("/v1/p/replies", json={"text": "hmm ok maybe", "client_key": str(uuid.uuid4())}).json()
    assert hedged["status"] == "NEEDS_CLARIFICATION"
    assert _count(Appointment, Appointment.patient_id == uuid.UUID(pid)) == 0


# 6 ---------------------------------------------------------------------------------------------
def test_gate_06_duplicate_webhook_creates_one_action(client, seeded):
    login(client, "nurse@sunrise.demo")
    pid = new_patient(client, "Gate Six", "+919000100006")
    payload = {"event_id": f"gate6-{uuid.uuid4().hex}", "type": "INBOUND_MESSAGE", "from": "+919000100006",
               "text": "Please call me back", "button": False}
    first, second, third = _sim_event(client, payload), _sim_event(client, payload), _sim_event(client, payload)
    assert first.json()["status"] == "accepted"
    assert second.json()["status"] == third.json()["status"] == "duplicate"
    pu = uuid.UUID(pid)
    assert _count(ProviderEvent, ProviderEvent.provider_event_id == payload["event_id"]) == 1
    assert _count(PatientReply, PatientReply.patient_id == pu) == 1
    assert _count(CareTask, CareTask.patient_id == pu, CareTask.category == "CALLBACK") == 1
    assert _count(OutboundMessage, OutboundMessage.patient_id == pu, OutboundMessage.template_key == "CALLBACK_ACK") == 1
    bad = json.dumps(payload | {"event_id": "forged"}).encode()
    r = client.post("/v1/webhooks/simulated", content=bad, headers={"X-Niyamit-Signature": "sha256=forged"})
    assert r.status_code == 401
    assert _count(ProviderEvent, ProviderEvent.provider_event_id == "forged") == 0


# 7 ---------------------------------------------------------------------------------------------
def test_gate_07_replays_do_not_duplicate_reminders_tasks_or_bookings(client, seeded):
    login(client, "nurse@sunrise.demo")
    pid = new_patient(client, "Gate Seven", "+919000100007")
    pu = uuid.UUID(pid)
    # Reminder: a double-clicked manual reminder (same client key) is one message.
    a = client.post(f"/v1/patients/{pid}/reminders", json={"client_key": "gate7-click"}).json()
    b = client.post(f"/v1/patients/{pid}/reminders", json={"client_key": "gate7-click"}).json()
    assert a["id"] == b["id"]
    # Delivery callback replayed (same event, and a late repeat with a new id): no change, no new message.
    _sim_event(client, {"event_id": f"gate7-{uuid.uuid4().hex}", "type": "INBOUND_MESSAGE", "from": "+919000100007",
                        "text": "Please call me back"})
    with SessionLocal() as db:
        ack = db.scalar(select(OutboundMessage).where(OutboundMessage.patient_id == pu,
                                                      OutboundMessage.template_key == "CALLBACK_ACK"))
    assert ack.status == "DELIVERED"
    messages_before = _count(OutboundMessage, OutboundMessage.patient_id == pu)
    event = {"event_id": f"{ack.provider_message_id}:delivered", "type": "DELIVERY_STATUS",
             "message_id": ack.provider_message_id, "status": "delivered"}
    assert _sim_event(client, event).json()["status"] == "duplicate"
    late = _sim_event(client, event | {"event_id": f"{ack.provider_message_id}:late-retry"}).json()
    assert late == {"status": "processed", "result": "NO_CHANGE"}
    assert _count(OutboundMessage, OutboundMessage.patient_id == pu) == messages_before
    # Booking retried with the same key: one appointment.
    slot = client.get("/v1/availability").json()["slots"][-1]["id"]
    r1 = client.post("/v1/appointments", json={"patient_id": pid, "slot_id": slot, "client_key": "gate7-booking"})
    r2 = client.post("/v1/appointments", json={"patient_id": pid, "slot_id": slot, "client_key": "gate7-booking"})
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["appointment"]["reference"] == r2.json()["appointment"]["reference"]
    assert _count(Appointment, Appointment.patient_id == pu) == 1
    # Task: the same reported barrier twice keeps one open task.
    patient_session(client, "nurse@sunrise.demo", pid)
    for _ in range(2):
        client.post("/v1/p/replies/button", json={"choice": "BARRIER:TRANSPORT", "client_key": str(uuid.uuid4())})
    assert _count(CareTask, CareTask.patient_id == pu, CareTask.category == "BARRIER") == 1


# 8 ---------------------------------------------------------------------------------------------
def test_gate_08_no_confirmation_without_a_committed_booking(client, seeded):
    login(client, "nurse@sunrise.demo")
    p1 = new_patient(client, "Gate Eight A", "+919000100081")
    p2 = new_patient(client, "Gate Eight B", "+919000100082")
    slot = client.get("/v1/availability").json()["slots"][-2]["id"]
    assert client.post("/v1/appointments", json={"patient_id": p1, "slot_id": slot}).status_code == 200
    taken = client.post("/v1/appointments", json={"patient_id": p2, "slot_id": slot})
    assert taken.status_code == 409 and "not booked" in taken.json()["detail"].lower()
    p2u = uuid.UUID(p2)
    assert _count(Appointment, Appointment.patient_id == p2u) == 0
    assert _count(OutboundMessage, OutboundMessage.patient_id == p2u, OutboundMessage.template_key == "BOOKING_CONFIRMED") == 0

    client.post("/v1/demo/faults", json={"key": "BOOKING_PROVIDER_DOWN", "enabled": True})
    try:
        other = client.get("/v1/availability")
        assert other.status_code == 503
        down = client.post("/v1/appointments", json={"patient_id": p2, "slot_id": slot})
        assert down.status_code == 409
    finally:
        client.post("/v1/demo/faults", json={"key": "BOOKING_PROVIDER_DOWN", "enabled": False})
    assert _count(Appointment, Appointment.patient_id == p2u) == 0
    assert _count(OutboundMessage, OutboundMessage.patient_id == p2u, OutboundMessage.template_key == "BOOKING_CONFIRMED") == 0
    assert _count(OutboundMessage, OutboundMessage.patient_id == p2u, OutboundMessage.template_key == "BOOKING_NOT_DONE") == 1
    tasks = client.get("/v1/tasks", params={"patient_id": p2}).json()["tasks"]
    assert any(t["category"] == "BOOKING_FAILED" for t in tasks)


# 9 ---------------------------------------------------------------------------------------------
def test_gate_09_nothing_dispatched_after_opt_out_including_queued(client, seeded):
    from datetime import timedelta

    from app.db import utcnow
    from app.services import messaging

    login(client, "nurse@sunrise.demo")
    pid = new_patient(client, "Gate Nine", "+919000100009", plan_days=2)
    pu = uuid.UUID(pid)
    pending_before = _count(OutboundMessage, OutboundMessage.patient_id == pu, OutboundMessage.status == "SCHEDULED")
    assert pending_before >= 1  # reminders were scheduled by the approved plan
    r = _sim_event(client, {"event_id": f"gate9-{uuid.uuid4().hex}", "type": "INBOUND_MESSAGE",
                            "from": "+919000100009", "text": "STOP"})
    assert r.json()["status"] == "accepted"
    assert _count(OutboundMessage, OutboundMessage.patient_id == pu, OutboundMessage.status.in_(["SCHEDULED", "QUEUED"])) == 0
    with SessionLocal() as db:  # even when the scheduler runs far in the future, nothing goes out
        messaging.dispatch_due(db, now=utcnow() + timedelta(days=30))
        db.commit()
        ids = db.scalars(select(OutboundMessage.id).where(OutboundMessage.patient_id == pu)).all()
    for mid in ids:
        with SessionLocal() as db:
            messaging.send(db, mid)
    with SessionLocal() as db:
        sent = db.scalars(select(OutboundMessage).where(OutboundMessage.patient_id == pu,
                                                        OutboundMessage.status.in_(["SENT_TO_PROVIDER", "DELIVERED"]))).all()
    assert [m.kind for m in sent] == ["OPT_OUT_CONFIRMATION"]  # only the essential confirmation
    manual = client.post(f"/v1/patients/{pid}/reminders", json={}).json()
    assert manual["status"] == "SUPPRESSED" and manual["suppressed_reason"] == "OPTED_OUT"


# 10 --------------------------------------------------------------------------------------------
def test_gate_10_clinical_advice_prompts_go_to_humans(client, seeded):
    from app.services.templates import TEMPLATES

    login(client, "nurse@sunrise.demo")
    pid = new_patient(client, "Gate Ten", "+919000100010", language="en")
    patient_session(client, "nurse@sunrise.demo", pid)
    prompts = ["Should I double my insulin dose tonight?", "Metformin band kar sakta hoon kya?",
               "Sugar 300 undi, tablet maarchala?", "Is my HbA1c report normal?"]
    ack = TEMPLATES["CLINICAL_ACK"]["en"].split("{")[0]
    for text_ in prompts:
        r = client.post("/v1/p/replies", json={"text": text_, "client_key": str(uuid.uuid4())}).json()
        assert r["status"] == "HUMAN_HANDOFF", (text_, r)
        act = next(a for a in r["actions"] if a["intent"] in ("CLINICAL_QUESTION", "URGENT_CONCERN"))
        if act["intent"] == "CLINICAL_QUESTION":
            assert act["patient_text"].startswith(ack.strip())
        for a in r["actions"]:  # nothing patient-facing contains dosing or a diagnosis
            words = (a.get("patient_text") or "").lower()
            assert "mg" not in words.split() and "dose" not in words and "diagnos" not in words
    login(client, "nurse@sunrise.demo")
    tasks = client.get("/v1/tasks", params={"patient_id": pid}).json()["tasks"]
    human = [t for t in tasks if t["category"] in ("CLINICAL_QUESTION", "URGENT_CONCERN")]
    assert len(human) == len(prompts)  # one clinician task per question
    assert all(t["queue"] in ("NURSE", "DOCTOR") for t in human)
    login(client, "reception@sunrise.demo")
    assert all(t["category"] != "CLINICAL_QUESTION" for t in client.get("/v1/tasks").json()["tasks"])


# 11 --------------------------------------------------------------------------------------------
def test_gate_11_provider_timeout_is_visible_with_safe_fallback(client, seeded):
    login(client, "nurse@sunrise.demo")
    pid = new_patient(client, "Gate Eleven", "+919000100011")
    for key in ("ASR_TIMEOUT", "LLM_TIMEOUT", "DOC_PROVIDER_DOWN"):
        client.post("/v1/demo/faults", json={"key": key, "enabled": True})
    try:
        prop = _upload(client, pid, "prescription_review.png")
        assert prop["status"] == "NEEDS_REVIEW" and prop["extractor"] == "rules"
        assert any("unavailable" in n for n in prop["notes"])
        patient_session(client, "nurse@sunrise.demo", pid)
        wav = (SAMPLES.parent / "tests" / "fixtures" / "silence.wav").read_bytes()
        v = client.post("/v1/p/replies/voice", files={"audio": ("v.wav", wav, "audio/wav")},
                        data={"client_key": str(uuid.uuid4())}).json()
        assert v["status"] == "TRANSCRIPTION_FAILED" and v["error_code"] == "TIMEOUT" and v["transcript"] is None
        t = client.post("/v1/p/replies", json={"text": "Monday raalenu", "client_key": str(uuid.uuid4())}).json()
        assert t["understood"]["source"] == "RULES" and "RESCHEDULE_REQUEST" in t["understood"]["intents"]
        fixed = client.post(f"/v1/p/replies/{v['id']}/correct", json={"text": "Please call me back"}).json()
        assert any(a["intent"] == "CALLBACK_REQUEST" for a in fixed["actions"])
    finally:
        login(client, "nurse@sunrise.demo")
        for key in ("ASR_TIMEOUT", "LLM_TIMEOUT", "DOC_PROVIDER_DOWN"):
            client.post("/v1/demo/faults", json={"key": key, "enabled": False})


# 12 --------------------------------------------------------------------------------------------
def test_gate_12_failed_message_is_never_shown_as_delivered(client, seeded, no_quiet_hours):
    from app.services import messaging

    login(client, "nurse@sunrise.demo")
    pid = new_patient(client, "Gate Twelve", "+919000100012")
    client.post("/v1/demo/faults", json={"key": "CHANNEL_SEND_FAIL", "enabled": True})
    try:
        m = client.post(f"/v1/patients/{pid}/reminders", json={}).json()
    finally:
        client.post("/v1/demo/faults", json={"key": "CHANNEL_SEND_FAIL", "enabled": False})
    listing = client.get("/v1/messages", params={"patient_id": pid}).json()
    attention = next(g for g in listing["groups"] if g["key"] == "attention")
    msg = next(x for x in attention["messages"] if x["id"] == m["id"])
    assert msg["status"] == "FAILED" and msg["delivered_at"] is None and msg["status_label"] == "Failed"
    sent = next(g for g in listing["groups"] if g["key"] == "sent")
    assert all(x["id"] != m["id"] for x in sent["messages"])
    tasks = client.get("/v1/tasks", params={"patient_id": pid}).json()["tasks"]
    assert any(t["category"] == "MESSAGE_FAILURE" for t in tasks)
    # A provider-reported failure is final: a late 'delivered' callback cannot move it backwards.
    _sim_event(client, {"event_id": f"gate12-{uuid.uuid4().hex}", "type": "INBOUND_MESSAGE", "from": "+919000100012",
                        "text": "Please call me back"})
    with SessionLocal() as db:
        ack = db.scalar(select(OutboundMessage).where(OutboundMessage.patient_id == uuid.UUID(pid),
                                                      OutboundMessage.template_key == "CALLBACK_ACK"))
        ack.status = "SENT_TO_PROVIDER"  # pretend the delivery receipt has not arrived yet
        ack.delivered_at = None
        db.commit()
        assert messaging.apply_delivery_status(db, ack.provider_message_id, "failed", "131026") == "FAILED"
        db.commit()
        assert messaging.apply_delivery_status(db, ack.provider_message_id, "delivered") == "NO_CHANGE"
        db.commit()
        db.refresh(ack)
        assert ack.status == "FAILED" and ack.delivered_at is None


# 13 --------------------------------------------------------------------------------------------
def test_gate_13_unresolved_tasks_stay_visible_with_owner_and_status(client, seeded):
    from datetime import timedelta

    from app.db import utcnow
    from app.services.tasks import escalate_unassigned

    login(client, "nurse@sunrise.demo")
    pid = new_patient(client, "Gate Thirteen", "+919000100013")
    _sim_event(client, {"event_id": f"gate13-{uuid.uuid4().hex}", "type": "INBOUND_MESSAGE",
                        "from": "+919000100013", "text": "Please call me back"})
    task = next(t for t in client.get("/v1/tasks", params={"patient_id": pid}).json()["tasks"]
                if t["category"] == "CALLBACK")
    assert task["status"] == "OPEN" and task["queue"] == "RECEPTION" and task["due_at"]
    with SessionLocal() as db:  # unassigned and past due -> escalated, never dropped
        assert escalate_unassigned(db, now=utcnow() + timedelta(days=3)) >= 1
        db.commit()
    task = client.get(f"/v1/tasks/{task['id']}").json()
    assert task["escalated_at"] and any("Escalated" in e["note"] for e in task["events"])
    assert client.post(f"/v1/tasks/{task['id']}/resolve", json={"outcome": "", "note": ""}).status_code == 422
    staff_id = next(s["id"] for s in client.get("/v1/clinic/staff").json()["staff"] if s["role"] == "RECEPTION")
    task = client.post(f"/v1/tasks/{task['id']}/assign", json={"assignee_user_id": staff_id, "note": "Ravi calls"}).json()
    assert task["status"] == "ASSIGNED" and task["assignee"] == "Ravi Kumar"
    task = client.post(f"/v1/tasks/{task['id']}/resolve", json={"outcome": "REACHED_PATIENT", "note": "Called"}).json()
    closed = client.get("/v1/tasks", params={"status": "closed", "patient_id": pid}).json()["tasks"]
    assert any(t["id"] == task["id"] and t["outcome"] == "REACHED_PATIENT" for t in closed)
    assert [e["to"] for e in task["events"]][:1] == ["OPEN"] and task["events"][-1]["to"] == "RESOLVED"


# 14 --------------------------------------------------------------------------------------------
def test_gate_14_uploads_are_private_validated_and_encrypted(client, seeded):
    login(client, "nurse@sunrise.demo")
    pid = new_patient(client, "Gate Fourteen", "+919000100014")
    bad = [("evil.exe", b"MZ\x90\x00binary"), ("report.pdf", b"\x89PNG\r\n\x1a\n" + b"0" * 100),
           ("notes.txt", b"just text without commas"), ("big.png", b"\x89PNG\r\n\x1a\n" + b"0" * (11 * 1024 * 1024))]
    for name, data in bad:
        r = client.post("/v1/intake-artifacts", files={"file": (name, data)}, data={"patient_id": pid})
        assert r.status_code in (413, 415), (name, r.status_code)
    prop = _upload(client, pid, "lab_report_hba1c.pdf", "LAB_REPORT")
    url = prop["artifact"]["content_url"]
    assert client.get(url).status_code == 200
    art_id = prop["artifact"]["id"]
    assert client.get(f"/v1/artifacts/{art_id}/content").status_code == 422  # no signature
    assert client.get(f"/v1/artifacts/{art_id}/content?exp=1&sig=abc").status_code == 403  # expired / forged
    with SessionLocal() as db:
        art = db.get(SourceArtifact, uuid.UUID(art_id))
        stored = (Path(settings.storage_dir) / art.storage_key).read_bytes()
    assert not stored.startswith(b"%PDF") and b"Venkat" not in stored  # encrypted at rest
    client.cookies.clear()
    assert client.get(url).status_code == 401  # a signed URL alone is not enough


# 15 --------------------------------------------------------------------------------------------
def test_gate_15_logs_carry_no_raw_patient_content(client, seeded, caplog):
    from app.logging_setup import JsonFormatter

    login(client, "nurse@sunrise.demo")
    pid = new_patient(client, "Gate Fifteen", "+919000100015")
    secret = "ZEBRA-7731 Monday raalenu, Saturday slot unda"
    caplog.set_level(logging.DEBUG)
    _sim_event(client, {"event_id": f"gate15-{uuid.uuid4().hex}", "type": "INBOUND_MESSAGE",
                        "from": "+919000100015", "text": secret})
    patient_session(client, "nurse@sunrise.demo", pid)
    client.post("/v1/p/replies", json={"text": secret, "client_key": str(uuid.uuid4())})
    fmt = JsonFormatter()
    out = "\n".join(fmt.format(r) for r in caplog.records)
    assert "ZEBRA-7731" not in out and "Gate Fifteen" not in out and "9000100015" not in out
    assert "[redacted-number]" in fmt.format(logging.LogRecord("t", 20, "", 0, "call +91 90001 00015 now", None, None))


# 16 --------------------------------------------------------------------------------------------
def test_gate_16_language_metrics_are_reproducible_from_the_versioned_set(client, seeded):
    login(client, "nurse@sunrise.demo")
    corpus = client.get("/v1/evals/corpus").json()
    assert corpus["version"] and corpus["count"] == len(corpus["items"]) >= 40
    assert set(corpus["by_language"]) == {"te-en", "hi-en", "en"}
    runs = []
    for _ in range(2):
        rid = client.post("/v1/evals/runs", json={"provider": "rules"}).json()["id"]
        runs.append(client.get(f"/v1/evals/runs/{rid}").json())
    a, b = runs
    assert a["run"]["status"] == b["run"]["status"] == "DONE"
    assert [(i["id"], i["predicted"]) for i in a["items"]] == [(i["id"], i["predicted"]) for i in b["items"]]
    assert a["run"]["exact_match"] == sum(i["exact"] for i in a["items"])
    assert {x["language_pair"] for x in a["by_language"]} == {"te-en", "hi-en", "en"}
    support = {x["intent"]: x["support"] for x in a["by_intent"]}
    for intent in {i for item in corpus["items"] for i in item["intents"]}:
        assert support[intent] == sum(intent in item["intents"] for item in corpus["items"])
    unconfigured = client.post("/v1/evals/runs", json={"provider": "openai"})
    assert unconfigured.status_code == 422  # never reports a run for a provider that is not configured


# 17 --------------------------------------------------------------------------------------------
def test_gate_17_demo_mode_labels_synthetic_data_and_simulations(client, seeded):
    login(client, "nurse@sunrise.demo")
    me = client.get("/v1/auth/me").json()
    assert me["demo_mode"] and me["clinic"]["is_synthetic"] and "Synthetic" in me["clinic"]["name"]
    assert all(p["is_synthetic"] for p in client.get("/v1/patients").json()["patients"])
    groups = client.get("/v1/messages").json()["groups"]
    listed = [m for g in groups for m in g["messages"]]
    assert listed and all(m["simulated"] for m in listed if m["channel"] == "SIMULATED")
    # Staff screens never show a patient's private access token.
    assert not any(re.search(r"/p/[A-Za-z0-9_\-]{8,}", m["body"]) for m in listed)
    phone = client.get(f"/v1/demo/phone/{patient_id(client, 'Sunita')}").json()
    assert phone["simulated"] is True and "SIMULATED" in phone["note"]
    assert "Synthetic" in client.get("/v1/metrics").json()["data_label"]
    assert client.get("/v1/availability").json()["source"] == "Seeded demo availability"
    settings.demo_mode = False
    try:
        assert client.get("/v1/demo/status").status_code == 404
        assert client.get("/v1/auth/demo-users").status_code == 404
    finally:
        settings.demo_mode = True


# 18 --------------------------------------------------------------------------------------------
def test_gate_18_text_and_human_routes_exist_without_voice(client, seeded):
    login(client, "nurse@sunrise.demo")
    pid = new_patient(client, "Gate Eighteen", "+919000100018")
    patient_session(client, "nurse@sunrise.demo", pid)
    home = client.get("/v1/p/home").json()
    assert home["voice_available"] is False and home["items"]
    wav = (SAMPLES.parent / "tests" / "fixtures" / "silence.wav").read_bytes()
    v = client.post("/v1/p/replies/voice", files={"audio": ("v.wav", wav, "audio/wav")},
                    data={"client_key": str(uuid.uuid4())}).json()
    assert v["status"] == "TRANSCRIPTION_FAILED" and v["error_code"] == "NOT_CONFIGURED" and v["can_correct"]
    typed = client.post("/v1/p/replies", json={"text": "Avunu, vastanu", "client_key": str(uuid.uuid4())}).json()
    assert typed["actions"][0]["intent"] == "CONFIRM_FOLLOWUP" and typed["actions"][0]["status"] == "DONE"
    callback = client.post("/v1/p/replies/button", json={"choice": "CALLBACK", "client_key": str(uuid.uuid4())}).json()
    assert callback["actions"][0]["status"] == "DONE" and callback["actions"][0]["patient_text"]
    login(client, "reception@sunrise.demo")
    assert any(t["category"] == "CALLBACK" for t in client.get("/v1/tasks", params={"patient_id": pid}).json()["tasks"])
