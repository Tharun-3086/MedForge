import uuid
from app.services.health_readings import latest
from app.routers.priorities import state,fingerprint
from app.models import PatientPriority
from tests.conftest import new_patient,login

READING={'key':'fasting_glucose','value':'110 mg/dL','artifact_id':'source','clinic_reviewed':False,'report_date':'2026-10-01'}

def test_unverified_never_becomes_automatic_critical_or_routine():
    reading=dict(READING,value='999 mg/dL')
    assert state([reading],None)[0]=='VERIFY'
    a=PatientPriority(priority='URGENT',readings_hash=fingerprint([READING]))
    assert state([reading],a)==('URGENT',True,True)
    a.priority='ROUTINE'
    assert state([reading],a)[0]=='VERIFY'
    reviewed=dict(READING,clinic_reviewed=True)
    a.readings_hash=fingerprint([reviewed])
    assert state([reviewed],a)[0]=='ROUTINE'
    assert state([],None)[0]=='NOT_ASSESSED'
    assert state([reviewed],a,'new-report-version')[0]=='VERIFY'

def test_staff_priority_permissions_reason_and_clinic_scope(nurse):
    pid=new_patient(nurse,'Priority QA','+919000450001')
    path='/v1/priorities/'+pid
    assert nurse.put(path,json={'priority':'URGENT','reason':'Staff reviewed synthetic test concern'}).status_code==200
    rows=nurse.get('/v1/priorities').json()['rows']
    row=next(r for r in rows if r['patient_id']==pid)
    assert row['bucket']=='URGENT' and row['assessment']['reason']
    assert nurse.put(path,json={'priority':'ROUTINE','reason':'  '}).status_code==422
    assert nurse.put(path,json={'priority':'CRITICAL','reason':'Unsupported'}).status_code==422
    login(nurse,'admin@sunrise.demo')
    assert nurse.get('/v1/priorities').status_code==200
    assert nurse.put(path,json={'priority':'HIGH','reason':'Admin cannot set clinical priority'}).status_code==403
    login(nurse,'reception@sunrise.demo')
    assert nurse.get('/v1/priorities').status_code==403
    login(nurse,'doctor@lakeview.demo')
    assert all(r['patient_id']!=pid for r in nurse.get('/v1/priorities').json()['rows'])
    assert nurse.put(path,json={'priority':'HIGH','reason':'Other clinic'}).status_code==404


def test_routine_requires_verified_readings(nurse):
    from app.db import SessionLocal
    from app.models import Patient
    from tests.test_health_readings import document
    pid=new_patient(nurse,'Priority OCR QA','+919000450002')
    with SessionLocal() as db:
        document(db,db.get(Patient,uuid.UUID(pid)),'unverified.png','2026-10-01','FBS: 110 mg/dL')
        db.commit()
    assert nurse.put('/v1/priorities/'+pid,json={'priority':'ROUTINE','reason':'Must not bypass verification'}).status_code==409
    row=next(r for r in nurse.get('/v1/priorities',params={'limit':100}).json()['rows'] if r['patient_id']==pid)
    assert row['bucket']=='VERIFY'
