"""Caregiver mode (PRD 7.11): patient-invited, explicitly scoped, logged and revocable. Report and clinical
message access are never included by default."""
from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit, timeline
from app.config import settings
from app.db import utcnow
from app.enums import ActorType, CaregiverScope, ConsentPurpose, ConsentStatus, Provenance
from app.models import CaregiverGrant, Clinic, Patient
from app.security import hash_token, new_token
from app.services.patients import normalise_phone, record_consent

SCOPE_LABELS = {
    CaregiverScope.VIEW_APPOINTMENTS: "See upcoming follow-ups and appointments",
    CaregiverScope.REQUEST_RESCHEDULE: "Ask for a new appointment time",
    CaregiverScope.RECEIVE_REMINDER_COPY: "Get a copy of reminders",
}


def invite(db: Session, clinic: Clinic, patient: Patient, name: str, phone: str, scopes: list[str]) -> tuple[CaregiverGrant, str]:
    valid = {s.value for s in CaregiverScope}
    scopes = sorted({s for s in scopes if s in valid})
    if not scopes:
        raise HTTPException(422, "Choose at least one permission.")
    if not name.strip():
        raise HTTPException(422, "Enter the caregiver's name.")
    token = new_token()
    grant = CaregiverGrant(clinic_id=clinic.id, patient_id=patient.id, caregiver_name=name.strip()[:120],
                           caregiver_phone=normalise_phone(phone), scopes=scopes, status="ACTIVE",
                           token_hash=hash_token(token), created_by="PATIENT",
                           expires_at=utcnow() + timedelta(days=90))
    db.add(grant)
    db.flush()
    record_consent(db, patient, ConsentPurpose.CAREGIVER_ACCESS, ConsentStatus.GRANTED, method="PATIENT_APP")
    link = f"{settings.public_app_url.rstrip('/')}/c/{token}"
    audit(db, clinic_id=clinic.id, action="CAREGIVER_GRANTED", actor_type=ActorType.PATIENT, actor_id=str(patient.id),
          object_type="caregiver_grant", object_id=grant.id, patient_id=patient.id, detail={"scopes": scopes})
    timeline(db, clinic_id=clinic.id, patient_id=patient.id, event_type="CAREGIVER_GRANTED",
             summary=f"Patient gave {grant.caregiver_name} limited access: " + "; ".join(SCOPE_LABELS[CaregiverScope(s)] for s in scopes),
             provenance=Provenance.PATIENT_REPORTED, actor_type=ActorType.PATIENT, actor_label="Patient",
             source_type="caregiver_grant", source_id=grant.id)
    return grant, link


def revoke(db: Session, patient: Patient, grant_id: uuid.UUID) -> CaregiverGrant:
    grant = db.get(CaregiverGrant, grant_id)
    if grant is None or grant.patient_id != patient.id:
        raise HTTPException(404, "Access not found.")
    if grant.status != "REVOKED":
        grant.status, grant.revoked_at = "REVOKED", utcnow()
        audit(db, clinic_id=grant.clinic_id, action="CAREGIVER_REVOKED", actor_type=ActorType.PATIENT,
              actor_id=str(patient.id), object_type="caregiver_grant", object_id=grant.id, patient_id=patient.id)
        timeline(db, clinic_id=grant.clinic_id, patient_id=patient.id, event_type="CAREGIVER_REVOKED",
                 summary=f"Patient revoked {grant.caregiver_name}'s access", provenance=Provenance.PATIENT_REPORTED,
                 actor_type=ActorType.PATIENT, actor_label="Patient", source_type="caregiver_grant", source_id=grant.id)
    return grant


def grants_for(db: Session, patient_id: uuid.UUID) -> list[dict]:
    rows = db.scalars(select(CaregiverGrant).where(CaregiverGrant.patient_id == patient_id)
                      .order_by(CaregiverGrant.created_at.desc())).all()
    return [{"id": str(g.id), "name": g.caregiver_name, "phone": g.caregiver_phone, "scopes": g.scopes,
             "scope_labels": [SCOPE_LABELS[CaregiverScope(s)] for s in g.scopes], "status": g.status,
             "expires_at": g.expires_at.isoformat(), "revoked_at": g.revoked_at.isoformat() if g.revoked_at else None}
            for g in rows]
