from sqlalchemy import select,func
from app.config import settings
from app.db import SessionLocal
from app.models import Patient,SourceArtifact
from app.demo_showcase import ensure_showcase
from tests.conftest import patient_session

def test_showcase_is_additive_reviewed_and_idempotent(nurse):
    with SessionLocal() as db:
        patient=db.scalar(select(Patient).where(Patient.external_ref=='SDC-1001'))
        pid=str(patient.id)
        before=db.scalar(select(func.count()).select_from(SourceArtifact))
    assert ensure_showcase()['added_reports']==0
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(SourceArtifact))==before
    patient_session(nurse,'nurse@sunrise.demo',pid,birth_year=1962)
    snapshot=nurse.get('/v1/p/health-readings').json()
    history=[r for r in snapshot['history'] if r['filename'].startswith('SHOWCASE-DEMO-v1-')]
    assert len(history)==36
    assert all(r['clinic_reviewed'] and r['date_reviewed'] for r in history)
    assert len({r['report_date'] for r in history})==3

def test_showcase_disabled_outside_demo(monkeypatch):
    monkeypatch.setattr(settings,'demo_mode',False)
    assert 'skipped' in ensure_showcase()
