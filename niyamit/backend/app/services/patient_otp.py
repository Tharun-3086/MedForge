"""Development OTP only. No SMS claim, no real records, no automatic clinic linking."""
import hashlib
import hmac
import re
import secrets
import uuid
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.config import settings
from app.db import utcnow
from app.models import PatientOtpChallenge, Patient


def available():
    return settings.patient_otp_provider == 'development' and settings.demo_mode and not settings.is_production


def guard():
    if not available():
        raise HTTPException(503, 'Phone login is not configured. Ask your clinic for access.')


def phone_number(value):
    value = re.sub(r'[\s()-]', '', value)
    if re.fullmatch(r'[6-9]\d{9}', value):
        value = '+91' + value
    if not re.fullmatch(r'\+[1-9]\d{7,14}', value):
        raise HTTPException(422, 'Enter a phone number with country code, such as +91 followed by 10 digits.')
    return value


def digest(value):
    return hmac.new(settings.secret_key.encode(), ('patient-otp:' + value).encode(), hashlib.sha256).hexdigest()


def request_code(db, phone):
    guard()
    phone = phone_number(phone)
    now = utcnow(); key = digest(phone); challenge = uuid.uuid4()
    code = f'{secrets.randbelow(1000000):06d}'
    values = dict(phone_hash=key, id=challenge, code_hash=digest(f'{challenge}:{code}'),
                  requested_at=now, expires_at=now+timedelta(minutes=5), attempts=0, used_at=None)
    created = db.scalar(insert(PatientOtpChallenge).values(**values).on_conflict_do_nothing(
        index_elements=['phone_hash']).returning(PatientOtpChallenge.id))
    row = db.scalar(select(PatientOtpChallenge).where(PatientOtpChallenge.phone_hash == key).with_for_update())
    if created is None:
        if (now-row.requested_at).total_seconds() < 60:
            raise HTTPException(429, 'Wait 60 seconds before requesting another code.')
        for name, value in values.items():
            setattr(row, name, value)
    db.commit()
    return {'challenge_id': str(challenge), 'expires_in_seconds': 300, 'resend_after_seconds': 60,
            'mode': 'development', 'development_code': code,
            'message': 'Development test code — no SMS sent. Only synthetic clinic records can be opened.'}


def verify_code(db, phone, challenge_id, code):
    guard()
    phone = phone_number(phone)
    row = db.scalar(select(PatientOtpChallenge).where(PatientOtpChallenge.id == challenge_id,
        PatientOtpChallenge.phone_hash == digest(phone)).with_for_update())
    now = utcnow()
    if row is None or row.used_at or row.expires_at <= now or row.attempts >= 5:
        raise HTTPException(401, 'Code is invalid or expired. Request a new code.')
    row.attempts += 1
    if not hmac.compare_digest(row.code_hash, digest(f'{row.id}:{code}')):
        if row.attempts >= 5:
            row.used_at = now
        db.commit()
        raise HTTPException(401, 'Code is invalid or expired. Request a new code.')
    row.used_at = now
    matches = db.scalars(select(Patient).where(Patient.phone_e164 == phone, Patient.is_synthetic.is_(True))).all()
    db.commit()
    return matches
