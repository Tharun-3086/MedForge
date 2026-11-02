"""Demo-mode tools: the simulated patient phone, fault switches, the test panel and a reset button.
Everything here is disabled unless DEMO_MODE=true, and every screen labels it SIMULATED."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import serializers as S
from app.audit import audit
from app.config import settings
from app.db import get_db
from app.enums import MessageStatus, Role
from app.models import OutboundMessage, Patient, PatientReply, ProviderEvent, SystemFlag
from app.security import Staff, require_roles, require_staff
from app.services import demo, guards, inbound
from app.services.common import FAULTS, get_clinic, set_fault

router = APIRouter(prefix="/v1/demo", tags=["demo"])
operators = require_roles(Role.ADMIN, Role.DOCTOR, Role.NURSE)
ON_PHONE = [MessageStatus.SENT_TO_PROVIDER, MessageStatus.DELIVERED, MessageStatus.UNKNOWN]


def demo_only() -> None:
    if not settings.demo_mode:
        raise HTTPException(404, "Not found.")


@router.get("/status", dependencies=[Depends(demo_only)])
def status(staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    flags = {f.key: f.enabled for f in db.scalars(select(SystemFlag)).all()}
    return {"demo_mode": True, "tasks_mode": "inline" if settings.tasks_eager else "celery",
            "faults": [{"key": k, "label": v, "enabled": flags.get(k, False)} for k, v in FAULTS.items()],
            "scenarios": [{"name": k, "title": t} for k, (t, _) in demo.SCENARIOS.items()]}


class FaultIn(BaseModel):
    key: str
    enabled: bool


@router.post("/faults", dependencies=[Depends(demo_only)])
def toggle_fault(body: FaultIn, staff: Staff = Depends(operators), db: Session = Depends(get_db)) -> dict:
    if body.key not in FAULTS:
        raise HTTPException(422, "Unknown fault switch.")
    set_fault(db, body.key, body.enabled)
    audit(db, clinic_id=staff.clinic_id, action="DEMO_FAULT_TOGGLED", actor=staff, detail=body.model_dump())
    db.commit()
    return status(staff, db)


@router.post("/scenarios/{name}", dependencies=[Depends(demo_only)])
def run_scenario(name: str, staff: Staff = Depends(operators), db: Session = Depends(get_db)) -> dict:
    result = demo.run(db, staff, get_clinic(db, staff.clinic_id), name)
    audit(db, clinic_id=staff.clinic_id, action="DEMO_SCENARIO_RUN", actor=staff,
          detail={"scenario": name, "passed": result["passed"]})
    db.commit()
    return result


@router.post("/run-scheduler", dependencies=[Depends(demo_only)])
def run_scheduler(_: Staff = Depends(operators)) -> dict:
    from app.jobs import periodic

    return periodic()


@router.post("/reset", dependencies=[Depends(demo_only)])
def reset(staff: Staff = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)) -> dict:
    """Wipe and re-seed the synthetic demo data. Everyone has to sign in again afterwards."""
    from app.seed import reset_database, seed

    db.rollback()
    db.close()  # release this request's locks before TRUNCATE
    reset_database()
    info = seed()
    return {"ok": True, "relogin": True, **info}


# ------------------------------------------------------------------ simulated phone
@router.get("/phone/patients", dependencies=[Depends(demo_only)])
def phone_patients(staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(Patient).where(Patient.clinic_id == staff.clinic_id,
                                            Patient.preferred_channel == "SIMULATED")
                      .order_by(Patient.display_name)).all()
    return {"patients": [S.patient_brief(p) for p in rows]}


def _thread(db: Session, patient: Patient) -> dict:
    outs = db.scalars(select(OutboundMessage).where(OutboundMessage.patient_id == patient.id,
                                                    OutboundMessage.channel == "SIMULATED",
                                                    OutboundMessage.status.in_(ON_PHONE))).all()
    ins = db.execute(select(PatientReply, ProviderEvent).outerjoin(
        ProviderEvent, ProviderEvent.id == PatientReply.provider_event_id).where(
        PatientReply.patient_id == patient.id, PatientReply.channel == "SIMULATED")).all()
    items = [{"direction": "out", "id": str(m.id), "body": m.body, "status": m.status,
              "status_label": S.STATUS_LABEL.get(m.status), "kind": m.kind, "at": S.iso(m.sent_at or m.created_at)}
             for m in outs]
    items += [{"direction": "in", "id": str(r.id), "body": r.text or r.transcript or "(voice note)",
               "status": r.status, "event_id": ev.provider_event_id if ev else None,
               "duplicates_ignored": ev.duplicate_count if ev else 0, "at": S.iso(r.created_at)} for r, ev in ins]
    items.sort(key=lambda x: x["at"] or "")
    return {"patient": S.patient_brief(patient), "simulated": True, "messages": items,
            "note": "SIMULATED phone. Messages here travel through the same signed webhook path as WhatsApp."}


@router.get("/phone/{patient_id}", dependencies=[Depends(demo_only)])
def phone_thread(patient_id: str, staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    return _thread(db, guards.get_patient(db, staff, patient_id))


class PhoneReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    button: bool = False


@router.post("/phone/{patient_id}/reply", dependencies=[Depends(demo_only)])
def phone_reply(patient_id: str, body: PhoneReplyIn, staff: Staff = Depends(require_staff),
                db: Session = Depends(get_db)) -> dict:
    patient = guards.get_patient(db, staff, patient_id)
    if patient.preferred_channel != "SIMULATED":
        raise HTTPException(409, "This patient is not on the simulated channel.")
    result, event_id = inbound.demo_phone_reply(db, patient, body.text, button=body.button)
    db.commit()
    return {"result": result, "event_id": event_id, **_thread(db, patient)}


class ReplayIn(BaseModel):
    event_id: str = Field(max_length=160)


@router.post("/phone/{patient_id}/replay", dependencies=[Depends(demo_only)])
def phone_replay(patient_id: str, body: ReplayIn, staff: Staff = Depends(require_staff),
                 db: Session = Depends(get_db)) -> dict:
    """Deliver the same provider event again, as a provider retry would. It must not create a second action."""
    patient = guards.get_patient(db, staff, patient_id)
    ev = db.scalar(select(ProviderEvent).where(ProviderEvent.provider == "SIMULATED",
                                               ProviderEvent.provider_event_id == body.event_id,
                                               ProviderEvent.clinic_id == patient.clinic_id))
    if ev is None:
        raise HTTPException(404, "Event not found.")
    result, _ = inbound.demo_phone_reply(db, patient, ev.payload.get("text", ""), button=bool(ev.payload.get("button")),
                                         event_id=body.event_id)
    db.commit()
    return {"result": result, "event_id": body.event_id, **_thread(db, patient)}
