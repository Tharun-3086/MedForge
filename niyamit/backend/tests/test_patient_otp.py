import uuid
from datetime import timedelta
from sqlalchemy import select
from app.config import settings
from app.db import SessionLocal, utcnow
from app.models import PatientOtpChallenge, Patient
from tests.conftest import new_patient


def request(c, phone):
    r = c.post('/v1/p/otp/request', json={'phone': phone})
    assert r.status_code == 200, r.text
    return r.json()


def verify(c, phone, challenge, code=None):
    return c.post('/v1/p/otp/verify', json={'phone': phone, 'challenge_id': challenge['challenge_id'],
                                         'code': code or challenge['development_code']})


def test_otp_single_use_login_and_role_separation(nurse, seeded):
    phone='+919000410001'; pid=new_patient(nurse,'OTP Login',phone)
    nurse.cookies.clear(); ch=request(nurse,phone)
    assert ch['mode']=='development' and len(ch['development_code'])==6
    with SessionLocal() as db:
        row=db.scalar(select(PatientOtpChallenge).where(PatientOtpChallenge.id==uuid.UUID(ch['challenge_id'])))
        assert row.code_hash != ch['development_code'] and row.phone_hash != phone
    assert verify(nurse,phone,ch).json()['authenticated'] is True
    assert nurse.get('/v1/p/home').status_code==200
    assert nurse.get('/v1/patients').status_code==401
    assert verify(nurse,phone,ch).status_code==401
    nurse.post('/v1/p/logout')
    assert nurse.get('/v1/p/home').status_code==401


def test_otp_expiry_attempt_limit_and_wrong_phone(nurse, seeded):
    phone='+919000410002';new_patient(nurse,'OTP Attempts',phone);nurse.cookies.clear()
    ch=request(nurse,phone)
    assert verify(nurse,'+919000410099',ch).status_code==401
    bad='000000' if ch['development_code']!='000000' else '111111'
    for _ in range(5): assert verify(nurse,phone,ch,bad).status_code==401
    assert verify(nurse,phone,ch).status_code==401
    phone2='+919000410003';ch2=request(nurse,phone2)
    with SessionLocal() as db:
        row=db.scalar(select(PatientOtpChallenge).where(PatientOtpChallenge.id==uuid.UUID(ch2['challenge_id'])))
        row.expires_at=utcnow()-timedelta(seconds=1);db.commit()
    assert verify(nurse,phone2,ch2).status_code==401


def test_otp_resend_cooldown_invalidates_previous(nurse, seeded):
    phone='+919000410004';ch=request(nurse,phone)
    assert nurse.post('/v1/p/otp/request',json={'phone':phone}).status_code==429
    with SessionLocal() as db:
        row=db.scalar(select(PatientOtpChallenge).where(PatientOtpChallenge.id==uuid.UUID(ch['challenge_id'])))
        row.requested_at=utcnow()-timedelta(seconds=61);db.commit()
    newer=request(nurse,phone)
    assert newer['challenge_id']!=ch['challenge_id']
    assert verify(nurse,phone,ch).status_code==401


def test_development_otp_never_opens_real_records_or_production(nurse, seeded, monkeypatch):
    phone='+919000410005';pid=new_patient(nurse,'Real Flag Test',phone)
    with SessionLocal() as db:
        db.get(Patient,uuid.UUID(pid)).is_synthetic=False;db.commit()
    nurse.cookies.clear();ch=request(nurse,phone)
    assert verify(nurse,phone,ch).json()['authenticated'] is False
    assert nurse.get('/v1/p/home').status_code==401
    monkeypatch.setattr(settings,'app_env','production')
    assert nurse.post('/v1/p/otp/request',json={'phone':'+919000410006'}).status_code==503
    assert nurse.get('/v1/p/otp/config').json()['available'] is False


def test_otp_requires_explicit_choice_between_clinics(nurse, seeded):
    phone='+919000410007';pid=new_patient(nurse,'OTP Multi Clinic',phone)
    with SessionLocal() as db:
        other=Patient(clinic_id=uuid.UUID(seeded['clinic_b']),display_name='OTP Other Clinic',phone_e164=phone,
                      birth_year=1970,is_synthetic=True)
        db.add(other);db.commit()
    nurse.cookies.clear();ch=request(nurse,phone);r=verify(nurse,phone,ch)
    assert len(r.json()['profiles'])==2 and r.json()['authenticated'] is False
    assert nurse.get('/v1/p/home').status_code==401
    assert nurse.post('/v1/p/otp/select',json={'patient_id':str(uuid.uuid4())}).status_code==403
    assert nurse.post('/v1/p/otp/select',json={'patient_id':pid}).status_code==200
    assert nurse.get('/v1/p/home').json()['patient']['first_name']=='OTP'


def test_otp_rejects_invalid_phone(nurse, seeded):
    assert nurse.post('/v1/p/otp/request',json={'phone':'not-a-number'}).status_code==422
