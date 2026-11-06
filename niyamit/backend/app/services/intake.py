"""Report Inbox with provenance (PRD 7.1, 7.8). The original file is kept encrypted; AI-extracted fields stay
UNVERIFIED/NEEDS_REVIEW until an authorised person approves or corrects each one."""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import HTTPException
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
           staff: Staff | None = None, by_patient: bool = False) -> tuple[SourceArtifact, ExtractionProposal]:
    vf = storage.validate_document(data, filename)
    art_id = uuid.uuid4()
    key = storage.store(clinic.id, art_id, vf.data)
    artifact = SourceArtifact(
        id=art_id, clinic_id=clinic.id, patient_id=patient.id if patient else None,
        uploaded_by_user_id=staff.user_id if staff else None, uploaded_by_patient=by_patient,
        source_type=SourceType(source_type), filename=vf.filename, mime_type=vf.mime, size_bytes=len(vf.data),
        page_count=vf.page_count, sha256=vf.sha256, storage_key=key, is_synthetic=True,
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
                                  faults=active_faults(db), local_only=local_only)
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


def review_field(db: Session, staff: Staff, proposal: ExtractionProposal, field: ExtractedField, *, action: str,
                 value: str | None, reason: str) -> ExtractedField:
    if proposal.status != ProposalStatus.NEEDS_REVIEW:
        raise HTTPException(409, "This proposal is no longer open for review.")
    before = {"value": field.value, "status": field.status}
    if action == "REJECT":
        field.status = FieldStatus.REJECTED
    elif action in ("APPROVE", "CORRECT"):
        new_value = (value if action == "CORRECT" else field.value) or ""
        from app.services.health_readings import LABELS, valid_value
        if field.name in LABELS and not valid_value(field.name,new_value):
            raise HTTPException(422,"Enter the reading with explicit units, for example 120/80 mmHg, 110 mg/dL or 6.2 %.")
        if field.name in DATE_FIELDS:
            try:
                date.fromisoformat(new_value)
            except ValueError:
                raise HTTPException(422, "Enter the date as YYYY-MM-DD before approving.") from None
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
    return field


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
    return plan


def reject_proposal(db: Session, staff: Staff, proposal: ExtractionProposal, reason: str) -> None:
    if proposal.status not in (ProposalStatus.NEEDS_REVIEW, ProposalStatus.EXTRACTION_FAILED):
        raise HTTPException(409, "This proposal can no longer be rejected.")
    proposal.status = ProposalStatus.REJECTED
    proposal.reviewed_by_user_id, proposal.reviewed_at = staff.user_id, utcnow()
    audit(db, clinic_id=proposal.clinic_id, action="PROPOSAL_REJECTED", actor=staff,
          object_type="extraction_proposal", object_id=proposal.id, patient_id=proposal.patient_id,
          detail={"reason": reason[:200]})


def retry(db: Session, staff: Staff, proposal: ExtractionProposal) -> None:
    if proposal.status not in (ProposalStatus.EXTRACTION_FAILED,):
        raise HTTPException(409, "Only failed extractions can be retried.")
    proposal.status, proposal.error_code = ProposalStatus.EXTRACTION_PENDING, ""
    defer(db, "process_extraction", proposal.id)
