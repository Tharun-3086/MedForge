"""Connected appointment replies and atomic changes on a separate PostgreSQL test DB."""
import uuid
from datetime import timedelta
import pytest
from sqlalchemy import select, func
from app.db import SessionLocal, utcnow
from app.models import Appointment, AppointmentRequest, AvailabilitySlot, CareTask, FollowUpItem
from tests.conftest import new_patient, patient_session, login


def scenario(client,number):
    login(client,'nurse@sunrise.demo')
    pid=new_patient(client,'Appointment Actions QA',number,plan_days=5)
    start=(utcnow()+timedelta(days=10)).replace(hour=5,minute=30,second=0,microsecond=0)
    provider='QA room '+number[-4:]
    slot=client.post('/v1/availability',json={'starts_at':start.isoformat(),'provider_label':provider})
    assert slot.status_code==201,slot.text
    booked=client.post('/v1/appointments',json={'patient_id':pid,'slot_id':slot.json()['id'],'client_key':'initial-'+number})
    assert booked.status_code==200,booked.text
    appointment=booked.json()['appointment']
    patient_session(client,'nurse@sunrise.demo',pid)
    response=client.post(f"/v1/p/appointments/{appointment['id']}/response",json={'choice':'CANNOT_ATTEND','reason':'FEELING_WELL'})
    assert response.status_code==200,response.text
    login(client,'doctor@sunrise.demo')
    task=client.get('/v1/tasks',params={'patient_id':pid,'category':'BARRIER'}).json()['tasks'][0]
    return pid,appointment,task,start,provider


def test_appointment_reply_is_visible_with_request_status_and_scoped(nurse):
    pid,appointment,task,_,_=scenario(nurse,'+919000494001')
    path=f"/v1/tasks/{task['id']}/reply"
    message={'text':'We received your attendance concern and will call you to discuss it.'}
    detail=nurse.get(f"/v1/tasks/{task['id']}").json()
    assert detail['can_reply'] and detail['appointment_options'][0]['id']==appointment['id']
    assert nurse.post(path,json=message).status_code==200
    login(nurse,'doctor@lakeview.demo')
    assert nurse.post(path,json=message).status_code==404
    login(nurse,'admin@sunrise.demo')
    assert nurse.post(path,json=message).status_code==403
    patient_session(nurse,'nurse@sunrise.demo',pid)
    home=nurse.get('/v1/p/home').json()
    request=next(r for r in home['appointment_requests'] if r['id']==task['id'])
    assert request['status']=='IN_PROGRESS' and request['reply']['text']==message['text']
    assert any(r['text']==message['text'] for r in home['clinician_replies'])
    login(nurse,'doctor@sunrise.demo')
    other=new_patient(nurse,'Reply Isolation QA','+919000494007',plan_days=None)
    patient_session(nurse,'doctor@sunrise.demo',other)
    assert not nurse.get('/v1/p/home').json()['appointment_requests']
    assert not nurse.get('/v1/p/home').json()['appointment_updates']


def test_cancel_notifies_patient_resolves_task_and_retries_safely(nurse):
    pid,appointment,task,_,_=scenario(nurse,'+919000494002')
    patient_session(nurse,'doctor@sunrise.demo',pid)
    assert nurse.post(f"/v1/p/appointments/{appointment['id']}/response",json={'choice':'RESCHEDULE'}).status_code==200
    login(nurse,'doctor@sunrise.demo')
    path=f"/v1/tasks/{task['id']}/appointment-action"
    body={'action':'CANCEL','appointment_id':appointment['id'],'message':'The appointment is cancelled. Please contact us to arrange your next visit.'}
    result=nurse.post(path,json=body)
    assert result.status_code==200,result.text
    assert result.json()['status']=='RESOLVED' and result.json()['outcome']=='APPOINTMENT_CANCELLED'
    assert nurse.post(path,json=body).status_code==200
    with SessionLocal() as db:
        appt=db.get(Appointment,uuid.UUID(appointment['id']))
        assert appt.status=='CANCELLED'
        assert db.get(AvailabilitySlot,appt.slot_id).status=='OPEN'
        assert db.get(FollowUpItem,appt.item_id).status=='PENDING'
    patient_session(nurse,'nurse@sunrise.demo',pid)
    home=nurse.get('/v1/p/home').json()
    assert not home['appointments']
    assert len(home['appointment_updates'])==1 and 'cancelled' in home['appointment_updates'][0]['text']
    assert all(r['status']=='RESOLVED' for r in home['appointment_requests'])
    assert next(r for r in home['appointment_requests'] if r['id']==task['id'])['reply']['text']==body['message']


@pytest.mark.parametrize('action,days,phone',[('POSTPONE',2,'+919000494003'),('PREPONE',-2,'+919000494004')])
def test_move_books_replacement_then_releases_original_and_updates_patient(nurse,action,days,phone):
    pid,appointment,task,start,provider=scenario(nurse,phone)
    new=nurse.post('/v1/availability',json={'starts_at':(start+timedelta(days=days)).isoformat(),'provider_label':provider}).json()
    body={'action':action,'appointment_id':appointment['id'],'slot_id':new['id'],'message':'Your appointment has been moved to the confirmed time shown in your app.'}
    path=f"/v1/tasks/{task['id']}/appointment-action"
    result=nurse.post(path,json=body)
    assert result.status_code==200,result.text
    replacement=result.json()['appointment']
    assert replacement['id']!=appointment['id']
    assert nurse.post(path,json=body).json()['appointment']['id']==replacement['id']
    with SessionLocal() as db:
        old=db.get(Appointment,uuid.UUID(appointment['id']))
        assert old.status=='CANCELLED' and db.get(AvailabilitySlot,old.slot_id).status=='OPEN'
        assert db.get(Appointment,uuid.UUID(replacement['id'])).status=='CONFIRMED'
        assert db.get(FollowUpItem,old.item_id).status=='BOOKED'
        assert db.get(AppointmentRequest,old.request_id).status=='CANCELLED'
        assert db.scalar(select(func.count()).select_from(Appointment).where(Appointment.patient_id==uuid.UUID(pid)))==2
    patient_session(nurse,'nurse@sunrise.demo',pid)
    home=nurse.get('/v1/p/home').json()
    assert [a['id'] for a in home['appointments']]==[replacement['id']]
    assert home['appointment_requests'][0]['outcome']=='APPOINTMENT_'+('POSTPONED' if days>0 else 'PREPONED')
    assert next(r for r in home['appointment_requests'] if r['id']==task['id'])['reply']['text']==body['message']


def test_wrong_direction_or_taken_replacement_preserves_original(nurse):
    pid,appointment,task,start,provider=scenario(nurse,'+919000494005')
    new=nurse.post('/v1/availability',json={'starts_at':(start+timedelta(days=2)).isoformat(),'provider_label':provider}).json()
    path=f"/v1/tasks/{task['id']}/appointment-action"
    body={'action':'PREPONE','appointment_id':appointment['id'],'slot_id':new['id'],'message':'Test replacement'}
    assert nurse.post(path,json=body).status_code==422
    other=new_patient(nurse,'Other Booking QA','+919000494006',plan_days=None)
    assert nurse.post('/v1/appointments',json={'patient_id':other,'slot_id':new['id'],'client_key':'occupy-replacement'}).status_code==200
    assert nurse.post(path,json={**body,'action':'POSTPONE'}).status_code==409
    with SessionLocal() as db:
        assert db.get(Appointment,uuid.UUID(appointment['id'])).status=='CONFIRMED'
        assert db.get(CareTask,uuid.UUID(task['id'])).status=='OPEN'
    login(nurse,'doctor@lakeview.demo')
    assert nurse.post(path,json={**body,'action':'CANCEL'}).status_code==404
    login(nurse,'admin@sunrise.demo')
    assert nurse.post(path,json={**body,'action':'CANCEL'}).status_code==403
