import uuid
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Patient, SourceArtifact, ExtractionProposal, ExtractedField, PatientAccessToken
from app.config import settings
from tests.conftest import new_patient, patient_session, login


def remove(c,pid,name):
    return c.request('DELETE','/v1/patients/'+pid,json={'confirm_name':name})


def test_remove_patient_clears_history_revokes_session_and_reuses_phone(nurse):
    pid=new_patient(nurse,'Disposable QA','+919000470080')
    data=b'Report date,FBS\n2026-11-12,75 mg/dL\n'
    r=nurse.post('/v1/intake-artifacts',data={'patient_id':pid,'source_type':'LAB_REPORT'},files={'file':('test.csv',data,'text/csv')})
    assert r.status_code==201
    proposal_id=r.json()['id'];artifact_id=r.json()['artifact']['id']
    patient_session(nurse,'nurse@sunrise.demo',pid)
    cookie=nurse.cookies.get('nyt_patient')
    login(nurse,'doctor@sunrise.demo')
    assert nurse.get('/v1/patients/'+pid).json()['can_remove_test_patient']
    assert remove(nurse,pid,'Wrong name').status_code==422
    r=remove(nurse,pid,'Disposable QA');assert r.status_code==200,r.text
    assert r.json()['file_cleanup_pending']==0
    assert nurse.get('/v1/patients/'+pid).status_code==404
    with SessionLocal() as db:
        assert db.get(Patient,uuid.UUID(pid)) is None
        assert db.get(ExtractionProposal,uuid.UUID(proposal_id)) is None
        assert not db.scalars(select(ExtractedField).where(ExtractedField.proposal_id==uuid.UUID(proposal_id))).all()
        artifact=db.get(SourceArtifact,uuid.UUID(artifact_id))
        assert artifact.patient_id is None and artifact.deleted_at is not None
    nurse.cookies.set('nyt_patient',cookie)
    assert nurse.get('/v1/p/health-readings').status_code==401
    fresh=new_patient(nurse,'Disposable QA Again','+919000470080',plan_days=None)
    assert fresh!=pid
    assert nurse.get(f'/v1/priorities/{fresh}/health-readings').json()['readings']==[]


def test_removal_is_scoped_role_restricted_and_production_disabled(nurse,monkeypatch):
    pid=new_patient(nurse,'Removal guard QA','+919000470081',plan_days=None)
    assert remove(nurse,pid,'Removal guard QA').status_code==403
    login(nurse,'doctor@lakeview.demo')
    assert remove(nurse,pid,'Removal guard QA').status_code==404
    login(nurse,'doctor@sunrise.demo')
    monkeypatch.setattr(settings,'demo_mode',False)
    assert remove(nurse,pid,'Removal guard QA').status_code==403
    monkeypatch.setattr(settings,'demo_mode',True)
    with SessionLocal() as db:
        p=db.get(Patient,uuid.UUID(pid));p.is_synthetic=False;db.commit()
    assert remove(nurse,pid,'Removal guard QA').status_code==403


def test_showcase_patient_is_protected(nurse):
    login(nurse,'doctor@sunrise.demo')
    rows=nurse.get('/v1/patients?q=Ramesh').json()['patients']
    ramesh=next(p for p in rows if p['external_ref']=='SDC-1001')
    assert not nurse.get('/v1/patients/'+ramesh['id']).json()['can_remove_test_patient']
    assert remove(nurse,ramesh['id'],ramesh['name']).status_code==403
