"""Report Inbox with provenance (PRD 7.1, 7.8). The original file is kept encrypted; AI-extracted fields stay
UNVERIFIED/NEEDS_REVIEW until an authorised person approves or corrects each one."""
from __future__ import annotations

import uuid
import hashlib
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app import storage
from app.ai.contracts import DATE_FIELDS, FIELD_LABELS, FIELD_TO_ITEM
from app.ai.pipeline import PIPELINE_VERSION, extract_document
from app.ai.providers.base import ProviderError
from app.audit import audit, timeline
from app.db import utcnow
from app.enums import (
    ActorType,
    ConsentPurpose,
    FieldStatus,
    ProposalStatus,
    Provenance,
    SourceType,
    TaskCategory,
    TaskQueue,
)
from app.jobs import defer
from app.models import Clinic, ExtractedField, ExtractionProposal, Patient, SourceArtifact
from app.security import Staff
from app.services import plans
from app.services.common import active_faults, clinic_today
from app.services.links import has_consent
from app.services.tasks import create_task


def upload(db: Session, clinic: Clinic, patient: Patient | None, data: bytes, filename: str, source_type: str, *,
           staff: Staff | None = None, by_patient: bool = False, document_style: str = "auto",
           document_language: str = "en") -> tuple[SourceArtifact, ExtractionProposal]:
    vf = storage.validate_document(data, filename)
    # Serialize identical patient-scoped uploads without a migration that would
    # destroy legacy duplicates. Another clinic/patient never reuses this row.
    identity=f"{clinic.id}:{patient.id if patient else ''}:{vf.sha256}:{source_type}:{document_style}:{document_language}"
    lock_key=int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8], 'big', signed=True)
    db.execute(select(func.pg_advisory_xact_lock(lock_key)))
    existing=db.execute(select(SourceArtifact,ExtractionProposal).join(ExtractionProposal,ExtractionProposal.artifact_id==SourceArtifact.id)
        .where(SourceArtifact.clinic_id==clinic.id,SourceArtifact.patient_id==(patient.id if patient else None),
               ExtractionProposal.clinic_id==clinic.id,ExtractionProposal.patient_id==(patient.id if patient else None),
               SourceArtifact.sha256==vf.sha256,SourceArtifact.source_type==source_type,
               SourceArtifact.document_style==document_style,SourceArtifact.document_language==document_language,
               SourceArtifact.deleted_at.is_(None),ExtractionProposal.status!='REJECTED')
        .order_by(SourceArtifact.created_at.desc()).limit(1)).first()
    if existing:
        audit(db,clinic_id=clinic.id,action='DUPLICATE_DOCUMENT_REUSED',actor=staff,
              actor_type='PATIENT' if by_patient else None,actor_id=str(patient.id) if by_patient and patient else '',
              object_type='source_artifact',object_id=existing[0].id,patient_id=existing[0].patient_id)
        return existing[0],existing[1]
    art_id = uuid.uuid4()
    key = storage.store(clinic.id, art_id, vf.data)
    artifact = SourceArtifact(
        id=art_id, clinic_id=clinic.id, patient_id=patient.id if patient else None,
        uploaded_by_user_id=staff.user_id if staff else None, uploaded_by_patient=by_patient,
        source_type=SourceType(source_type), filename=vf.filename, mime_type=vf.mime, size_bytes=len(vf.data),
        page_count=vf.page_count, document_style=document_style, document_language=document_language,
        sha256=vf.sha256, storage_key=key, is_synthetic=bool(clinic.is_synthetic and (patient is None or patient.is_synthetic)),
        retention_until=utcnow() + timedelta(days=clinic.document_retention_days))
    db.add(artifact)
    db.flush()  # the proposal references the artifact row
    proposal = ExtractionProposal(clinic_id=clinic.id, patient_id=artifact.patient_id, artifact_id=art_id,
                                  status=ProposalStatus.EXTRACTION_PENDING, pipeline_version=PIPELINE_VERSION)
    db.add(proposal)
    db.flush()
    audit(db, clinic_id=clinic.id, action="ARTIFACT_UPLOADED", actor=staff,
          actor_type=ActorType.PATIENT if by_patient else None, actor_id=str(patient.id) if by_patient and patient else "",
          object_type="source_artifact", object_id=art_id, patient_id=artifact.patient_id,
          detail={"mime": vf.mime, "pages": vf.page_count, "sha256": vf.sha256[:16]})
    if patient:
        timeline(db, clinic_id=clinic.id, patient_id=patient.id, event_type="DOCUMENT_SHARED",
                 summary=f"{'Patient shared' if by_patient else 'Staff uploaded'} a document ({vf.filename}) — awaiting staff review",
                 provenance=Provenance.PATIENT_REPORTED if by_patient else Provenance.SYSTEM_EVENT,
                 actor_type=ActorType.PATIENT if by_patient else ActorType.USER,
                 actor_label="Patient" if by_patient else (staff.label if staff else "Staff"),
                 source_type="source_artifact", source_id=art_id)
    if by_patient and patient:
        create_task(db, clinic=clinic, patient=patient, category=TaskCategory.DOCUMENT_REVIEW, queue=TaskQueue.NURSE,
                    title="Patient shared a document — review in Report Inbox", dedupe_key=f"docreview:{art_id}",
                    source_type="source_artifact", source_id=art_id)
    defer(db, "process_extraction", proposal.id)
    return artifact, proposal


def run_extraction(db: Session, proposal_id: uuid.UUID) -> None:
    proposal = db.get(ExtractionProposal, proposal_id, with_for_update=True, populate_existing=True)
    if proposal is None or proposal.status != ProposalStatus.EXTRACTION_PENDING:
        return
    artifact = db.get(SourceArtifact, proposal.artifact_id)
    clinic = db.get(Clinic, proposal.clinic_id)
    try:
        data = storage.load(artifact.storage_key)
    except storage.StorageUnavailable:
        proposal.status, proposal.error_code = ProposalStatus.EXTRACTION_FAILED, "STORAGE_UNREADABLE"
        proposal.provider_notes = ["The stored file could not be read."]
        proposal.processed_at = utcnow()
        return
    local_only = proposal.patient_id is not None and not has_consent(db, proposal.patient_id,
                                                                     ConsentPurpose.AI_PROCESSING)
    try:
        result = extract_document(data, artifact.mime_type, artifact.filename, today=clinic_today(clinic),
                                  faults=active_faults(db), local_only=local_only,
                                  document_style=artifact.document_style, document_language=artifact.document_language)
    except ProviderError as exc:
        proposal.status, proposal.error_code = ProposalStatus.EXTRACTION_FAILED, exc.code
        proposal.provider_notes = [exc.detail or exc.code]
        proposal.processed_at = utcnow()
        return
    proposal.blocks, proposal.page_sizes = result.blocks, result.page_sizes
    proposal.ocr_provider, proposal.llm_provider, proposal.model_version = result.ocr_provider, result.extractor, result.model_version
    proposal.provider_notes = result.notes
    for pos, f in enumerate(result.fields):
        db.add(ExtractedField(clinic_id=proposal.clinic_id, proposal_id=proposal.id, position=pos, name=f.name,
                              value=f.value, proposed_value=f.value, extracted_value=f.extracted_value[:300], status=f.status,
                              confidence=f.confidence, evidence=f.evidence, review_reasons=f.review_reasons))
    proposal.status = ProposalStatus.NEEDS_REVIEW
    proposal.processed_at = utcnow()
    if proposal.patient_id:
        timeline(db, clinic_id=proposal.clinic_id, patient_id=proposal.patient_id, event_type="AI_EXTRACTION",
                 summary=f"AI proposed {len(result.fields)} field(s) from {artifact.filename} — unverified until staff review",
                 provenance=Provenance.AI_PROPOSED, actor_type=ActorType.AI, actor_label=result.extractor,
                 source_type="extraction_proposal", source_id=proposal.id, visibility="STAFF")


def add_missing_field(db: Session, staff: Staff, proposal: ExtractionProposal, *, name: str, label: str,
                      value: str, quote: str, page: int, reason: str) -> ExtractedField:
    """Human transcription from the original; never silently invent a new tracked parameter."""
    from app.services.health_readings import LABELS, valid_value, custom_reading
    if not staff.is_clinical:
        raise HTTPException(403, "A doctor or nurse must check missing measurements against the original.")
    if proposal.status not in (ProposalStatus.NEEDS_REVIEW, ProposalStatus.REVIEWED, ProposalStatus.APPROVED):
        raise HTTPException(409, "Wait for extraction to finish; rejected reports cannot be edited.")
    artifact = db.get(SourceArtifact, proposal.artifact_id)
    if artifact is None or artifact.deleted_at is not None or page > artifact.page_count:
        raise HTTPException(422, "Choose an existing page in the original document.")
    value, quote, reason, label = value.strip(), quote.strip(), reason.strip(), label.strip()
    if not value or not quote or len(reason) < 3:
        raise HTTPException(422, "Copy the original result and give a verification note.")
    if name not in LABELS and name not in ("clinical_observation", "custom_measurement"):
        raise HTTPException(422, "Choose a supported measurement or an additional clinical observation.")
    if name in LABELS and not valid_value(name, value):
        raise HTTPException(422, "Enter the reading with its explicit supported unit, for example 75 mg/dL.")
    if name == "custom_measurement" and not custom_reading(label,value):
        raise HTTPException(422, "Name the lab test and enter its numeric result with the source unit.")
    if name == "clinical_observation" and not label:
        raise HTTPException(422, "Name the additional observation. It will be kept in the report, outside charts.")
    if any(f.name == name and f.status != FieldStatus.REJECTED and
           (name not in ("clinical_observation", "custom_measurement") or (f.evidence or {}).get("manual_label") == label)
           for f in proposal.fields):
        raise HTTPException(409, "This field already exists. Correct or reject its existing candidate first.")
    field = ExtractedField(clinic_id=proposal.clinic_id, proposal=proposal,
        position=max((f.position for f in proposal.fields), default=-1) + 1,
        name=name, value=value, proposed_value=None, extracted_value=quote,
        status=FieldStatus.APPROVED, confidence=None, review_reasons=[],
        evidence={"page": page, "quote": quote, "extraction_method": "CLINICIAN_TRANSCRIPTION",
                  "manual_label": LABELS.get(name) or label, "verification_note": reason},
        reviewed_by_user_id=staff.user_id, reviewed_at=utcnow())
    db.add(field)
    db.flush()
    audit(db, clinic_id=proposal.clinic_id, action="FIELD_ADDED_BY_CLINICIAN", actor=staff,
          object_type="extracted_field", object_id=field.id, patient_id=proposal.patient_id,
          detail={"field": name, "value": value, "page": page, "reason": reason})
    finish_report_review(db, staff, proposal)
    return field


def review_field(db: Session, staff: Staff, proposal: ExtractionProposal, field: ExtractedField, *, action: str,
                 value: str | None, reason: str, measurement_name: str | None = None) -> ExtractedField:
    if proposal.status not in (ProposalStatus.NEEDS_REVIEW, ProposalStatus.REVIEWED, ProposalStatus.APPROVED):
        raise HTTPException(409, "This proposal is no longer open for review.")
    if proposal.status == ProposalStatus.APPROVED and field.name in FIELD_TO_ITEM and field.status == FieldStatus.APPROVED and action != "APPROVE":
        raise HTTPException(409, "This date has already been approved into a plan. Change the follow-up plan separately.")
    before = {"value": field.value, "status": field.status}
    if action == "REJECT":
        field.status = FieldStatus.REJECTED
    elif action in ("APPROVE", "CORRECT"):
        if field.name in ('unmapped_measurement','custom_measurement'):
            from app.services.health_readings import custom_reading, LABELS
            if not staff.is_clinical:
                raise HTTPException(403, "A doctor or nurse must verify laboratory results.")
            if field.name=='unmapped_measurement' and action!='CORRECT':
                raise HTTPException(422, "Use Correct to verify the test name, numeric value and unit first.")
            from app.ai.medical_contracts import PARAMETER_ALIASES
            import re
            label=(measurement_name or (field.evidence or {}).get('manual_label') or (field.evidence or {}).get('parameter') or '').strip()
            key=PARAMETER_ALIASES.get(re.sub(r'[^a-z0-9]','',label.lower()))
            if key:
                field.name=key
            else:
                if not custom_reading(label,(value if action=='CORRECT' else field.value) or ''):
                    raise HTTPException(422, "Enter the exact test name and numeric result with its unit.")
                field.name='custom_measurement'
            field.evidence={**(field.evidence or {}),'manual_label':LABELS.get(key,label),'parameter_verified_by_clinician':True}
        from app.ai.providers.ocr_review import VERIFICATION_REASONS
        if action == "APPROVE" and VERIFICATION_REASONS.intersection(field.review_reasons or []) and not reason:
            raise HTTPException(422, "Check the original and give a verification note before confirming this uncertain reading.")
        new_value = (value if action == "CORRECT" else field.value) or ""
        from app.services.health_readings import LABELS, valid_value
        if (field.name in LABELS or field.name in ("clinical_observation", "custom_measurement")) and staff.role not in ("DOCTOR", "NURSE"):
            raise HTTPException(403, "A doctor or nurse must confirm health readings against the original.")
        if field.name in LABELS and not valid_value(field.name,new_value):
            raise HTTPException(422,"Enter the reading with explicit units, for example 120/80 mmHg, 110 mg/dL or 6.2 %.")
        if field.name in DATE_FIELDS:
            try:
                date.fromisoformat(new_value)
            except ValueError:
                raise HTTPException(422, "Enter the date as YYYY-MM-DD before approving.") from None
        if field.name == 'document_time':
            from app.services.health_readings import normalise_report_time
            new_value=normalise_report_time(new_value)
            if new_value is None:
                raise HTTPException(422, "Enter the collection/report time as HH:MM or HH:MM:SS.")
        if not new_value:
            raise HTTPException(422, "This field has no value to approve. Correct it first.")
        if action == "CORRECT" and not reason:
            raise HTTPException(422, "Give a short reason for the correction.")
        field.value, field.status = new_value, FieldStatus.APPROVED
    else:
        raise HTTPException(422, "Unknown review action.")
    field.reviewed_by_user_id, field.reviewed_at = staff.user_id, utcnow()
    audit(db, clinic_id=proposal.clinic_id, action=f"FIELD_{action}", actor=staff, object_type="extracted_field",
          object_id=field.id, patient_id=proposal.patient_id,
          detail={"field": field.name, "before": before, "after": {"value": field.value, "status": field.status},
                  "reason": reason[:200]})
    finish_report_review(db, staff, proposal)
    return field


def finish_report_review(db: Session, staff: Staff, proposal: ExtractionProposal) -> None:
    """A checked lab report can finish without inventing a follow-up date."""
    resolved = bool(proposal.fields) and all(f.status in (FieldStatus.APPROVED, FieldStatus.REJECTED) for f in proposal.fields)
    plan_pending = any(f.name in FIELD_TO_ITEM and f.status == FieldStatus.APPROVED for f in proposal.fields)
    if resolved and not plan_pending and proposal.status == ProposalStatus.NEEDS_REVIEW:
        proposal.status = ProposalStatus.REVIEWED
        proposal.reviewed_by_user_id, proposal.reviewed_at = staff.user_id, utcnow()
        audit(db, clinic_id=proposal.clinic_id, action="REPORT_REVIEW_COMPLETED", actor=staff,
              object_type="extraction_proposal", object_id=proposal.id, patient_id=proposal.patient_id,
              detail={"follow_up_plan_created": False})
    elif proposal.status == ProposalStatus.REVIEWED and (not resolved or plan_pending):
        proposal.status = ProposalStatus.NEEDS_REVIEW
    if resolved and proposal.status in (ProposalStatus.REVIEWED, ProposalStatus.APPROVED):
        close_document_tasks(db, staff, proposal)


def close_document_tasks(db: Session, staff: Staff, proposal: ExtractionProposal) -> None:
    from app.enums import OPEN_TASK_STATES, TaskStatus
    from app.models import CareTask
    from app.services.tasks import transition
    rows=db.scalars(select(CareTask).where(CareTask.clinic_id==proposal.clinic_id,
        CareTask.patient_id==proposal.patient_id,CareTask.category==TaskCategory.DOCUMENT_REVIEW,
        CareTask.source_type=="source_artifact",CareTask.source_id==str(proposal.artifact_id),
        CareTask.status.in_(OPEN_TASK_STATES)).with_for_update()).all()
    for task in rows:
        transition(db,staff,task,TaskStatus.RESOLVED,outcome="DOCUMENT_REVIEWED",
            note="Source report review completed in Report Inbox." if proposal.status!=ProposalStatus.REJECTED else "Source report rejected in Report Inbox.")


def approve_proposal(db: Session, staff: Staff, clinic: Clinic, proposal: ExtractionProposal,
                     field_ids: list[uuid.UUID], notes: str = ""):
    if proposal.status != ProposalStatus.NEEDS_REVIEW:
        raise HTTPException(409, "This proposal is no longer open for review.")
    if proposal.patient_id is None:
        raise HTTPException(422, "Link the document to a patient first.")
    if not plans.can_approve(staff, clinic):
        raise HTTPException(403, "Your role cannot approve follow-up plans in this clinic.")
    by_id = {f.id: f for f in proposal.fields}
    items = []
    for fid in field_ids:
        f = by_id.get(fid)
        if f is None:
            raise HTTPException(404, "Field not found on this proposal.")
        if f.status != FieldStatus.APPROVED:
            raise HTTPException(422, f"'{FIELD_LABELS.get(f.name, f.name)}' must be approved before it can be used.")
        if f.name not in FIELD_TO_ITEM:
            continue
        items.append({"kind": FIELD_TO_ITEM[f.name], "due_date": date.fromisoformat(f.value),
                      "source_field_id": f.id})
    if not items:
        raise HTTPException(422, "Select at least one approved due-date field.")
    patient = db.get(Patient, proposal.patient_id)
    plan = plans.create_plan(db, staff, clinic, patient, items, notes=notes, source="ARTIFACT",
                             artifact_id=proposal.artifact_id, proposal_id=proposal.id)
    plans.approve_plan(db, staff, clinic, plan)
    proposal.status, proposal.plan_id = ProposalStatus.APPROVED, plan.id
    proposal.reviewed_by_user_id, proposal.reviewed_at = staff.user_id, utcnow()
    audit(db, clinic_id=clinic.id, action="PROPOSAL_APPROVED", actor=staff, object_type="extraction_proposal",
          object_id=proposal.id, patient_id=patient.id, detail={"plan_id": str(plan.id), "fields": [str(i) for i in field_ids]})
    finish_report_review(db, staff, proposal)
    return plan


def reject_proposal(db: Session, staff: Staff, proposal: ExtractionProposal, reason: str) -> None:
    if proposal.status not in (ProposalStatus.NEEDS_REVIEW, ProposalStatus.EXTRACTION_FAILED):
        raise HTTPException(409, "This proposal can no longer be rejected.")
    proposal.status = ProposalStatus.REJECTED
    proposal.reviewed_by_user_id, proposal.reviewed_at = staff.user_id, utcnow()
    audit(db, clinic_id=proposal.clinic_id, action="PROPOSAL_REJECTED", actor=staff,
          object_type="extraction_proposal", object_id=proposal.id, patient_id=proposal.patient_id,
          detail={"reason": reason[:200]})
    close_document_tasks(db, staff, proposal)


def retry(db: Session, staff: Staff, proposal: ExtractionProposal) -> None:
    if proposal.status not in (ProposalStatus.EXTRACTION_FAILED,):
        raise HTTPException(409, "Only failed extractions can be retried.")
    proposal.status, proposal.error_code = ProposalStatus.EXTRACTION_PENDING, ""
    defer(db, "process_extraction", proposal.id)
