import uuid
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Patient,SourceArtifact,ExtractionProposal,ExtractedField
from app.services.health_readings import extract,latest,report_date_from_text
from tests.conftest import new_patient,patient_session

def test_conservative_reading_parser():
    assert str(report_date_from_text([{'text':'Document date: 2026-10-02'}]))=='2026-10-02'
    assert report_date_from_text([{'text':'Report date: 2026-10-02 Document date: 2026-10-01'}]) is None
    result=extract([{'id':'x','text':'BP: 120/80 mmHg\nFBS: 110 mg/dL\nPPBS: 7.2 mmol/L\nHbA1c: 6.2 %'}])
    assert result['blood_pressure'][0]=='120/80 mmHg'
    assert result['fasting_glucose'][0]=='110 mg/dL'
    assert result['postmeal_glucose'][0]=='7.2 mmol/L'
    assert 'blood_glucose' not in result
    assert not extract([{'text':'FBS: 70-100 mg/dL\nHbA1c: <6 %\nBP: 120/80\nGlucose: 110'}])
    assert not extract([{'text':'FBS: 110 mg/dL\nFBS: 140 mg/dL'}])

def document(db,patient,filename,when,text):
    artifact=SourceArtifact(clinic_id=patient.clinic_id,patient_id=patient.id,source_type='LAB_REPORT',filename=filename,mime_type='image/png',size_bytes=1,sha256='0'*64,storage_key='test')
    db.add(artifact);db.flush()
    proposal=ExtractionProposal(clinic_id=patient.clinic_id,patient_id=patient.id,artifact_id=artifact.id,status='NEEDS_REVIEW',blocks=[{'id':'line','text':text}])
    db.add(proposal);db.flush()
    db.add(ExtractedField(clinic_id=patient.clinic_id,proposal_id=proposal.id,position=0,name='document_date',value=when,proposed_value=when,status='UNVERIFIED'))
    db.flush();return artifact,proposal

def test_latest_by_report_date_missing_values_and_clinic_correction(nurse):
    pid=new_patient(nurse,'Readings QA','+919000470001')
    with SessionLocal() as db:
        patient=db.get(Patient,uuid.UUID(pid))
        old,_=document(db,patient,'older.png','2026-10-01','BP: 120/80 mmHg\nFBS: 110 mg/dL')
        newer,proposal=document(db,patient,'newer.png','2026-10-02','FBS: 130 mg/dL')
        document(db,patient,'old-uploaded-last.png','2026-09-01','FBS: 90 mg/dL')
        document(db,patient,'undated.png',None,'FBS: 150 mg/dL')
        db.commit();db.expire_all();result={r['key']:r for r in latest(db,patient.id,patient.clinic_id)['readings']}
        assert result['fasting_glucose']['value']=='130 mg/dL'
        assert result['blood_pressure']['artifact_id']==str(old.id)
        db.add(ExtractedField(clinic_id=patient.clinic_id,proposal_id=proposal.id,position=1,name='fasting_glucose',value='125 mg/dL',proposed_value='130 mg/dL',extracted_value='FBS: 130 mg/dL',status='APPROVED'))
        db.commit();db.expire_all();result={r['key']:r for r in latest(db,patient.id,patient.clinic_id)['readings']}
        assert result['fasting_glucose']['value']=='125 mg/dL' and result['fasting_glucose']['clinic_reviewed']
    patient_session(nurse,'nurse@sunrise.demo',pid)
    assert len(nurse.get('/v1/p/health-readings').json()['readings'])==2

def test_patient_readings_are_scoped(nurse):
    pid=new_patient(nurse,'Readings Other','+919000470002')
    patient_session(nurse,'nurse@sunrise.demo',pid)
    assert nurse.get('/v1/p/health-readings').json()['readings']==[]
