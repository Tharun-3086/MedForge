"""Additional results are source-backed proposals, never self-approved AI output."""
import uuid
from datetime import timedelta
from sqlalchemy import select, func
from app.ai.pipeline import measurement_fields
from app.db import SessionLocal
from app.models import Patient, Appointment
from tests.conftest import new_patient, patient_session, login, clinic_today
from tests.test_health_readings import document


def test_additional_lab_row_review_reaches_both_dashboards_and_is_idempotent(nurse):
    pid=new_patient(nurse,'Additional Laboratory QA','+919000492001',plan_days=None)
    with SessionLocal() as db:
        patient=db.get(Patient,uuid.UUID(pid))
        _,proposal=document(db,patient,'synthetic-uric-acid.png','2026-11-12',
            'S. URIC ACID 4.6 mg/dL\nBlood urea 20 mg/dL\nReference 3.4 mg/dL\nMetformin 500 mg')
        proposal.blocks=[{'id':'row','page':1,'text':proposal.blocks[0]['text'],'ocr_conf':.99}]
        proposal_id=str(proposal.id);db.commit()
    path=f'/v1/intake-proposals/{proposal_id}'
    response=nurse.post(path+'/find-lab-results')
    assert response.status_code==200,response.text
    fields=response.json()['fields']
    custom=[f for f in fields if f['name']=='unmapped_measurement']
    assert len(custom)==2
    assert len(nurse.post(path+'/find-lab-results').json()['fields'])==len(fields)
    uric=next(f for f in custom if 'URIC' in f['evidence']['parameter'])
    assert nurse.patch(path+f"/fields/{uric['id']}",json={'action':'APPROVE','reason':'Checked original'}).status_code==422
    corrected=nurse.patch(path+f"/fields/{uric['id']}",json={'action':'CORRECT','value':'4.6 mg/dL',
        'measurement_name':'Serum uric acid','reason':'Compared name, result and unit with the source row'})
    assert corrected.status_code==200,corrected.text
    staff=nurse.get(f'/v1/priorities/{pid}/health-readings').json()['readings']
    result=next(r for r in staff if r['label']=='Serum uric acid')
    assert result['value']=='4.6 mg/dL' and result['clinic_reviewed']
    patient_session(nurse,'nurse@sunrise.demo',pid)
    patient=nurse.get('/v1/p/health-readings').json()['readings']
    assert any(r['label']=='Serum uric acid' and r['value']=='4.6 mg/dL' for r in patient)
    assert nurse.get('/v1/p/diabetes-summary').status_code==200
    login(nurse,'admin@sunrise.demo')
    assert nurse.post(path+'/find-lab-results').status_code==403
    login(nurse,'doctor@lakeview.demo')
    assert nurse.post(path+'/find-lab-results').status_code==404


def test_generic_unknown_tests_are_separate_and_require_explicit_units():
    fields=measurement_fields([{'id':'r','page':1,'text':'S. URIC ACID 4.6 mg/dL\nPotassium 4.6 mmol/L\nMetformin 500 mg\nBlood urea 20\nNormal range 3.4 mg/dL'}])
    assert len(fields)==2 and all(f.status=='NEEDS_REVIEW' for f in fields)
    assert {f.evidence['parameter'] for f in fields}=={'S. URIC ACID','Potassium'}
    uncertain=measurement_fields([{'id':'r','page':1,'text':'S. URIC ACID 4.6 ng/dl'}])
    assert len(uncertain)==1 and uncertain[0].value=='4.6 ng/dL'  # never silently change the OCR unit
    assert not measurement_fields([{'id':'r','page':1,'text':'FASTING BLOOD 75 ng/dl\nSUGAR'}])  # incomplete label is not a new test
    from app.services.health_readings import custom_reading
    from app.services.diabetes_analysis import comparisons
    key,label,_=custom_reading('Serum uric acid','4.6 mg/dL')
    assert key!=custom_reading('Serum uric acid','0.27 mmol/L')[0]
    history=[{'key':key,'label':label,'value':value,'clinic_reviewed':True,'date_reviewed':True,'report_date':day}
             for value,day in [('4.5 mg/dL','2026-10-01'),('4.6 mg/dL','2026-11-01')]]
    assert comparisons(history)[0]['label']=='Serum uric acid'


def test_conversation_assistant_proposes_but_never_books(nurse):
    pid=new_patient(nurse,'Conversation Assistant QA','+919000492002',plan_days=None)
    day=clinic_today(nurse)+timedelta(days=4)
    patient_session(nurse,'nurse@sunrise.demo',pid)
    assert nurse.post('/v1/p/questions',json={'text':'I have a question about my report','client_key':'assist-qa'}).status_code==200
    # No AI consent: assisted workflow must use offline rules.
    assert nurse.post('/v1/p/consents',json={'purpose':'AI_PROCESSING','granted':False}).status_code==200
    login(nurse,'doctor@sunrise.demo')
    task=nurse.get('/v1/tasks',params={'patient_id':pid,'category':'CLINICAL_QUESTION'}).json()['tasks'][0]
    path=f"/v1/tasks/{task['id']}/assist"
    with SessionLocal() as db:before=db.scalar(select(func.count()).select_from(Appointment))
    response=nurse.post(path,json={'draft':f'Please change date to {day.isoformat()} for a review slot.'})
    assert response.status_code==200,response.text
    assert response.json()['requires_confirmation'] and response.json()['patient_id']==pid
    assert response.json()['proposed_date']==day.isoformat()
    assert 'RULES' in response.json()['provider']
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Appointment))==before
    login(nurse,'admin@sunrise.demo')
    assert nurse.post(path,json={}).status_code==403
    login(nurse,'doctor@lakeview.demo')
    assert nurse.post(path,json={}).status_code==404
