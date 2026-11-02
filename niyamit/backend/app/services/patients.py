"""Patients, consent, opt-out and patient-app access."""
from __future__ import annotations

import re
import uuid
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit, timeline
from app.db import utcnow
from app.enums import ActorType, ConsentPurpose, ConsentStatus, MessageKind, Provenance
from app.models import Clinic, ConsentRecord, Patient, PatientAccessToken
from app.security import Staff, hash_token
from app.services import messaging


def normalise_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 10:
        digits = "91" + digits
    if not 11 <= len(digits) <= 15:
        raise HTTPException(422, "Enter a valid mobile number.")
    return "+" + digits


LANGUAGES = {"en", "hi", "te"}
CHANNELS = {"SIMULATED", "WHATSAPP"}


def create_patient(db: Session, staff: Staff, clinic: Clinic, *, name: str, phone: str, birth_year: int | None,
                   language: str, channel: str, external_ref: str = "", consent_reminders: bool = False,
                   consent_ai: bool = False) -> Patient:
    if not name.strip():
        raise HTTPException(422, "Enter the patient's name.")
    if language not in LANGUAGES or channel not in CHANNELS:
        raise HTTPException(422, "Unsupported language or channel.")
    phone_e164 = normalise_phone(phone)
    if db.scalar(select(Patient).where(Patient.clinic_id == clinic.id, Patient.phone_e164 == phone_e164)):
        raise HTTPException(409, "A patient with this mobile number already exists in this clinic.")
    p = Patient(clinic_id=clinic.id, display_name=name.strip()[:120], phone_e164=phone_e164, birth_year=birth_year,
                preferred_language=language, preferred_channel=channel, external_ref=external_ref.strip()[:60],
                is_synthetic=True)
    db.add(p)
    db.flush()
    audit(db, clinic_id=clinic.id, action="PATIENT_CREATED", actor=staff, object_type="patient", object_id=p.id,
          patient_id=p.id)
    if consent_reminders:
        record_consent(db, p, ConsentPurpose.REMINDERS, ConsentStatus.GRANTED, method="STAFF_RECORDED", staff=staff)
    if consent_ai:
        record_consent(db, p, ConsentPurpose.AI_PROCESSING, ConsentStatus.GRANTED, method="STAFF_RECORDED", staff=staff)
    return p


CONSENT_NAMES = {"REMINDERS": "reminders", "AI_PROCESSING": "AI help with replies and documents",
                 "REPORT_SHARING": "sharing reports", "CAREGIVER_ACCESS": "family helper access"}
CONSENT_METHODS = {"STAFF_RECORDED": "recorded by staff", "PATIENT_APP": "in the patient app", "DEMO_SEED": "demo data",
                   "MESSAGE": "by message reply"}


def record_consent(db: Session, patient: Patient, purpose: ConsentPurpose, status: ConsentStatus, *, method: str,
                   staff: Staff | None = None, channel: str | None = None) -> ConsentRecord:
    rec = ConsentRecord(clinic_id=patient.clinic_id, patient_id=patient.id, purpose=purpose, status=status,
                        method=method, channel=channel, recorded_by_user_id=staff.user_id if staff else None)
    db.add(rec)
    audit(db, clinic_id=patient.clinic_id, action=f"CONSENT_{status}", actor=staff,
          actor_type=None if staff else ActorType.PATIENT, actor_id="" if staff else str(patient.id),
          object_type="consent", patient_id=patient.id, detail={"purpose": purpose, "method": method})
    timeline(db, clinic_id=patient.clinic_id, patient_id=patient.id, event_type="CONSENT_CHANGED",
             summary=f"Consent for {CONSENT_NAMES.get(purpose, purpose.lower())}: {status.lower()} "
                     f"({CONSENT_METHODS.get(method, method.lower().replace('_', ' '))})",
             provenance=Provenance.STAFF_CONFIRMED if staff else Provenance.PATIENT_REPORTED,
             actor_type=ActorType.USER if staff else ActorType.PATIENT, actor_label=staff.label if staff else "Patient")
    return rec


def consent_state(db: Session, patient_id: uuid.UUID) -> dict[str, str]:
    out: dict[str, str] = {}
    for rec in db.scalars(select(ConsentRecord).where(ConsentRecord.patient_id == patient_id)
                          .order_by(ConsentRecord.created_at)).all():
        out[rec.purpose] = rec.status
    return out


def opt_out(db: Session, clinic: Clinic, patient: Patient, *, method: str, staff: Staff | None = None) -> int:
    """Immediate: suppress queued non-essential messages, withdraw messaging consent, confirm once."""
    if patient.opted_out:
        return 0
    patient.opted_out = True
    patient.opted_out_at = utcnow()
    record_consent(db, patient, ConsentPurpose.REMINDERS, ConsentStatus.WITHDRAWN, method=method, staff=staff)
    suppressed = messaging.suppress_pending(db, patient, "OPTED_OUT")
    messaging.queue_message(db, clinic=clinic, patient=patient, kind=MessageKind.OPT_OUT_CONFIRMATION,
                            template_key="OPT_OUT_CONFIRMED", idempotency_key=f"optout:{patient.id}:{patient.opted_out_at.isoformat()}")
    timeline(db, clinic_id=clinic.id, patient_id=patient.id, event_type="OPT_OUT",
             summary=f"Patient opted out of reminders; {suppressed} pending message(s) suppressed",
             provenance=Provenance.STAFF_CONFIRMED if staff else Provenance.PATIENT_REPORTED,
             actor_type=ActorType.USER if staff else ActorType.PATIENT, actor_label=staff.label if staff else "Patient")
    return suppressed


def opt_in(db: Session, patient: Patient, *, method: str, staff: Staff | None = None) -> None:
    patient.opted_out = False
    patient.opted_out_at = None
    record_consent(db, patient, ConsentPurpose.REMINDERS, ConsentStatus.GRANTED, method=method, staff=staff)


def start_patient_session(db: Session, token: str) -> tuple[PatientAccessToken, Patient]:
    rec = db.scalar(select(PatientAccessToken).where(PatientAccessToken.token_hash == hash_token(token)))
    if rec is None or rec.revoked_at is not None or rec.expires_at < utcnow():
        raise HTTPException(401, "This link has expired. Ask the clinic for a new one.")
    if rec.failed_attempts >= 5:
        raise HTTPException(429, "Too many attempts. Ask the clinic for a new link.")
    patient = db.get(Patient, rec.patient_id)
    assert patient is not None
    return rec, patient


def verify_birth_year(db: Session, rec: PatientAccessToken, patient: Patient, birth_year: int | None,
                      clinic: Clinic) -> None:
    """Light identity check before any health detail is shown (PRD 7.3 step 2)."""
    if not clinic.require_patient_verification:
        return
    if birth_year is None or patient.birth_year != birth_year:
        rec.failed_attempts += 1
        audit(db, clinic_id=clinic.id, action="PATIENT_VERIFY_FAILED", actor_type=ActorType.PATIENT,
              actor_id=str(patient.id), patient_id=patient.id, outcome="DENIED")
        db.commit()
        raise HTTPException(401, "That year of birth does not match our records.")
    rec.last_used_at = utcnow()
    audit(db, clinic_id=clinic.id, action="PATIENT_SESSION_STARTED", actor_type=ActorType.PATIENT,
          actor_id=str(patient.id), patient_id=patient.id)


def staff_access_link(db: Session, staff: Staff, patient: Patient) -> str:
    from app.services.links import patient_link

    audit(db, clinic_id=patient.clinic_id, action="PATIENT_LINK_CREATED", actor=staff, object_type="patient",
          object_id=patient.id, patient_id=patient.id)
    return patient_link(db, patient, days=1)


def expire_tokens_for(db: Session, patient: Patient) -> None:
    for rec in db.scalars(select(PatientAccessToken).where(PatientAccessToken.patient_id == patient.id,
                                                           PatientAccessToken.revoked_at.is_(None))).all():
        rec.revoked_at = utcnow() - timedelta(seconds=1)
