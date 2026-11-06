import uuid
import pytest
import httpx
from fastapi import HTTPException
from app.config import settings
from app.services import twilio_verify
from tests.conftest import new_patient

@pytest.fixture
def sms(monkeypatch):
    monkeypatch.setattr(settings,"patient_otp_provider","twilio")
    monkeypatch.setattr(settings,"twilio_account_sid","AC"+"1"*32)
    monkeypatch.setattr(settings,"twilio_auth_token","test-only")
    monkeypatch.setattr(settings,"twilio_verify_service_sid","VA"+"2"*32)

def test_sms_login_no_code_exposure_and_single_use(nurse,sms,monkeypatch):
    phone='+919000480001';new_patient(nurse,'SMS Test',phone)
    monkeypatch.setattr(twilio_verify,'send',lambda phone:'VE'+'3'*32)
    monkeypatch.setattr(twilio_verify,'check',lambda sid,code:code=='123456')
    assert nurse.get('/v1/p/otp/config').json()=={'available':True,'development':False}
    challenge=nurse.post('/v1/p/otp/request',json={'phone':phone}).json()
    assert 'development_code' not in challenge and challenge['mode']=='twilio'
    data={'phone':phone,'challenge_id':challenge['challenge_id'],'code':'000000'}
    assert nurse.post('/v1/p/otp/verify',json=data).status_code==401
    data['code']='123456'
    assert nurse.post('/v1/p/otp/verify',json=data).json()['authenticated']
    assert nurse.post('/v1/p/otp/verify',json=data).status_code==401

def test_sms_failure_never_falls_back_to_dev(nurse,sms,monkeypatch):
    def fail(phone):raise HTTPException(503,'SMS unavailable')
    monkeypatch.setattr(twilio_verify,'send',fail)
    r=nurse.post('/v1/p/otp/request',json={'phone':'+919000480002'})
    assert r.status_code==503 and 'development_code' not in r.text

def test_adapter_uses_provider_sid_and_approved_status(sms,monkeypatch):
    calls=[]
    def post(url,**kw):
        calls.append((url,kw['data']))
        return httpx.Response(200,json={'status':'pending','sid':'VE'+'3'*32} if url.endswith('/Verifications') else {'status':'approved'})
    monkeypatch.setattr(httpx,'post',post)
    sid=twilio_verify.send('+919000480003');assert twilio_verify.check(sid,'123456')
    assert calls[1][1]=={'VerificationSid':sid,'Code':'123456'}

def test_adapter_failure_redacts_provider_body(sms,monkeypatch):
    monkeypatch.setattr(httpx,'post',lambda *a,**k:httpx.Response(500,text='secret provider body'))
    with pytest.raises(HTTPException) as exc:twilio_verify.send('+919000480004')
    assert 'secret' not in exc.value.detail


def test_sms_real_record_access_requires_provider_approval(nurse,sms,monkeypatch):
    from app.db import SessionLocal
    from app.models import Patient
    phone='+919000480005';pid=new_patient(nurse,'Fictional Real Mode SMS',phone)
    with SessionLocal() as db:
        db.get(Patient,uuid.UUID(pid)).is_synthetic=False;db.commit()
    monkeypatch.setattr(settings,'demo_mode',False)
    monkeypatch.setattr(twilio_verify,'send',lambda phone:'VE'+'4'*32)
    monkeypatch.setattr(twilio_verify,'check',lambda sid,code:code=='123456')
    c=nurse.post('/v1/p/otp/request',json={'phone':phone}).json()
    r=nurse.post('/v1/p/otp/verify',json={'phone':phone,'challenge_id':c['challenge_id'],'code':'123456'})
    assert r.status_code==200 and r.json()['authenticated']
