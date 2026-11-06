from app.config import settings
from tests.conftest import login

def test_billing_admin_only_and_tenant_isolation(client):
    login(client,'nurse@sunrise.demo');assert client.get('/v1/billing').status_code==403
    assert client.post('/v1/billing/simulate',json={'plan_key':'starter'}).status_code==403
    login(client,'admin@sunrise.demo');before=client.get('/v1/billing').json()
    assert before['simulation'] is True and before['active_patients']>0
    assert client.post('/v1/billing/simulate',json={'plan_key':'starter','monthly_paise':1}).status_code==200
    result=client.get('/v1/billing').json();assert result['invoices'][0]['amount_paise']==99900
    assert result['invoices'][0]['status']=='SIMULATED_NO_PAYMENT'
    count=len(result['invoices']);client.post('/v1/billing/simulate',json={'plan_key':'starter'})
    assert len(client.get('/v1/billing').json()['invoices'])==count
    login(client,'admin@lakeview.demo');assert client.get('/v1/billing').json()['subscription'] is None

def test_demo_activation_disabled_in_real_mode(client,monkeypatch):
    login(client,'admin@sunrise.demo');monkeypatch.setattr(settings,'demo_mode',False)
    assert client.get('/v1/billing').json()['selection_enabled'] is False
    assert client.post('/v1/billing/simulate',json={'plan_key':'growth'}).status_code==403
    assert client.post('/v1/billing/simulate',json={'plan_key':'unknown'}).status_code==422
