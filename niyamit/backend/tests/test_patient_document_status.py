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
