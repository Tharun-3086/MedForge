"""Demo-only test profile removal; never a production patient-erasure workflow."""
from sqlalchemy import select, delete, update
from app import storage
from app.config import settings
from app.db import Base, utcnow
from app.models import SourceArtifact, ExtractionProposal, ExtractedField, CareTask, TaskEvent, Patient, PatientOtpChallenge
from app.audit import audit


def allowed(clinic,patient,staff):
    return (settings.demo_mode and not settings.is_production and clinic.is_synthetic and patient.is_synthetic
            and staff.role in ('ADMIN','DOCTOR') and patient.external_ref!='SDC-1001')


def remove(db,clinic,patient,staff):
    # Exclude simultaneous extraction changes before deleting dependent fields.
    db.scalars(select(ExtractionProposal).where(ExtractionProposal.patient_id==patient.id,ExtractionProposal.clinic_id==clinic.id).with_for_update()).all()
    # Lock patient only after active extraction releases its proposal lock;
    # extraction may still need a patient FK lock when writing its timeline.
    if db.get(Patient,patient.id,with_for_update=True,populate_existing=True) is None:
        from fastapi import HTTPException
        raise HTTPException(404,'Patient not found.')
    artifacts=db.scalars(select(SourceArtifact).where(SourceArtifact.patient_id==patient.id,SourceArtifact.clinic_id==clinic.id)).all()
    proposal_ids=select(ExtractionProposal.id).where(ExtractionProposal.patient_id==patient.id,ExtractionProposal.clinic_id==clinic.id)
    task_ids=select(CareTask.id).where(CareTask.patient_id==patient.id,CareTask.clinic_id==clinic.id)
    db.execute(delete(ExtractedField).where(ExtractedField.proposal_id.in_(proposal_ids),ExtractedField.clinic_id==clinic.id))
    db.execute(delete(TaskEvent).where(TaskEvent.task_id.in_(task_ids),TaskEvent.clinic_id==clinic.id))
    # Detach originals into the existing retention cleanup path. This keeps
    # storage failures retryable without restoring the removed phone/profile.
    for artifact in artifacts:
        artifact.patient_id=None;artifact.retention_until=utcnow();artifact.filename='Removed test document'
    db.flush()
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in ('source_artifacts','audit_events') or 'patient_id' not in table.c:continue
        criteria=table.c.patient_id==patient.id
        if 'clinic_id' in table.c:criteria=criteria & (table.c.clinic_id==clinic.id)
        db.execute(delete(table).where(criteria))
    # Invalidate any pending phone challenge without bypassing its send limits.
    from app.services.patient_otp import digest
    db.execute(update(PatientOtpChallenge).where(PatientOtpChallenge.phone_hash==digest(patient.phone_e164)).values(used_at=utcnow()))
    patient_id=patient.id
    db.execute(delete(Patient).where(Patient.id==patient_id,Patient.clinic_id==clinic.id))
    audit(db,clinic_id=clinic.id,action='TEST_PATIENT_REMOVED',actor=staff,object_type='patient',object_id=patient_id,
          detail={'document_count':len(artifacts),'scope':'DEMO_ONLY','phone_reusable':True})
    db.commit()
    pending=0
    for artifact in artifacts:
        try:
            storage.delete(artifact.storage_key)
            artifact.deleted_at=utcnow()
        except storage.StorageUnavailable:pending+=1
    db.commit()
    return {'ok':True,'phone_reusable':True,'file_cleanup_pending':pending}
