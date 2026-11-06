import uuid
from sqlalchemy import select
from app.db import SessionLocal
from app.models import MessageTemplate

def payload():
    tag=uuid.uuid4().hex
    return dict(clinic_name="Fictional Signup "+tag,short_name="QA",owner_name="QA Owner",email=tag+"@example.test",password="test-password-clinic-2026")

def test_signup_owner_is_admin_of_empty_isolated_clinic(client):
    data=payload();r=client.post('/v1/auth/register-clinic',json=data)
    assert r.status_code==201
    me=r.json();assert me['user']['role']=='ADMIN' and me['clinic']['is_synthetic'] is True
    assert client.get('/v1/patients').json()['patients']==[]
    assert client.get('/v1/clinic/staff-access').status_code==200
    with SessionLocal() as db:
        statuses=db.scalars(select(MessageTemplate.status).where(MessageTemplate.clinic_id==uuid.UUID(me['clinic']['id']))).all()
        assert statuses and set(statuses)=={'DRAFT'}
    client.post('/v1/auth/logout')
    assert client.post('/v1/auth/login',json={'email':data['email'],'password':data['password']}).status_code==200
    assert client.post('/v1/auth/register-clinic',json=data).status_code==409

def test_signup_rejects_invalid_and_existing_accounts(client):
    data=payload();data['password']='short'
    assert client.post('/v1/auth/register-clinic',json=data).status_code==422
    data=payload();data['email']='admin@sunrise.demo'
    assert client.post('/v1/auth/register-clinic',json=data).status_code==409
    assert client.post('/v1/auth/login',json={'email':'admin@sunrise.demo','password':'niyamit-demo'}).status_code==200
