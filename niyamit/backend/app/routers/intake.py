"""Report Inbox: upload, AI-proposed fields with evidence, field-by-field review, approval into a plan."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import serializers as S
from app import storage
from app.audit import audit
from app.config import settings
from app.db import get_db
from app.enums import ProposalStatus, SourceType
from app.models import ExtractionProposal, Patient, SourceArtifact
from app.security import Staff, require_staff
from app.services import guards, intake
from app.services.common import clinic_today, get_clinic

router = APIRouter(prefix="/v1", tags=["report-inbox"])


async def read_limited(file: UploadFile, limit_mb: int) -> bytes:
    data = await file.read(limit_mb * 1024 * 1024 + 1)
    if len(data) > limit_mb * 1024 * 1024:
        raise HTTPException(413, f"File is larger than {limit_mb} MB.")
    return data


@router.post("/intake-artifacts", status_code=201)
async def upload(file: UploadFile = File(...), patient_id: str = Form(...),
                 source_type: Literal["PRESCRIPTION", "LAB_REPORT", "REGISTER", "SPREADSHEET", "OTHER"] = Form("PRESCRIPTION"),
                 staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    clinic = get_clinic(db, staff.clinic_id)
    patient = guards.get_patient(db, staff, patient_id)
    data = await read_limited(file, settings.max_upload_mb)
    artifact, proposal = intake.upload(db, clinic, patient, data, file.filename or "upload", SourceType(source_type),
                                       staff=staff)
    db.commit()  # extraction runs after commit (worker, or inline in eager mode)
    db.refresh(proposal)
    return S.proposal_dict(proposal, artifact, patient)


@router.get("/intake-proposals")
def list_proposals(status: Literal["open", "all", "NEEDS_REVIEW", "EXTRACTION_FAILED", "APPROVED", "REJECTED"] = "open",
                   limit: int = Query(100, ge=1, le=300), staff: Staff = Depends(require_staff),
                   db: Session = Depends(get_db)) -> dict:
    stmt = (select(ExtractionProposal, SourceArtifact, Patient)
            .join(SourceArtifact, SourceArtifact.id == ExtractionProposal.artifact_id)
            .outerjoin(Patient, Patient.id == ExtractionProposal.patient_id)
            .where(ExtractionProposal.clinic_id == staff.clinic_id))
    if status == "open":
        stmt = stmt.where(ExtractionProposal.status.in_([ProposalStatus.EXTRACTION_PENDING, ProposalStatus.NEEDS_REVIEW,
                                                         ProposalStatus.EXTRACTION_FAILED]))
    elif status != "all":
        stmt = stmt.where(ExtractionProposal.status == status)
    rows = db.execute(stmt.order_by(ExtractionProposal.created_at.desc()).limit(limit)).all()
    return {"proposals": [S.proposal_dict(p, a, pt) for p, a, pt in rows]}


def _proposal_out(db: Session, staff: Staff, proposal: ExtractionProposal) -> dict:
    artifact = db.get(SourceArtifact, proposal.artifact_id)
    patient = db.get(Patient, proposal.patient_id) if proposal.patient_id else None
    out = S.proposal_dict(proposal, artifact, patient, with_blocks=True)
    clinic = get_clinic(db, staff.clinic_id)
    out["today"] = clinic_today(clinic).isoformat()
    from app.services.plans import can_approve

    out["can_approve"] = can_approve(staff, clinic)
    return out


@router.get("/intake-proposals/{proposal_id}")
def get_proposal(proposal_id: str, staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    proposal = guards.get_proposal(db, staff, proposal_id)
    audit(db, clinic_id=staff.clinic_id, action="VIEW_PROPOSAL", actor=staff, object_type="extraction_proposal",
          object_id=proposal.id, patient_id=proposal.patient_id)
    db.commit()
    return _proposal_out(db, staff, proposal)


class FieldReviewIn(BaseModel):
    action: Literal["APPROVE", "CORRECT", "REJECT"]
    value: str | None = Field(default=None, max_length=200)
    reason: str = Field(default="", max_length=300)


@router.patch("/intake-proposals/{proposal_id}/fields/{field_id}")
def review_field(proposal_id: str, field_id: str, body: FieldReviewIn, staff: Staff = Depends(require_staff),
                 db: Session = Depends(get_db)) -> dict:
    proposal = guards.get_proposal(db, staff, proposal_id)
    field = next((f for f in proposal.fields if str(f.id) == field_id), None)
    if field is None:
        raise HTTPException(404, "Field not found on this proposal.")
    intake.review_field(db, staff, proposal, field, action=body.action, value=body.value, reason=body.reason.strip())
    db.commit()
    return _proposal_out(db, staff, proposal)


class ApproveIn(BaseModel):
    field_ids: list[str] = Field(min_length=1, max_length=20)
    notes: str = Field(default="", max_length=2000)


@router.post("/intake-proposals/{proposal_id}/approve")
def approve(proposal_id: str, body: ApproveIn, staff: Staff = Depends(require_staff),
            db: Session = Depends(get_db)) -> dict:
    proposal = guards.get_proposal(db, staff, proposal_id)
    ids = [guards._uuid(i) for i in body.field_ids]
    if any(i is None for i in ids):
        raise HTTPException(422, "Unknown field.")
    plan = intake.approve_proposal(db, staff, get_clinic(db, staff.clinic_id), proposal, ids, body.notes)
    db.commit()
    out = _proposal_out(db, staff, proposal)
    out["plan"] = S.plan_dict(plan, clinic_today(get_clinic(db, staff.clinic_id)))
    return out


class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


@router.post("/intake-proposals/{proposal_id}/reject")
def reject(proposal_id: str, body: RejectIn, staff: Staff = Depends(require_staff),
           db: Session = Depends(get_db)) -> dict:
    proposal = guards.get_proposal(db, staff, proposal_id)
    intake.reject_proposal(db, staff, proposal, body.reason)
    db.commit()
    return _proposal_out(db, staff, proposal)


@router.post("/intake-proposals/{proposal_id}/retry")
def retry(proposal_id: str, staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    proposal = guards.get_proposal(db, staff, proposal_id)
    intake.retry(db, staff, proposal)
    db.commit()
    db.refresh(proposal)
    return _proposal_out(db, staff, proposal)


# ------------------------------------------------------------------ original files (signed, short-lived, staff only)
def _checked_artifact(db: Session, staff: Staff, artifact_id: str, exp: int, sig: str) -> SourceArtifact:
    if not storage.verify_signature(artifact_id, exp, sig):
        raise HTTPException(403, "This file link has expired. Reload the page.")
    return guards.get_artifact(db, staff, artifact_id)


@router.get("/artifacts/{artifact_id}/content")
def artifact_content(artifact_id: str, exp: int, sig: str, staff: Staff = Depends(require_staff),
                     db: Session = Depends(get_db)) -> Response:
    art = _checked_artifact(db, staff, artifact_id, exp, sig)
    audit(db, clinic_id=staff.clinic_id, action="VIEW_ORIGINAL_FILE", actor=staff, object_type="source_artifact",
          object_id=art.id, patient_id=art.patient_id)
    db.commit()
    return Response(storage.load(art.storage_key), media_type=art.mime_type,
                    headers={"Content-Disposition": f'inline; filename="{art.filename}"', "Cache-Control": "private, no-store",
                             "Content-Security-Policy": "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"})


@router.get("/artifacts/{artifact_id}/page/{page}")
def artifact_page(artifact_id: str, page: int, exp: int, sig: str, staff: Staff = Depends(require_staff),
                  db: Session = Depends(get_db)) -> Response:
    """Page image for the evidence viewer (PDF pages are rendered on the server)."""
    art = _checked_artifact(db, staff, artifact_id, exp, sig)
    data = storage.load(art.storage_key)
    if art.mime_type.startswith("image/"):
        if page != 1:
            raise HTTPException(404, "Images have one page.")
        return Response(data, media_type=art.mime_type, headers={"Cache-Control": "private, no-store"})
    if art.mime_type != "application/pdf":
        raise HTTPException(415, "No page preview for this file type.")
    if not 1 <= page <= art.page_count:
        raise HTTPException(404, "Page not found.")
    from app.ai.providers.local_docs import render_pdf_pages

    pngs = render_pdf_pages(data, max_pages=page, scale=1.6)
    if len(pngs) < page:
        raise HTTPException(500, "The page could not be rendered.")
    return Response(pngs[page - 1], media_type="image/png", headers={"Cache-Control": "private, no-store"})
