"""Magic links for the patient web app and consent helpers."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import utcnow
from app.enums import ConsentPurpose, ConsentStatus
from app.models import ConsentRecord, Patient, PatientAccessToken
from app.security import hash_token, new_token


def patient_link(db: Session, patient: Patient, days: int = 7) -> str:
    token = new_token()
    db.add(PatientAccessToken(clinic_id=patient.clinic_id, patient_id=patient.id, token_hash=hash_token(token),
                              expires_at=utcnow() + timedelta(days=days)))
    return f"{settings.public_app_url.rstrip('/')}/p/{token}"


def has_consent(db: Session, patient_id: uuid.UUID, purpose: str) -> bool:
    latest = db.scalar(select(ConsentRecord).where(ConsentRecord.patient_id == patient_id,
                                                   ConsentRecord.purpose == purpose)
                       .order_by(ConsentRecord.created_at.desc()).limit(1))
    return latest is not None and latest.status == ConsentStatus.GRANTED


def reminders_allowed(db: Session, patient: Patient) -> tuple[bool, str]:
    if patient.opted_out:
        return False, "OPTED_OUT"
    if not has_consent(db, patient.id, ConsentPurpose.REMINDERS):
        return False, "NO_MESSAGING_CONSENT"
    return True, ""
