"""OTP retries must not exhaust SMS quotas or block unrelated patients."""
import uuid
from datetime import timedelta

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal, utcnow
from app.models import PatientOtpChallenge
from app.services import twilio_verify


def challenge_row(db, phone):
    from app.services.patient_otp import digest
    return db.scalar(select(PatientOtpChallenge).where(PatientOtpChallenge.phone_hash == digest(phone)))


def allow_resend(phone):
    with SessionLocal() as db:
        challenge_row(db, phone).requested_at = utcnow() - timedelta(seconds=61)
        db.commit()


def test_cooldown_taps_do_not_consume_phone_quota(client):
    phone = '+919000510001'
    first = client.post('/v1/p/otp/request', json={'phone': phone})
    assert first.status_code == 200
    for _ in range(12):
        blocked = client.post('/v1/p/otp/request', json={'phone': phone})
        assert blocked.status_code == 429
        assert 1 <= int(blocked.headers['retry-after']) <= 60
    with SessionLocal() as db:
        assert challenge_row(db, phone).send_count == 1
    allow_resend(phone)
    assert client.post('/v1/p/otp/request', json={'phone': phone}).status_code == 200
    with SessionLocal() as db:
        assert challenge_row(db, phone).send_count == 2


def test_successful_send_limit_is_durable_and_resets_after_hour(client):
    phone = '+919000510002'
    for _ in range(5):
        response = client.post('/v1/p/otp/request', json={'phone': phone})
        assert response.status_code == 200
        allow_resend(phone)
    last_id = response.json()['challenge_id']
    blocked = client.post('/v1/p/otp/request', json={'phone': phone})
    assert blocked.status_code == 429 and int(blocked.headers['retry-after']) > 60
    # Clearing the optional process limiter cannot reset this DB-backed phone quota.
    from app.security import _local_counters
    _local_counters.clear()
    assert client.post('/v1/p/otp/request', json={'phone': phone}).status_code == 429
    with SessionLocal() as db:
        row = challenge_row(db, phone)
        assert row.send_count == 5 and str(row.id) == last_id
        row.send_window_started_at = utcnow() - timedelta(hours=1, seconds=1)
        db.commit()
    assert client.post('/v1/p/otp/request', json={'phone': phone}).status_code == 200
    with SessionLocal() as db:
        assert challenge_row(db, phone).send_count == 1


def test_shared_network_allows_distinct_patients_and_cooldown_checks_run_first(client, monkeypatch):
    from app import redis_client
    from app.security import _local_counters
    monkeypatch.setattr(settings, 'rate_limits_enabled', True)

    def unavailable():
        raise ConnectionError('offline test')

    monkeypatch.setattr(redis_client, 'get_redis', unavailable)
    _local_counters.clear()
    try:
        for i in range(12):
            phone = f'+91900052{i:04d}'
            assert client.post('/v1/p/otp/request', json={'phone': phone}).status_code == 200
        for _ in range(8):
            assert client.post('/v1/p/otp/request', json={'phone': phone}).status_code == 429
        send_counts = [count for key, (count, _) in _local_counters.items() if 'otp-send-ip:' in key]
        assert sum(send_counts) == 12  # no 10-tap shared proxy cap, no quota cost for cooldown taps
    finally:
        _local_counters.clear()


def test_provider_outage_preserves_previous_challenge_and_quota(client, monkeypatch):
    phone = '+919000510003'
    first = client.post('/v1/p/otp/request', json={'phone': phone}).json()
    allow_resend(phone)
    monkeypatch.setattr(settings, 'patient_otp_provider', 'twilio')
    monkeypatch.setattr(settings, 'twilio_account_sid', 'AC'+'1'*32)
    monkeypatch.setattr(settings, 'twilio_auth_token', 'test-only')
    monkeypatch.setattr(settings, 'twilio_verify_service_sid', 'VA'+'2'*32)

    def fail(_):
        raise HTTPException(503, 'Test outage', headers={'Retry-After': '60'})

    monkeypatch.setattr(twilio_verify, 'send', fail)
    failed = client.post('/v1/p/otp/request', json={'phone': phone})
    assert failed.status_code == 503 and failed.headers['retry-after'] == '60'
    with SessionLocal() as db:
        row = challenge_row(db, phone)
        assert str(row.id) == first['challenge_id'] and row.send_count == 1


def test_provider_check_throttle_is_not_a_wrong_code_attempt(client, monkeypatch):
    phone = '+919000510004'
    challenge = client.post('/v1/p/otp/request', json={'phone': phone}).json()
    with SessionLocal() as db:
        challenge_row(db, phone).code_hash = 'twilio:VE'+'3'*32
        db.commit()
    monkeypatch.setattr(settings, 'patient_otp_provider', 'twilio')
    monkeypatch.setattr(settings, 'twilio_account_sid', 'AC'+'1'*32)
    monkeypatch.setattr(settings, 'twilio_auth_token', 'test-only')
    monkeypatch.setattr(settings, 'twilio_verify_service_sid', 'VA'+'2'*32)

    def blocked(*_):
        raise HTTPException(429, 'Provider temporarily limited', headers={'Retry-After': '600'})

    monkeypatch.setattr(twilio_verify, 'check', blocked)
    response = client.post('/v1/p/otp/verify', json={'phone': phone, 'challenge_id': challenge['challenge_id'], 'code': '123456'})
    assert response.status_code == 429
    with SessionLocal() as db:
        assert challenge_row(db, phone).attempts == 0


@pytest.mark.parametrize('code', [60202, 60203, 60245])
def test_twilio_limit_exposes_safe_retry_time_without_provider_body(monkeypatch, code):
    monkeypatch.setattr(httpx, 'post', lambda *a, **k: httpx.Response(429, json={'code': code, 'message': 'secret account details'}))
    with pytest.raises(HTTPException) as error:
        twilio_verify.send('+919000510005')
    assert error.value.status_code == 429 and error.value.headers['Retry-After'] == '600'
    assert 'secret' not in error.value.detail


def test_twilio_trial_restriction_is_actionable(monkeypatch):
    monkeypatch.setattr(httpx, 'post', lambda *a, **k: httpx.Response(400, json={'code': 21608, 'message': 'secret provider details'}))
    with pytest.raises(HTTPException) as error:
        twilio_verify.send('+919000510006')
    assert error.value.status_code == 422 and 'Twilio trial' in error.value.detail
    assert 'secret' not in error.value.detail


def test_generic_limiter_reports_real_reset_time(monkeypatch):
    from app import security, redis_client
    monkeypatch.setattr(settings, 'rate_limits_enabled', True)
    monkeypatch.setattr(security.time, 'time', lambda: 3700.1)
    monkeypatch.setattr(redis_client, 'get_redis', lambda: (_ for _ in ()).throw(ConnectionError()))
    security._local_counters.clear()
    try:
        security.rate_limit('test-reset', 1, 3600)
        with pytest.raises(HTTPException) as error:
            security.rate_limit('test-reset', 1, 3600)
        assert error.value.headers['Retry-After'] == '3500'
        assert '3500' in error.value.detail
    finally:
        security._local_counters.clear()
