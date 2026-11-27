import io
from PIL import Image
from sqlalchemy import select
from app.db import SessionLocal
from app.enums import ProposalStatus
from app.models import ExtractionProposal
from tests.conftest import new_patient, patient_session


def test_document_status_is_patient_scoped_and_does_not_expose_proposed_fields(nurse, seeded):
    first = new_patient(nurse, 'Document Status Test', '+919000390001', plan_days=None)
    second = new_patient(nurse, 'Other Document Patient', '+919000390002', plan_days=None)
    patient_session(nurse, 'nurse@sunrise.demo', first)
    image = io.BytesIO()
    Image.new('RGB', (300, 300), 'white').save(image, format='PNG')
    response = nurse.post('/v1/p/documents', files={'file': ('status-test.png', image.getvalue(), 'image/png')}, data={'source_type': 'PRESCRIPTION'})
    assert response.status_code == 201
    for status in ProposalStatus:
        with SessionLocal() as db:
            proposal = db.scalar(select(ExtractionProposal).where(ExtractionProposal.patient_id == first))
            proposal.status = status
            db.commit()
        doc = nurse.get('/v1/p/passport').json()['documents'][0]
        assert doc['status'] == status
        assert set(doc) == {'filename', 'uploaded_at', 'status'}
    patient_session(nurse, 'nurse@sunrise.demo', second)
    assert nurse.get('/v1/p/passport').json()['documents'] == []


def test_checked_lab_report_completes_without_a_followup_plan(nurse):
    import uuid
    from app.models import Patient,ExtractedField
    from tests.test_health_readings import document
    pid=new_patient(nurse,'Completed lab QA','+919000588845',plan_days=None)
    with SessionLocal() as db:
        patient=db.get(Patient,uuid.UUID(pid))
        _,proposal=document(db,patient,'completed-lab.png','2026-11-01','FBS: 110 mg/dL')
        db.add(ExtractedField(clinic_id=patient.clinic_id,proposal_id=proposal.id,position=1,name='fasting_glucose',value='110 mg/dL',proposed_value='110 mg/dL',status='NEEDS_REVIEW',review_reasons=['LOW_OCR_CONFIDENCE']))
        db.commit();proposal_id=str(proposal.id)
    data=nurse.get(f'/v1/intake-proposals/{proposal_id}').json()
    for f in data['fields']:
        response=nurse.patch(f"/v1/intake-proposals/{proposal_id}/fields/{f['id']}",json={'action':'APPROVE','reason':'Synthetic QA: checked source number, unit and date'})
        assert response.status_code==200,response.text
    assert response.json()['status']=='REVIEWED' and response.json()['plan_id'] is None
    assert proposal_id not in [p['id'] for p in nurse.get('/v1/intake-proposals').json()['proposals']]
    assert proposal_id in [p['id'] for p in nurse.get('/v1/intake-proposals?status=REVIEWED').json()['proposals']]
    patient_session(nurse,'nurse@sunrise.demo',pid)
    assert nurse.get('/v1/p/documents').json()['documents'][0]['status']=='REVIEWED'
    assert not nurse.get('/v1/p/home').json()['items']


def test_patient_listen_requires_ai_consent(nurse,monkeypatch):
    from app.ai import pipeline
    from uuid import uuid4
    pid=new_patient(nurse,'Voice consent journey QA','+919000588846')
    patient_session(nurse,'nurse@sunrise.demo',pid)
    nurse.post('/v1/p/consents',json={'purpose':'AI_PROCESSING','granted':False}).raise_for_status()
    reply=nurse.post('/v1/p/replies/button',json={'choice':'CONFIRM','client_key':str(uuid4())}).json()
    calls=[]
    class FakeTTS:
        def synthesize(self,text,language):calls.append(text);return b'RIFF-test-WAVE'
    monkeypatch.setattr(pipeline,'get_tts',lambda:FakeTTS())
    assert nurse.get('/v1/p/home').json()['tts_available'] is False
    assert nurse.get(f"/v1/p/replies/{reply['id']}/audio").status_code==403
    assert not calls
    nurse.post('/v1/p/consents',json={'purpose':'AI_PROCESSING','granted':True}).raise_for_status()
    assert nurse.get('/v1/p/home').json()['tts_available'] is True
    assert nurse.get(f"/v1/p/replies/{reply['id']}/audio").status_code==200
    assert len(calls)==1


def test_plan_approval_does_not_lock_pending_health_review(nurse):
    import uuid
    from datetime import date,timedelta
    from app.models import Patient,ExtractedField,CareTask,Clinic
    from app.services.tasks import create_task
    from tests.test_health_readings import document
    pid=new_patient(nurse,'Plan and report review QA','+919000588847',plan_days=None)
    with SessionLocal() as db:
        patient=db.get(Patient,uuid.UUID(pid));clinic=db.get(Clinic,patient.clinic_id)
        art,prop=document(db,patient,'plan-and-lab.png','2026-11-01','Weight: 75 kg')
        db.add(ExtractedField(clinic_id=patient.clinic_id,proposal_id=prop.id,position=1,name='next_review_date',value=str(date.today()+timedelta(days=10)),proposed_value=str(date.today()+timedelta(days=10)),status='UNVERIFIED'))
        db.add(ExtractedField(clinic_id=patient.clinic_id,proposal_id=prop.id,position=2,name='weight',value='75 kg',proposed_value='75 kg',status='NEEDS_REVIEW',review_reasons=['LOW_OCR_CONFIDENCE']))
        task,_=create_task(db,clinic=clinic,patient=patient,category='DOCUMENT_REVIEW',queue='NURSE',title='Review source report',dedupe_key=f'docreview:{art.id}',source_type='source_artifact',source_id=art.id)
        db.commit();propid=str(prop.id);taskid=task.id
    fields=nurse.get('/v1/intake-proposals/'+propid).json()['fields'];due=next(f for f in fields if f['name']=='next_review_date')
    for f in fields:
        if f['name']!='weight':assert nurse.patch(f"/v1/intake-proposals/{propid}/fields/{f['id']}",json={'action':'APPROVE'}).status_code==200
    assert nurse.post(f'/v1/intake-proposals/{propid}/approve',json={'field_ids':[due['id']]}).status_code==200
    with SessionLocal() as db:assert db.get(CareTask,taskid).status=='OPEN'
    weight=next(f for f in fields if f['name']=='weight')
    assert nurse.patch(f"/v1/intake-proposals/{propid}/fields/{weight['id']}",json={'action':'APPROVE','reason':'Checked original weight and kg unit'}).status_code==200
    with SessionLocal() as db:assert db.get(CareTask,taskid).status=='RESOLVED'
    assert nurse.patch(f"/v1/intake-proposals/{propid}/fields/{due['id']}",json={'action':'CORRECT','value':'2026-12-25','reason':'Should use plan editor'}).status_code==409
