"""Test panel scenarios (PRD 18.1 step 13, FR-25/26).

Each scenario runs the real services and reports every check it made. Scenarios run in a separate synthetic
'Test Panel sandbox' clinic, so the real worklist, metrics and patient list are never polluted. The sandbox
has quiet hours switched off so results do not depend on the time of day. Fault switches are always restored.
"""
from __future__ import annotations

import io
import time
import uuid
import wave
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.enums import ConsentPurpose, ConsentStatus, InputMode, ItemKind, MessageKind, MessageStatus, Role
from app.models import (
    Appointment,
    AuditEvent,
    AvailabilitySlot,
    CareTask,
    Clinic,
    ExtractionProposal,
    FollowUpPlan,
    Membership,
    OutboundMessage,
    Patient,
    PatientReply,
    ProviderEvent,
    TimelineEvent,
    User,
)
from app.security import Staff, hash_password, new_token
from app.services import booking, inbound, intake, messaging, patients, plans, replies
from app.services.common import clinic_today, local_dt, set_fault
from app.services.guards import get_patient, get_task
from app.services.templates import approved_template, seed_templates

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
SANDBOX_PREFIX = "Test Panel sandbox"
SANDBOX_EMAIL_PREFIX = "test-panel+"


class Check:
    def __init__(self) -> None:
        self.steps: list[dict[str, Any]] = []

    def __call__(self, name: str, passed: bool, detail: object = "") -> None:
        self.steps.append({"check": name, "passed": bool(passed), "detail": str(detail or "")[:300]})


# ------------------------------------------------------------------ sandbox clinic
def sandbox(db: Session, home: Clinic) -> tuple[Staff, Clinic]:
    name = f"{SANDBOX_PREFIX} · {home.short_name}"
    clinic = db.scalar(select(Clinic).where(Clinic.name == name))
    if clinic is None:
        clinic = Clinic(name=name, short_name="Test Panel", phone=home.phone, timezone=home.timezone,
                        is_synthetic=True, quiet_hours_start=0, quiet_hours_end=0)
        db.add(clinic)
        db.flush()
        seed_templates(db, clinic.id)
        user = User(email=f"{SANDBOX_EMAIL_PREFIX}{clinic.id.hex[:12]}@niyamit.invalid", name="Test Panel (automated)",
                    password_hash=hash_password(new_token()))
        db.add(user)
        db.flush()
        db.add(Membership(user_id=user.id, clinic_id=clinic.id, role=Role.DOCTOR))
        db.commit()
    member = db.scalar(select(Membership).where(Membership.clinic_id == clinic.id))
    user = db.get(User, member.user_id)
    _ensure_slots(db, clinic)
    return Staff(user.id, clinic.id, member.role, user.name, user.email), clinic


def _ensure_slots(db: Session, clinic: Clinic) -> None:
    open_future = db.scalar(select(func.count()).select_from(AvailabilitySlot).where(
        AvailabilitySlot.clinic_id == clinic.id, AvailabilitySlot.status == "OPEN",
        AvailabilitySlot.starts_at > utcnow() + timedelta(hours=2))) or 0
    if open_future >= 20:
        return
    existing = set(db.scalars(select(AvailabilitySlot.starts_at).where(AvailabilitySlot.clinic_id == clinic.id)))
    today = clinic_today(clinic)
    for day in range(1, 8):
        for hour in range(10, 17):
            for minute in (0, 20, 40):
                start = local_dt(clinic, today + timedelta(days=day), hour, minute)
                if start not in existing:
                    db.add(AvailabilitySlot(clinic_id=clinic.id, provider_label="Test Panel doctor (synthetic)",
                                            starts_at=start, ends_at=start + timedelta(minutes=20), source="TEST_PANEL"))
    db.commit()


def _test_patient(db: Session, staff: Staff, clinic: Clinic, label: str) -> Patient:
    n = db.scalar(select(func.count()).select_from(Patient).where(Patient.clinic_id == clinic.id)) or 0
    p = Patient(clinic_id=clinic.id, display_name=f"Test Panel {label}", phone_e164=f"+9190009{n:05d}",
                birth_year=1970, preferred_language="te", preferred_channel="SIMULATED", is_synthetic=True,
                external_ref="TEST-PANEL")
    db.add(p)
    db.flush()
    for purpose in (ConsentPurpose.REMINDERS, ConsentPurpose.AI_PROCESSING):
        patients.record_consent(db, p, purpose, ConsentStatus.GRANTED, method="DEMO_SEED")
    plan = plans.create_plan(db, staff, clinic, p, [{"kind": ItemKind.REVIEW_VISIT, "due_date": clinic_today(clinic)}],
                             notes="Test panel")
    plans.approve_plan(db, staff, clinic, plan)
    db.commit()
    return p


def _process(db: Session, reply_id: uuid.UUID) -> PatientReply:
    """Process synchronously. If the worker (or inline job) already did it, this is a no-op."""
    replies.process_reply(db, reply_id)
    db.commit()
    return db.get(PatientReply, reply_id, populate_existing=True)


def _count(db: Session, model, *where) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where)) or 0


# ------------------------------------------------------------------ scenarios
def duplicate_webhook(db: Session, staff: Staff, clinic: Clinic, c: Check) -> None:
    p = _test_patient(db, staff, clinic, "Duplicate")
    event_id = f"sim-dup-{uuid.uuid4().hex[:8]}"
    first, _ = inbound.demo_phone_reply(db, p, "Please call me back", button=False, event_id=event_id)
    db.commit()
    second, _ = inbound.demo_phone_reply(db, p, "Please call me back", button=False, event_id=event_id)
    db.commit()
    reply_id = uuid.UUID(first["reply_id"])
    _process(db, reply_id)
    _process(db, reply_id)  # a repeated processing attempt must be a no-op
    ev = db.scalar(select(ProviderEvent).where(ProviderEvent.provider_event_id == event_id)
                   .execution_options(populate_existing=True))
    c("Same provider event stored once", _count(db, ProviderEvent, ProviderEvent.provider_event_id == event_id) == 1)
    c("Second delivery recorded as a duplicate", second.get("status") == "duplicate" and ev.duplicate_count == 1,
      f"duplicate_count={ev.duplicate_count}")
    n_replies = _count(db, PatientReply, PatientReply.patient_id == p.id)
    n_tasks = _count(db, CareTask, CareTask.patient_id == p.id, CareTask.category == "CALLBACK")
    c("Exactly one patient reply", n_replies == 1, f"replies={n_replies}")
    c("Exactly one callback task", n_tasks == 1, f"tasks={n_tasks}")


def duplicate_confirmation(db: Session, staff: Staff, clinic: Clinic, c: Check) -> None:
    p = _test_patient(db, staff, clinic, "Confirm twice")
    for _ in range(2):
        r, _ = inbound.demo_phone_reply(db, p, "1", button=False)
        db.commit()
        _process(db, uuid.UUID(r["reply_id"]))
    n = _count(db, TimelineEvent, TimelineEvent.patient_id == p.id, TimelineEvent.event_type == "PATIENT_CONFIRMED")
    acks = _count(db, OutboundMessage, OutboundMessage.patient_id == p.id, OutboundMessage.template_key == "CONFIRM_ACK")
    c("Confirmation recorded once", n == 1, f"confirmation events={n}")
    c("No repeated thank-you message", acks == 1, f"acknowledgements={acks}")
    plan = db.scalar(select(FollowUpPlan).where(FollowUpPlan.patient_id == p.id))
    c("Clinician-approved plan unchanged", plan.status == "ACTIVE" and plan.version == 1, f"v{plan.version} {plan.status}")


def low_confidence(db: Session, staff: Staff, clinic: Clinic, c: Check) -> None:
    p = _test_patient(db, staff, clinic, "Unclear")
    r, _ = replies.ingest(db, clinic, p, channel="PATIENT_APP", mode=InputMode.TEXT,
                          idempotency_key=f"tp-{uuid.uuid4().hex}", text="hmm ok maybe later na")
    db.commit()
    r = _process(db, r.id)
    c("A hedged 'ok' is not recorded as a confirmation", r.status in ("NEEDS_CLARIFICATION", "NEEDS_CONFIRMATION"),
      f"status={r.status}")
    r2, _ = replies.ingest(db, clinic, p, channel="PATIENT_APP", mode=InputMode.TEXT,
                           idempotency_key=f"tp-{uuid.uuid4().hex}", text="Next week vastanu")
    db.commit()
    r2 = _process(db, r2.id)
    act = next(iter(r2.actions), {})
    c("'Next week vastanu' is not recorded as a confirmation", r2.status == "NEEDS_CONFIRMATION"
      and act.get("status") == "AWAITING_CONFIRMATION", f"{r2.status}: {act.get('question', '')}")
    c("No date was guessed from 'next week'", act.get("candidate_date") is None)
    confirmed = _count(db, TimelineEvent, TimelineEvent.patient_id == p.id, TimelineEvent.event_type == "PATIENT_CONFIRMED")
    c("Still no confirmation and nothing booked", confirmed == 0
      and _count(db, Appointment, Appointment.patient_id == p.id) == 0)


def _latest_open_slot(db: Session, clinic: Clinic) -> AvailabilitySlot:
    return db.scalar(select(AvailabilitySlot).where(AvailabilitySlot.clinic_id == clinic.id,
                                                    AvailabilitySlot.status == "OPEN",
                                                    AvailabilitySlot.starts_at > utcnow())
                     .order_by(AvailabilitySlot.starts_at.desc()))


def failed_booking(db: Session, staff: Staff, clinic: Clinic, c: Check) -> None:
    p = _test_patient(db, staff, clinic, "Booking down")
    slot = _latest_open_slot(db, clinic)
    set_fault(db, "BOOKING_PROVIDER_DOWN", True)
    db.commit()
    try:
        req = booking.create_request(db, clinic, p, item=None, reply_id=None, requested_by="PATIENT", day_text=None,
                                     requested=None, window=None, statement="Saturday slot unda?")
        res = booking.commit_booking(db, clinic, p, slot_id=slot.id, request_id=req.id,
                                     idempotency_key=f"tp-{uuid.uuid4().hex}", created_by="PATIENT")
        db.commit()
    finally:
        set_fault(db, "BOOKING_PROVIDER_DOWN", False)
        db.commit()
    c("Booking reported as NOT booked", not res.booked and res.reason == "PROVIDER_UNAVAILABLE", res.reason)
    c("No appointment row was created", _count(db, Appointment, Appointment.patient_id == p.id) == 0)
    t = db.scalar(select(CareTask).where(CareTask.patient_id == p.id, CareTask.category == "BOOKING_FAILED"))
    c("A staff task owns the next step", t is not None, t.title if t else "")
    msg = db.scalar(select(OutboundMessage).where(OutboundMessage.patient_id == p.id,
                                                  OutboundMessage.template_key.like("BOOKING%")))
    c("Patient is told the truth (not booked)", msg is not None and msg.template_key == "BOOKING_NOT_DONE",
      msg.body if msg else "")


def slot_taken(db: Session, staff: Staff, clinic: Clinic, c: Check) -> None:
    p1 = _test_patient(db, staff, clinic, "Slot A")
    p2 = _test_patient(db, staff, clinic, "Slot B")
    slot = _latest_open_slot(db, clinic)
    key = f"tp-{uuid.uuid4().hex}"
    r1 = booking.commit_booking(db, clinic, p1, slot_id=slot.id, request_id=None, idempotency_key=key, created_by="PATIENT")
    db.commit()
    r2 = booking.commit_booking(db, clinic, p2, slot_id=slot.id, request_id=None,
                                idempotency_key=f"tp-{uuid.uuid4().hex}", created_by="PATIENT")
    r3 = booking.commit_booking(db, clinic, p1, slot_id=slot.id, request_id=None, idempotency_key=key, created_by="PATIENT")
    db.commit()
    c("First booking commits with a reference", r1.booked and bool(r1.appointment.booking_reference),
      r1.appointment.booking_reference if r1.appointment else "")
    c("Second patient cannot take the same slot", not r2.booked and r2.reason == "SLOT_UNAVAILABLE", r2.reason)
    c("Retried request returns the same booking", bool(r3.appointment) and r3.appointment.id == r1.appointment.id,
      r3.reason)
    c("Exactly one appointment holds the slot", _count(db, Appointment, Appointment.slot_id == slot.id) == 1)


def _silent_wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 8000)
    return buf.getvalue()


def provider_timeout(db: Session, staff: Staff, clinic: Clinic, c: Check) -> None:
    p = _test_patient(db, staff, clinic, "Timeout")
    set_fault(db, "ASR_TIMEOUT", True)
    set_fault(db, "LLM_TIMEOUT", True)
    db.commit()
    try:
        v, _ = replies.ingest(db, clinic, p, channel="PATIENT_APP", mode=InputMode.VOICE,
                              idempotency_key=f"tp-{uuid.uuid4().hex}", audio=(_silent_wav(), "voice.wav"))
        db.commit()
        v = _process(db, v.id)
        t, _ = replies.ingest(db, clinic, p, channel="PATIENT_APP", mode=InputMode.TEXT,
                              idempotency_key=f"tp-{uuid.uuid4().hex}", text="Monday raalenu, Saturday slot unda?")
        db.commit()
        t = _process(db, t.id)
    finally:
        set_fault(db, "ASR_TIMEOUT", False)
        set_fault(db, "LLM_TIMEOUT", False)
        db.commit()
    c("Speech timeout gives a visible failure state", v.status == "TRANSCRIPTION_FAILED", v.error_code)
    c("No transcript was invented", v.transcript is None)
    c("Language-model timeout falls back to offline rules", t.understanding_source == "RULES",
      "; ".join(t.provider_notes))
    c("Fallback still understood the request", "RESCHEDULE_REQUEST" in (t.understanding or {}).get("intents", []))


def opt_out_queued(db: Session, staff: Staff, clinic: Clinic, c: Check) -> None:
    p = _test_patient(db, staff, clinic, "Opt-out")
    m = messaging.queue_message(db, clinic=clinic, patient=p, kind=MessageKind.REMINDER_MANUAL,
                                template_key="REMINDER_PRE_DUE", idempotency_key=f"tp-{uuid.uuid4().hex}",
                                values={"due_date": "soon"}, scheduled_for=utcnow() + timedelta(minutes=30))
    db.commit()
    c("Reminder is queued before the opt-out", m.status == "SCHEDULED", m.status)
    r, _ = inbound.demo_phone_reply(db, p, "STOP", button=False)
    db.commit()
    _process(db, uuid.UUID(r["reply_id"]))
    messaging.dispatch_due(db, now=utcnow() + timedelta(hours=2))
    db.commit()
    messaging.send(db, m.id)
    db.refresh(m)
    c("Queued reminder was suppressed, not sent", m.status == "SUPPRESSED" and m.sent_at is None,
      f"{m.status} / {m.suppressed_reason}")
    conf = db.scalar(select(OutboundMessage).where(OutboundMessage.patient_id == p.id,
                                                   OutboundMessage.kind == MessageKind.OPT_OUT_CONFIRMATION))
    c("Only the essential opt-out confirmation goes out", conf is not None and conf.essential)


def cross_tenant(db: Session, staff: Staff, clinic: Clinic, c: Check) -> None:
    other = db.scalar(select(Patient).where(Patient.clinic_id != clinic.id).limit(1))
    if other is None:
        c("Another clinic exists for the test", False, "seed the demo data first")
        return
    before = _count(db, AuditEvent, AuditEvent.action == "ACCESS_DENIED")
    try:
        get_patient(db, staff, other.id)
        c("Another clinic's patient is hidden", False, "record was returned!")
    except HTTPException as exc:
        c("Another clinic's patient is hidden (404, no data)", exc.status_code == 404, exc.detail)
    task = db.scalar(select(CareTask).where(CareTask.clinic_id != clinic.id).limit(1))
    if task:
        try:
            get_task(db, staff, task.id)
            c("Another clinic's task is hidden", False, "record was returned!")
        except HTTPException as exc:
            c("Another clinic's task is hidden (404)", exc.status_code == 404)
    after = _count(db, AuditEvent, AuditEvent.action == "ACCESS_DENIED")
    c("Each attempt is recorded as a security event", after > before, f"{after - before} event(s)")


def clinical_routing(db: Session, staff: Staff, clinic: Clinic, c: Check) -> None:
    p = _test_patient(db, staff, clinic, "Clinical")
    r, _ = replies.ingest(db, clinic, p, channel="PATIENT_APP", mode=InputMode.TEXT,
                          idempotency_key=f"tp-{uuid.uuid4().hex}", text="Should I double my insulin dose tonight?")
    db.commit()
    r = _process(db, r.id)
    act = next((a for a in r.actions if a["intent"] == "CLINICAL_QUESTION"), None)
    c("Clinical question handed to a clinician", r.status == "HUMAN_HANDOFF" and act is not None, r.status)
    t = db.scalar(select(CareTask).where(CareTask.patient_id == p.id, CareTask.category == "CLINICAL_QUESTION"))
    c("Task sits in the clinical queue", t is not None and t.queue in ("NURSE", "DOCTOR"), t.queue if t else "")
    approved = approved_template(db, clinic.id, "CLINICAL_ACK", p.preferred_language).body
    text_ = (act or {}).get("patient_text") or ""
    c("Patient sees only the approved acknowledgement (no advice)", text_[:40] == approved[:40], text_[:80])
    r2, _ = replies.ingest(db, clinic, p, channel="PATIENT_APP", mode=InputMode.TEXT,
                           idempotency_key=f"tp-{uuid.uuid4().hex}", text="Chest lo noppi ga undi, chemata vastundi")
    db.commit()
    _process(db, r2.id)
    u = db.scalar(select(CareTask).where(CareTask.patient_id == p.id, CareTask.category == "URGENT_CONCERN"))
    c("Possible urgent concern escalated as URGENT", u is not None and u.priority == "URGENT", u.queue if u else "")
    esc = db.scalar(select(OutboundMessage).where(OutboundMessage.patient_id == p.id,
                                                  OutboundMessage.kind == MessageKind.URGENT_ESCALATION))
    c("Clinic-approved emergency message sent", esc is not None, esc.body[:60] if esc else "")


def prompt_injection_document(db: Session, staff: Staff, clinic: Clinic, c: Check) -> None:
    p = _test_patient(db, staff, clinic, "Injection")
    before = _count(db, OutboundMessage, OutboundMessage.clinic_id == clinic.id)
    data = (SAMPLES / "prompt_injection.png").read_bytes()
    _, prop = intake.upload(db, clinic, p, data, "prompt_injection.png", "PRESCRIPTION", staff=staff)
    db.commit()
    intake.run_extraction(db, prop.id)
    db.commit()
    prop = db.get(ExtractionProposal, prop.id, populate_existing=True)
    c("Document stays in review", prop.status in ("NEEDS_REVIEW", "EXTRACTION_FAILED"), prop.status)
    c("Instruction-like text was flagged and treated as data", any("instruction-like" in n for n in prop.provider_notes),
      "; ".join(prop.provider_notes))
    c("No field was auto-approved", all(f.status != "APPROVED" for f in prop.fields))
    c("No plan was created", prop.plan_id is None)
    after = _count(db, OutboundMessage, OutboundMessage.clinic_id == clinic.id)
    c("No messages were sent because of the document", after == before, f"{after - before} new")


def channel_failure(db: Session, staff: Staff, clinic: Clinic, c: Check) -> None:
    p = _test_patient(db, staff, clinic, "Channel fail")
    set_fault(db, "CHANNEL_SEND_FAIL", True)
    db.commit()
    try:
        m = messaging.queue_message(db, clinic=clinic, patient=p, kind=MessageKind.REMINDER_MANUAL,
                                    template_key="REMINDER_PRE_DUE", idempotency_key=f"tp-{uuid.uuid4().hex}",
                                    values={"due_date": "today"})
        db.commit()
        messaging.send(db, m.id)  # no-op if the worker already handled it
        # The worker may be sending it at this moment: keep the fault on until the attempt has finished.
        for _ in range(100):
            db.refresh(m)
            if m.status in (MessageStatus.FAILED, MessageStatus.DELIVERED, MessageStatus.SENT_TO_PROVIDER):
                break
            db.rollback()
            time.sleep(0.1)
    finally:
        set_fault(db, "CHANNEL_SEND_FAIL", False)
        db.commit()
    c("Failed message is marked FAILED, never 'delivered'", m.status == "FAILED" and m.delivered_at is None,
      f"{m.status} {m.last_error_code}")
    t = db.scalar(select(CareTask).where(CareTask.patient_id == p.id, CareTask.category == "MESSAGE_FAILURE"))
    c("Staff task created to contact the patient another way", t is not None, t.title if t else "")


SCENARIOS: dict[str, tuple[str, Callable[..., None]]] = {
    "duplicate_webhook": ("Duplicate webhook produces exactly one action", duplicate_webhook),
    "duplicate_confirmation": ("Repeated confirmation creates no duplicates", duplicate_confirmation),
    "low_confidence": ("Unclear or vague input asks instead of guessing", low_confidence),
    "failed_booking": ("Booking service down: honest 'not booked' + staff task", failed_booking),
    "slot_taken": ("Slot taken before commit / idempotent retry", slot_taken),
    "provider_timeout": ("Speech and AI timeouts fail visibly and safely", provider_timeout),
    "opt_out_queued": ("Opt-out suppresses an already-queued reminder", opt_out_queued),
    "cross_tenant": ("One clinic cannot read another clinic's data", cross_tenant),
    "clinical_routing": ("Clinical and urgent messages go to humans", clinical_routing),
    "prompt_injection_document": ("Malicious document text is treated as data", prompt_injection_document),
    "channel_failure": ("Permanent channel failure is visible and owned", channel_failure),
}


def run(db: Session, staff: Staff, home: Clinic, name: str) -> dict[str, Any]:
    if name not in SCENARIOS:
        raise HTTPException(404, "Unknown scenario.")
    if staff.role not in (Role.ADMIN, Role.DOCTOR, Role.NURSE):
        raise HTTPException(403, "Only admins and clinicians can run test scenarios.")
    title, fn = SCENARIOS[name]
    c = Check()
    sb_staff, sb_clinic = sandbox(db, home)
    try:
        fn(db, sb_staff, sb_clinic, c)
    except Exception as exc:  # noqa: BLE001 - report, never crash the panel
        db.rollback()
        c("Scenario ran to completion", False, f"{type(exc).__name__}: {exc}")
    return {"name": name, "title": title, "passed": bool(c.steps) and all(s["passed"] for s in c.steps),
            "steps": c.steps, "ran_in": sb_clinic.name, "ran_at": utcnow().isoformat()}
