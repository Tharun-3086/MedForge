import io
import uuid
from PIL import Image
from sqlalchemy import select
from app.db import SessionLocal, utcnow
from app.models import ExtractionProposal, ExtractedField
from tests.conftest import new_patient, patient_session


def test_patient_analysis_keeps_ai_original_separate_from_corrections_and_scopes_files(nurse, seeded):
    first=new_patient(nurse,'Analysis Owner','+919000420001',plan_days=None)
    second=new_patient(nurse,'Analysis Other','+919000420002',plan_days=None)
    patient_session(nurse,'nurse@sunrise.demo',first)
    buf=io.BytesIO();Image.new('RGB',(300,300),'white').save(buf,format='PNG')
    assert nurse.post('/v1/p/documents',files={'file':('analysis.png',buf.getvalue(),'image/png')},data={'source_type':'PRESCRIPTION'}).status_code==201
    with SessionLocal() as db:
        p=db.scalar(select(ExtractionProposal).where(ExtractionProposal.patient_id==uuid.UUID(first)))
        p.blocks=[{'text':'SYNTHETIC DOCUMENT TEXT'}]
        db.add(ExtractedField(clinic_id=p.clinic_id,proposal_id=p.id,position=99,name='next_review_date',
            value='2026-12-20',proposed_value='2026-12-10',extracted_value='10 Dec 2026',status='APPROVED',reviewed_at=utcnow()))
        db.commit()
    doc=nurse.get('/v1/p/documents').json()['documents'][0]
    assert doc['automatic_text']=='SYNTHETIC DOCUMENT TEXT'
    assert doc['automatic_fields'][-1]['value']=='2026-12-10'
    assert doc['clinic_reviewed_fields'][-1]['value']=='2026-12-20'
    assert doc['plan_approved'] is False
    path=f"/v1/p/documents/{doc['id']}/file"
    assert nurse.get(path).content==buf.getvalue()
    patient_session(nurse,'nurse@sunrise.demo',second)
    assert nurse.get('/v1/p/documents').json()['documents']==[]
    assert nurse.get(path).status_code==404
    nurse.cookies.clear()
    assert nurse.get(path).status_code==401
