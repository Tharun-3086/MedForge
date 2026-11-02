"""Tenant-scoped lookups. Every id coming from a client goes through one of these.

A record from another clinic and a record that does not exist return the same 404, and the attempt is
written to the audit log as ACCESS_DENIED (PRD FR-02, FR-03)."""
from __future__ import annotations

import uuid
from typing import TypeVar

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    AppointmentRequest,
    CareTask,
    ExtractionProposal,
    FollowUpItem,
    FollowUpPlan,
    OutboundMessage,
    Patient,
    PatientReply,
    SourceArtifact,
)
from app.security import PatientPrincipal, Staff, not_found_or_denied
from app.services.tasks import can_see

T = TypeVar("T")


def _uuid(value: object) -> uuid.UUID | None:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def scoped(db: Session, staff: Staff, model: type[T], object_id: object, object_type: str) -> T:
    oid = _uuid(object_id)
    obj = db.get(model, oid) if oid else None
    if obj is None or getattr(obj, "clinic_id", None) != staff.clinic_id:
        raise not_found_or_denied(db, staff, object_type, object_id)
    return obj


def get_patient(db: Session, staff: Staff, patient_id: object) -> Patient:
    return scoped(db, staff, Patient, patient_id, "patient")


def get_task(db: Session, staff: Staff, task_id: object) -> CareTask:
    task = scoped(db, staff, CareTask, task_id, "care_task")
    if not can_see(staff, task):  # clinical questions are visible to clinical staff only
        raise not_found_or_denied(db, staff, "care_task", task_id)
    return task


def get_plan(db: Session, staff: Staff, plan_id: object) -> FollowUpPlan:
    return scoped(db, staff, FollowUpPlan, plan_id, "follow_up_plan")


def get_item(db: Session, staff: Staff, item_id: object) -> FollowUpItem:
    return scoped(db, staff, FollowUpItem, item_id, "follow_up_item")


def get_proposal(db: Session, staff: Staff, proposal_id: object) -> ExtractionProposal:
    return scoped(db, staff, ExtractionProposal, proposal_id, "extraction_proposal")


def get_artifact(db: Session, staff: Staff, artifact_id: object) -> SourceArtifact:
    art = scoped(db, staff, SourceArtifact, artifact_id, "source_artifact")
    if art.deleted_at is not None:
        raise HTTPException(410, "This file was deleted at the end of its retention period.")
    return art


def get_message(db: Session, staff: Staff, message_id: object) -> OutboundMessage:
    return scoped(db, staff, OutboundMessage, message_id, "outbound_message")


def get_request(db: Session, staff: Staff, request_id: object) -> AppointmentRequest:
    return scoped(db, staff, AppointmentRequest, request_id, "appointment_request")


def get_appointment(db: Session, staff: Staff, appointment_id: object) -> Appointment:
    return scoped(db, staff, Appointment, appointment_id, "appointment")


# ------------------------------------------------------------------ patient-app ownership checks
def own_reply(db: Session, me: PatientPrincipal, reply_id: object) -> PatientReply:
    rid = _uuid(reply_id)
    reply = db.get(PatientReply, rid) if rid else None
    if reply is None or reply.patient_id != me.patient_id:
        raise HTTPException(404, "Message not found.")
    return reply


def own_request(db: Session, patient_id: uuid.UUID, request_id: object) -> AppointmentRequest | None:
    if not request_id:
        return None
    rid = _uuid(request_id)
    req = db.get(AppointmentRequest, rid) if rid else None
    if req is None or req.patient_id != patient_id:
        raise HTTPException(404, "Request not found.")
    return req
