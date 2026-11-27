"""Add fictional source-verified report fixtures to the fixed public demo only.

Idempotent and additive. Never reset a database or modify ordinary patients.
Run in a standalone startup/CLI process, before accepting API requests.
"""
import hashlib
import json
from pathlib import Path

from sqlalchemy import select
from app.config import settings
from app.db import SessionLocal
from app.models import Clinic, Patient, User, Membership, SourceArtifact, ExtractionProposal
from app.security import Staff
from app.services import intake

def ensure_showcase():
    if not settings.demo_mode or settings.is_production:
        return {"skipped":"not a synthetic demo"}
    from app.seed import _offline_inline
    with _offline_inline(), SessionLocal() as db:
        patient=db.scalar(select(Patient).join(Clinic).where(
            Clinic.name=="Sunrise Diabetes Clinic (Synthetic)",Clinic.is_synthetic.is_(True),
            Patient.is_synthetic.is_(True),Patient.external_ref=="SDC-1001",
            Patient.phone_e164=="+919000000101",Patient.display_name=="Ramesh Kumar").with_for_update(of=Patient))
        if patient is None:return {"skipped":"fixed synthetic patient missing"}
        clinic=db.get(Clinic,patient.clinic_id)
        member=db.execute(select(User,Membership).join(Membership,Membership.user_id==User.id).where(
            User.email=="doctor@sunrise.demo",Membership.clinic_id==clinic.id,
            Membership.role=="DOCTOR",User.is_active.is_(True))).first()
        if member is None:return {"skipped":"synthetic doctor membership missing"}
        user,_=member
        staff=Staff(user.id,clinic.id,"DOCTOR",user.name,user.email)
        root=Path(__file__).resolve().parents[1]/"samples"/"showcase"
        added=0
        for spec in json.loads((root/"manifest.json").read_text(encoding="utf-8")):
            data=(root/spec["filename"]).read_bytes()
            existing=db.scalar(select(SourceArtifact.id).where(SourceArtifact.patient_id==patient.id,
                SourceArtifact.clinic_id==clinic.id,SourceArtifact.sha256==hashlib.sha256(data).hexdigest(),
                SourceArtifact.deleted_at.is_(None)))
            if existing:
                proposal=db.scalar(select(ExtractionProposal).where(ExtractionProposal.artifact_id==existing))
                if proposal is not None:intake.finish_report_review(db,staff,proposal)
                continue
            _,proposal=intake.upload(db,clinic,patient,data,spec["filename"],"LAB_REPORT",staff=staff,document_style="printed")
            intake.run_extraction(db,proposal.id)
            db.flush()
            db.refresh(proposal)
            expected={"document_date":spec["date"],**spec["values"]}
            actual={f.name:f.value for f in proposal.fields}
            if any(actual.get(k)!=v for k,v in expected.items()):
                raise RuntimeError("Showcase fixture extraction mismatch; refusing automatic fixture confirmation.")
            for field in proposal.fields:
                if field.name in expected or field.name=="document_type":
                    intake.review_field(db,staff,proposal,field,action="APPROVE",value=None,
                        reason="FICTIONAL DEMO FIXTURE: checked against the bundled expected values. Not a real clinical review.")
            added+=1
        db.commit()
        return {"added_reports":added,"synthetic_only":True}

if __name__=="__main__":
    print(json.dumps(ensure_showcase()))
