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


def test_rejected_date_alternative_does_not_hide_confirmed_date(nurse):
    pid=new_patient(nurse,'OCR date alternatives QA','+919000588814',plan_days=None)
    with SessionLocal() as db:
        patient=db.get(Patient,uuid.UUID(pid))
        document(db,patient,'older.png','2026-01-01','FBS: 100 mg/dL')
        artifact,proposal=document(db,patient,'newer.png','2026-02-01','FBS: 120 mg/dL')
        date_field=db.scalar(select(ExtractedField).where(ExtractedField.proposal_id==proposal.id))
        date_field.status='APPROVED'
        db.add(ExtractedField(clinic_id=patient.clinic_id,proposal_id=proposal.id,position=1,name='document_date',value='2027-12-01',proposed_value='2027-12-01',status='REJECTED'))
        db.commit();db.expire_all()
        result=latest(db,patient.id,patient.clinic_id)['readings'][0]
        assert result['value']=='120 mg/dL' and result['report_date']=='2026-02-01' and result['date_reviewed']


def test_extended_measurements_units_and_abstention():
    from app.services.health_readings import valid_value
    text="Serum creatinine: 1.2 mg/dL\neGFR: >90 mL/min/1.73m2\nUACR: 12 mg/g\nTotal cholesterol: 180 mg/dL\nLDL: 95 mg/dL\nHDL: 50 mg/dL\nTriglycerides: 130 mg/dL\nWeight: 72.5 kg"
    result=extract([{'text':text}])
    assert len(result)==8
    assert result['egfr'][0]=='>90 mL/min/1.73m²'
    for key,row in result.items():assert valid_value(key,row[0]),(key,row)
    assert not extract([{'text':'Weight: 70-80 kg\nLDL: <100 mg/dL\nUACR: 12\nReference total cholesterol: 150 mg/dL\nUrine creatinine: 100 mg/dL'}])
    assert not valid_value('weight','72 kg extra text')
    assert extract([{'text':'Serum creatinine: 90 umol/L'}])['creatinine'][0]=='90 µmol/L'
    assert extract([{'text':'UACR: 2 mg/mmol\nWeight: 150 lb'}])['uacr'][0]=='2 mg/mmol'


def test_extended_history_verification_roles_and_tenant_scope(nurse):
    from tests.conftest import login
    pid=new_patient(nurse,'Extended history QA','+919000588832',plan_days=None)
    with SessionLocal() as db:
        patient=db.get(Patient,uuid.UUID(pid))
        old,p1=document(db,patient,'kidney-old.png','2026-01-01','Serum creatinine: 1.1 mg/dL\nWeight: 73 kg')
        new,p2=document(db,patient,'kidney-new.png','2026-02-01','Serum creatinine: 1.2 mg/dL\nWeight: 72 kg')
        bad,p3=document(db,patient,'kidney-uncertain.png','2026-03-01','Serum creatinine: 9 mg/dL')
        db.add(ExtractedField(clinic_id=patient.clinic_id,proposal_id=p3.id,position=1,name='creatinine',value='9 mg/dL',proposed_value='9 mg/dL',status='NEEDS_REVIEW',review_reasons=['HANDWRITING_REQUIRES_REVIEW']))
        db.commit();db.expire_all()
        result=latest(db,patient.id,patient.clinic_id)
        assert next(r for r in result['readings'] if r['key']=='creatinine')['value']=='1.2 mg/dL'
        assert len([r for r in result['history'] if r['key']=='creatinine'])==2
        assert result['pending_verification_count']==1
        assert all(r['artifact_id']!=str(bad.id) for r in result['history'])
    staff=nurse.get(f'/v1/priorities/{pid}/health-readings')
    assert staff.status_code==200
    patient_session(nurse,'nurse@sunrise.demo',pid)
    patient_result=nurse.get('/v1/p/health-readings').json()
    assert patient_result['history']==staff.json()['history']
    assert nurse.get(f'/v1/priorities/{pid}/health-readings').status_code==401
    login(nurse,'reception@sunrise.demo')
    assert nurse.get(f'/v1/priorities/{pid}/health-readings').status_code==403
    login(nurse,'doctor@lakeview.demo')
    assert nurse.get(f'/v1/priorities/{pid}/health-readings').status_code==404
