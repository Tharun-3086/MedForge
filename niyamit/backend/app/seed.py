"""Synthetic demo data: two clinics, staff accounts, patients in different workflow states, seeded
availability and approved (draft-wording) templates. History is created by running the real workflows.

    python -m app.seed            # seed an empty database
    python -m app.seed --force    # wipe everything and seed again

All people, numbers and documents are fictional. Phone numbers use the unallocated +91 90000 0xxxx range.
"""
from __future__ import annotations

import contextlib
import logging
import sys
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base, SessionLocal, engine, utcnow
from app.enums import ConsentPurpose, ConsentStatus, InputMode, ItemKind, MessageKind, Role
from app.models import AppointmentRequest, AvailabilitySlot, Clinic, Membership, Patient, PatientReply, User
from app.security import Staff, hash_password
from app.services import booking, caregivers, inbound, intake, messaging, patients, plans, replies
from app.services.common import clinic_today, current_item, local_dt, set_fault
from app.services.templates import seed_templates

log = logging.getLogger("niyamit.seed")
DEMO_PASSWORD = "niyamit-demo"
SAMPLES = Path(__file__).resolve().parents[1] / "samples"

STAFF_A = [
    ("admin@sunrise.demo", "Meera Iyer", Role.ADMIN),
    ("doctor@sunrise.demo", "Dr. Ananya Rao", Role.DOCTOR),
    ("nurse@sunrise.demo", "Priya Nair", Role.NURSE),
    ("reception@sunrise.demo", "Ravi Kumar", Role.RECEPTION),
    ("ops@niyamit.demo", "Ops Support", Role.OPERATOR),
]
STAFF_B = [("doctor@lakeview.demo", "Dr. Kabir Shah", Role.DOCTOR), ("admin@lakeview.demo", "Nisha Verma", Role.ADMIN)]

# key, name, phone, birth year, language, clinic ref, plan items as (kind, days from today)
PATIENTS_A = [
    ("ramesh", "Ramesh Kumar", "+919000000101", 1962, "te", "SDC-1001", [(ItemKind.REVIEW_VISIT, -12), (ItemKind.HBA1C_TEST, -12)]),
    ("lakshmi", "Lakshmi Prasad", "+919000000102", 1968, "te", "SDC-1187", [(ItemKind.REVIEW_VISIT, 3), (ItemKind.KIDNEY_TEST, 3)]),
    ("abdul", "Abdul Sattar", "+919000000103", 1959, "hi", "SDC-1203", [(ItemKind.EYE_EXAM, -4)]),
    ("meena", "Meena Devi", "+919000000104", 1971, "hi", "SDC-1250", [(ItemKind.REVIEW_VISIT, -2)]),
    ("sunita", "Sunita Reddy", "+919000000105", 1975, "te", "SDC-1302", [(ItemKind.REVIEW_VISIT, 5)]),
    ("venkat", "Venkat Rao", "+919000000106", 1955, "te", "SDC-1340", [(ItemKind.HBA1C_TEST, -9)]),
    ("farhana", "Farhana Begum", "+919000000107", 1966, "hi", "SDC-1388", [(ItemKind.REVIEW_VISIT, -6)]),
    ("suresh", "Suresh Naidu", "+919000000108", 1964, "en", "SDC-1401", [(ItemKind.KIDNEY_TEST, 1)]),
    ("kavya", "Kavya Menon", "+919000000109", 1980, "en", "SDC-1455", [(ItemKind.MEDICINE_REFILL, 6)]),
    ("harish", "Harish Goud", "+919000000110", 1958, "te", "SDC-2210", []),
    ("padma", "Padma Venkatesh", "+919000000111", 1963, "te", "SDC-1490", [(ItemKind.REVIEW_VISIT, 2)]),
    ("imran", "Imran Khan", "+919000000112", 1970, "hi", "SDC-1502", [(ItemKind.REVIEW_VISIT, 10), (ItemKind.FOOT_EXAM, 10)]),
]
PATIENTS_B = [
    ("anil", "Lakeview Patient Anil", "+919000000201", 1960, "en", "LDC-001", [(ItemKind.REVIEW_VISIT, -3)]),
    ("sara", "Lakeview Patient Sara", "+919000000202", 1972, "hi", "LDC-002", [(ItemKind.HBA1C_TEST, 4)]),
]


@contextlib.contextmanager
def _offline_inline():
    """Seeding never calls paid AI providers and runs jobs inline, so the data is deterministic."""
    saved = (settings.tasks_eager, settings.llm_provider, settings.asr_provider, settings.doc_provider)
    settings.tasks_eager, settings.llm_provider, settings.asr_provider, settings.doc_provider = True, "rules", "none", "local"
    try:
        yield
    finally:
        settings.tasks_eager, settings.llm_provider, settings.asr_provider, settings.doc_provider = saved


def reset_database() -> None:
    with engine.begin() as conn:
        tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


def _staff(db: Session, clinic: Clinic, rows) -> dict[str, Staff]:
    out = {}
    for email, name, role in rows:
        user = User(email=email, name=name, password_hash=hash_password(DEMO_PASSWORD))
        db.add(user)
        db.flush()
        db.add(Membership(user_id=user.id, clinic_id=clinic.id, role=role))
        out[role] = Staff(user.id, clinic.id, role, name, email)
    return out


def _slots(db: Session, clinic: Clinic, provider: str) -> None:
    today = clinic_today(clinic)
    for day in range(0, 15):
        d = today + timedelta(days=day)
        if d.weekday() == 6:  # closed on Sundays
            continue
        for hour, minute in [(10, 0), (10, 20), (10, 40), (11, 0), (11, 20), (11, 40), (12, 0), (12, 20),
                             (16, 0), (16, 20), (16, 40), (17, 0), (17, 20)]:
            start = local_dt(clinic, d, hour, minute)
            if start > utcnow():
                db.add(AvailabilitySlot(clinic_id=clinic.id, provider_label=provider, starts_at=start,
                                        ends_at=start + timedelta(minutes=20)))


def _patients(db: Session, clinic: Clinic, doctor: Staff, rows) -> dict[str, Patient]:
    out = {}
    today = clinic_today(clinic)
    for key, name, phone, year, lang, ref, items in rows:
        p = Patient(clinic_id=clinic.id, display_name=name, phone_e164=phone, birth_year=year, preferred_language=lang,
                    preferred_channel="SIMULATED", external_ref=ref, is_synthetic=True,
                    last_visit_at=utcnow() - timedelta(days=95))
        db.add(p)
        db.flush()
        for purpose in (ConsentPurpose.REMINDERS, ConsentPurpose.AI_PROCESSING):
            patients.record_consent(db, p, purpose, ConsentStatus.GRANTED, method="DEMO_SEED")
        if items:
            plan = plans.create_plan(db, doctor, clinic, p, [{"kind": k, "due_date": today + timedelta(days=d)}
                                                            for k, d in items], notes="Seeded synthetic plan")
            plans.approve_plan(db, doctor, clinic, plan)
        db.commit()
        out[key] = p
    return out


def _phone(db: Session, patient: Patient, text_: str, button: bool = False) -> PatientReply:
    """A reply from the simulated phone, sent through the signed webhook path like a real provider event."""
    result, _ = inbound.demo_phone_reply(db, patient, text_, button=button)
    db.commit()  # the reply is processed after commit (inline while seeding)
    return db.get(PatientReply, uuid.UUID(result["reply_id"]), populate_existing=True)


def _upload(db: Session, clinic: Clinic, patient: Patient, name: str, source_type: str, *, staff: Staff | None,
            by_patient: bool = False) -> None:
    sample = SAMPLES / name
    if sample.exists():
        intake.upload(db, clinic, patient, sample.read_bytes(), sample.name, source_type, staff=staff,
                      by_patient=by_patient)
        db.commit()


def seed() -> dict[str, str]:
    with _offline_inline(), SessionLocal() as db:
        a = Clinic(name="Sunrise Diabetes Clinic (Synthetic)", short_name="Sunrise Clinic", phone="040-0000-1111")
        b = Clinic(name="Lakeview Diabetes Centre (Synthetic)", short_name="Lakeview Centre", phone="040-0000-2222")
        # Seeded history is created as if during clinic hours, so the demo looks the same at any time of day.
        a.quiet_hours_start = a.quiet_hours_end = b.quiet_hours_start = b.quiet_hours_end = 0
        db.add_all([a, b])
        db.flush()
        seed_templates(db, a.id)
        seed_templates(db, b.id)
        sa, sb = _staff(db, a, STAFF_A), _staff(db, b, STAFF_B)
        _slots(db, a, "Dr. Ananya Rao (synthetic)")
        _slots(db, b, "Dr. Kabir Shah (synthetic)")
        db.commit()

        P = _patients(db, a, sa[Role.DOCTOR], PATIENTS_A)
        PB = _patients(db, b, sb[Role.DOCTOR], PATIENTS_B)

        # Overdue reminders that went out earlier (sent and delivered through the simulated channel)
        for key in ("ramesh", "farhana", "venkat"):
            item = current_item(db, P[key].id)
            messaging.queue_message(db, clinic=a, patient=P[key], kind=MessageKind.REMINDER_OVERDUE,
                                    template_key="REMINDER_OVERDUE", idempotency_key=f"seed-overdue:{item.id}",
                                    values={"due_date": item.due_date}, plan_id=item.plan_id,
                                    item_id=item.id)
            db.commit()

        # Patient replies from the simulated phone, understood by the offline rules
        _phone(db, P["abdul"], "Paise nahi hain abhi, test baad mein karwaunga")  # cost barrier
        _phone(db, P["meena"], "Dawai ki dose kam karni hai kya? Chakkar aate hain")  # clinical question
        _phone(db, P["sunita"], "Avunu, vastanu")  # confirms
        _phone(db, P["farhana"], "STOP")  # opts out; her queued reminders are suppressed
        _phone(db, PB["anil"], "Please call me back")
        venkat = _phone(db, P["venkat"], "Repu raalenu, Saturday slot unda?")  # asks for a new time, then books
        act = next((x for x in venkat.actions if x.get("slots")), None)
        if act:
            req = db.get(AppointmentRequest, uuid.UUID(act["request_id"]))
            result = booking.commit_booking(db, a, P["venkat"], slot_id=uuid.UUID(act["slots"][0]["id"]),
                                            request_id=req.id, idempotency_key="seed-book-venkat", created_by="PATIENT")
            replies.booking_outcome(db, req, result)
            db.commit()

        # A patient-app reply that is waiting for the patient to choose a slot
        replies.ingest(db, a, P["imran"], channel="PATIENT_APP", mode=InputMode.TEXT, idempotency_key="seed:imran:1",
                       text="Monday nahi aa sakta, Saturday ko aa jaunga")
        db.commit()

        # A permanent channel failure (demo fault switch) -> FAILED message and an owned staff task
        set_fault(db, "CHANNEL_SEND_FAIL", True)
        db.commit()
        plans.manual_reminder(db, sa[Role.RECEPTION], a, P["suresh"], current_item(db, P["suresh"].id))
        db.commit()
        set_fault(db, "CHANNEL_SEND_FAIL", False)
        db.commit()

        # Caregiver access granted by the patient (view + reschedule only)
        _, caregiver_link = caregivers.invite(db, a, P["kavya"], "Arjun Menon (son)", "+919000000190",
                                              ["VIEW_APPOINTMENTS", "REQUEST_RESCHEDULE"])
        db.commit()

        # Report Inbox: two staff uploads and one report shared by a patient
        _upload(db, a, P["harish"], "prescription_review.png", "PRESCRIPTION", staff=sa[Role.NURSE])
        _upload(db, a, P["lakshmi"], "prescription_conflicting_dates.png", "PRESCRIPTION", staff=sa[Role.NURSE])
        _upload(db, a, P["venkat"], "lab_report_hba1c.pdf", "LAB_REPORT", staff=None, by_patient=True)

        from app.jobs import periodic

        periodic()  # overdue tasks for long-overdue items
        for clinic in (a, b):
            clinic.quiet_hours_start, clinic.quiet_hours_end = 21, 8
        db.commit()
        log.info("seed complete")
        return {"clinic_a": str(a.id), "clinic_b": str(b.id), "caregiver_link": caregiver_link}


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as s:
        has_data = s.scalar(select(Clinic.id).limit(1)) is not None
    if has_data and "--force" not in sys.argv:
        print("Database already has data; skipping seed. Use `python -m app.seed --force` to wipe and re-seed.")
        return
    if has_data:
        reset_database()
    info = seed()
    print(f"Seeded synthetic demo data. Staff password: {DEMO_PASSWORD}. Caregiver demo link: {info['caregiver_link']}")


if __name__ == "__main__":
    main()
