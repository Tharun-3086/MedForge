"""Single-use phone login challenges with separate development and SMS modes."""
import hashlib
import hmac
import math
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


def development():
    return settings.patient_otp_provider == 'development' and settings.demo_mode and not settings.is_production


def available():
    from app.services import twilio_verify
    return development() or (settings.patient_otp_provider == "twilio" and twilio_verify.ready())


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


def request_code(db, phone, *, before_send=None):
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
        remaining = math.ceil(60 - (now-row.requested_at).total_seconds())
        if remaining > 0:
            raise HTTPException(429, f'Wait {remaining} seconds before requesting another code.',
                                headers={'Retry-After': str(remaining)})
    window_end = row.send_window_started_at + timedelta(hours=1) if row.send_window_started_at else now
    if row.send_count >= 5 and now < window_end:
        remaining = max(1, math.ceil((window_end-now).total_seconds()))
        raise HTTPException(429, 'This number has reached its hourly SMS limit. Use the latest code or wait for the countdown.',
                            headers={'Retry-After': str(remaining)})
    if before_send is not None:
        before_send()  # coarse IP backstop counts possible sends, never cooldown taps
    if created is None:
        for name, value in values.items():
            setattr(row, name, value)
    if settings.patient_otp_provider == 'twilio':
        from app.services import twilio_verify
        try:
            row.code_hash = 'twilio:' + twilio_verify.send(phone)
        except HTTPException:
            db.rollback()
            raise
    if now >= window_end:
        row.send_window_started_at, row.send_count = now, 0
    row.send_count += 1
    db.commit()
    result = {'challenge_id': str(challenge), 'expires_in_seconds': 300, 'resend_after_seconds': 60,
              'mode': settings.patient_otp_provider,
              'message': 'Enter the code sent by SMS. It expires in 5 minutes.'}
    if development():
        result.update(development_code=code, message='Development test code - no SMS sent. Only synthetic clinic records can be opened.')
    return result


def verify_code(db, phone, challenge_id, code):
    guard()
    phone = phone_number(phone)
    row = db.scalar(select(PatientOtpChallenge).where(PatientOtpChallenge.id == challenge_id,
        PatientOtpChallenge.phone_hash == digest(phone)).with_for_update())
    now = utcnow()
    if row is None or row.used_at or row.expires_at <= now or row.attempts >= 5:
        raise HTTPException(401, 'Code is invalid or expired. Request a new code.')
    if settings.patient_otp_provider == 'twilio':
        from app.services import twilio_verify
        try:
            valid = row.code_hash.startswith('twilio:') and twilio_verify.check(row.code_hash[7:], code)
        except HTTPException:
            db.rollback()  # provider downtime/rate limits are not incorrect-code attempts
            raise
    else:
        valid = not row.code_hash.startswith('twilio:') and hmac.compare_digest(row.code_hash, digest(f'{row.id}:{code}'))
    row.attempts += 1
    if not valid:
        if row.attempts >= 5:
            row.used_at = now
        db.commit()
        raise HTTPException(401, 'Code is invalid or expired. Request a new code.')
    row.used_at = now
    query = select(Patient).where(Patient.phone_e164 == phone)
    if development() or settings.demo_mode:
        query = query.where(Patient.is_synthetic.is_(True))
    matches = db.scalars(query).all()
    db.commit()
    return matches
