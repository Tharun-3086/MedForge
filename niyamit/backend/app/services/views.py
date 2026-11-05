"""Read models: clinic worklist (PRD 7.12), Visit Capsule (7.10), Care Passport (7.9) and timeline.

Sorting uses objective fields only (days overdue, due date, task age) — never an AI risk score."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select, true
from sqlalchemy.orm import Session

from app import serializers as S
from app.audit import audit
from app.enums import (
    CLINICAL_TASK_CATEGORIES,
    OPEN_TASK_STATES,
    InputMode,
    ItemStatus,
    MessageStatus,
    PlanStatus,
    Role,
)
from app.models import (
    Appointment,
    AppointmentRequest,
    AvailabilitySlot,
    CareTask,
    Clinic,
    ExtractedField,
    ExtractionProposal,
    FollowUpItem,
    FollowUpPlan,
    OutboundMessage,
    Patient,
    PatientReply,
    SourceArtifact,
    TimelineEvent,
    User,
)
from app.security import Staff
from app.services.common import clinic_today, clinic_tz, slot_label
from app.services.labels import CHOICE_LABELS


def _names(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    return {u.id: u.name for u in db.scalars(select(User).where(User.id.in_(ids))).all()}


def visible_task_filter(staff: Staff):
    if staff.is_clinical or staff.role == Role.ADMIN:
        return true()
    return CareTask.category.notin_([c.value for c in CLINICAL_TASK_CATEGORIES])


def worklist(db: Session, staff: Staff, clinic: Clinic, *, view: str = "attention", days_ahead: int = 7,
             queue: str | None = None, channel_failures: bool = False) -> dict[str, Any]:
    today = clinic_today(clinic)
    rows = db.execute(
        select(FollowUpItem, Patient)
        .join(FollowUpPlan, FollowUpItem.plan_id == FollowUpPlan.id)
        .join(Patient, Patient.id == FollowUpItem.patient_id)
        .where(FollowUpItem.clinic_id == clinic.id, FollowUpPlan.status == PlanStatus.ACTIVE,
               FollowUpItem.status.in_([ItemStatus.PENDING, ItemStatus.CONFIRMED_BY_PATIENT, ItemStatus.BOOKED]),
               FollowUpItem.due_date <= today + timedelta(days=days_ahead))
    ).all()
    patient_ids = {p.id for _, p in rows}
    tasks_by_patient: dict[uuid.UUID, list[CareTask]] = {}
    if patient_ids:
        for t in db.scalars(select(CareTask).where(CareTask.patient_id.in_(patient_ids),
                                                   CareTask.status.in_([s.value for s in OPEN_TASK_STATES]),
                                                   visible_task_filter(staff))).all():
            tasks_by_patient.setdefault(t.patient_id, []).append(t)
    last_reply: dict[uuid.UUID, PatientReply] = {}
    last_msg: dict[uuid.UUID, OutboundMessage] = {}
    if patient_ids:
        for r in db.scalars(select(PatientReply).where(PatientReply.patient_id.in_(patient_ids))
                            .order_by(PatientReply.created_at)).all():
            last_reply[r.patient_id] = r
        for m in db.scalars(select(OutboundMessage).where(OutboundMessage.patient_id.in_(patient_ids),
                                                          OutboundMessage.status != MessageStatus.SCHEDULED)
                            .order_by(OutboundMessage.created_at)).all():
            last_msg[m.patient_id] = m
    names = _names(db, {t.assignee_user_id for ts in tasks_by_patient.values() for t in ts if t.assignee_user_id})

    out = []
    for item, patient in rows:
        days_overdue = (today - item.due_date).days
        tasks = sorted(tasks_by_patient.get(patient.id, []), key=lambda t: ({"URGENT": 0, "HIGH": 1}.get(t.priority, 2), t.created_at))
        reply = last_reply.get(patient.id)
        msg = last_msg.get(patient.id)
        if view == "overdue" and days_overdue <= 0:
            continue
        if view == "upcoming" and days_overdue > 0:
            continue
        if view == "attention" and days_overdue <= 0 and not tasks and item.status != ItemStatus.PENDING:
            continue
        if queue and not any(t.queue == queue for t in tasks):
            continue
        if channel_failures and not (msg and msg.status == MessageStatus.FAILED):
            continue
        statement = choice = None
        if reply and reply.input_mode == InputMode.BUTTON:  # a tapped button is a choice, not the patient's words
            choice = CHOICE_LABELS.get((reply.text or "").upper(), reply.text)
        elif reply:
            statement = reply.corrected_text or reply.text or reply.transcript
        out.append({
            "patient": S.patient_brief(patient),
            "item": S.item_dict(item, today),
            "days_overdue": max(days_overdue, 0),
            "due_in_days": max(-days_overdue, 0),
            "state": _state(item, tasks, reply),
            "next_action": _next_action(item, tasks, reply, days_overdue, msg, patient),
            "latest_statement": statement,
            "latest_choice": choice,
            "latest_reply_status": reply.status if reply else None,
            "latest_reply_at": S.iso(reply.created_at) if reply else None,
            "last_message": {"status": msg.status, "label": S.STATUS_LABEL.get(msg.status), "channel": msg.channel,
                             "at": S.iso(msg.created_at)} if msg else None,
            "open_tasks": [{"id": str(t.id), "category": t.category, "queue": t.queue, "priority": t.priority,
                            "status": t.status, "assignee": names.get(t.assignee_user_id),
                            "escalated": bool(t.escalated_at), "source_id": t.source_id} for t in tasks],
        })
    out.sort(key=lambda r: (-r["days_overdue"], r["due_in_days"], r["patient"]["name"]))
    return {"today": today.isoformat(), "rows": out, "sort": "Days overdue, then due date (objective fields only)"}


def _state(item: FollowUpItem, tasks: list[CareTask], reply: PatientReply | None) -> str:
    if any(t.category == "URGENT_CONCERN" for t in tasks):
        return "Urgent concern reported"
    if item.status == ItemStatus.BOOKED:
        return "New time booked"
    if item.status == ItemStatus.CONFIRMED_BY_PATIENT:
        return "Patient confirmed (self-reported)"
    if reply and reply.status in ("NEEDS_CONFIRMATION", "NEEDS_CLARIFICATION"):
        return "Waiting for patient choice"
    if tasks:
        return "Staff action needed"
    return "No response yet"


def _next_action(item, tasks, reply, days_overdue, msg, patient) -> str:
    if patient.opted_out:
        return "Opted out of messages — call if clinically needed"
    for t in tasks:
        if t.category == "URGENT_CONCERN":
            return "Clinician to call now"
    if msg and msg.status == "FAILED":
        return "Message failed — call patient"
    for t in tasks:
        return {"CLINICAL_QUESTION": "Clinician to answer question", "CALLBACK": "Call patient back",
                "BARRIER": "Help with reported barrier", "RESCHEDULE": "Arrange a new time",
                "BOOKING_FAILED": "Book a time manually", "UNCLEAR_INPUT": "Call to clarify",
                "OVERDUE_FOLLOWUP": "Call overdue patient", "DOCUMENT_REVIEW": "Review shared document",
                "MESSAGE_FAILURE": "Contact patient another way"}.get(t.category, "Review task")
    if item.status in (ItemStatus.BOOKED, ItemStatus.CONFIRMED_BY_PATIENT):
        return "Nothing needed until the visit"
    if days_overdue > 0:
        return "Call or send reminder"
    return "Reminder scheduled"


def timeline_for(db: Session, patient: Patient, *, staff: Staff | None, since=None, limit: int = 200) -> list[dict]:
    q = select(TimelineEvent).where(TimelineEvent.patient_id == patient.id)
    if staff is None:
        q = q.where(TimelineEvent.visibility == "PATIENT_AND_STAFF")
    elif not (staff.is_clinical or staff.role == Role.ADMIN):
        q = q.where(TimelineEvent.visibility != "CLINICAL")
    if since:
        q = q.where(TimelineEvent.occurred_at >= since)
    return [S.timeline_dict(e) for e in db.scalars(q.order_by(TimelineEvent.occurred_at.desc()).limit(limit)).all()]


def active_plan(db: Session, patient_id: uuid.UUID) -> FollowUpPlan | None:
    return db.scalar(select(FollowUpPlan).where(FollowUpPlan.patient_id == patient_id,
                                                FollowUpPlan.status == PlanStatus.ACTIVE))


def appointments_for(db: Session, clinic: Clinic, patient_id: uuid.UUID) -> list[dict]:
    rows = db.execute(select(Appointment, AvailabilitySlot).join(AvailabilitySlot, AvailabilitySlot.id == Appointment.slot_id)
                      .where(Appointment.patient_id == patient_id).order_by(AvailabilitySlot.starts_at.desc())).all()
    tz = clinic_tz(clinic)
    return [S.appointment_dict(a, slot_label(s.starts_at.astimezone(tz), year=True) + f", {s.provider_label}")
            for a, s in rows]


def visit_capsule(db: Session, staff: Staff, clinic: Clinic, patient: Patient) -> dict[str, Any]:
    """Compact, source-linked pre-visit view. Facts only; AI output is labelled and drillable to source."""
    today = clinic_today(clinic)
    plan = active_plan(db, patient.id)
    approver = None
    if plan and plan.approved_by_user_id:
        approver = _names(db, {plan.approved_by_user_id}).get(plan.approved_by_user_id)
    since = patient.last_visit_at
    replies = db.scalars(select(PatientReply).where(PatientReply.patient_id == patient.id)
                         .order_by(PatientReply.created_at.desc()).limit(20)).all()
    reason = next((r for r in replies if (r.corrected_text or r.text or r.transcript) and r.input_mode != "BUTTON"), None)
    tasks = db.scalars(select(CareTask).where(CareTask.patient_id == patient.id, visible_task_filter(staff))
                       .order_by(CareTask.created_at.desc()).limit(30)).all()
    names = _names(db, {t.assignee_user_id for t in tasks if t.assignee_user_id})
    artifacts = db.scalars(select(SourceArtifact).where(SourceArtifact.patient_id == patient.id,
                                                        SourceArtifact.source_type != "VOICE_NOTE",
                                                        SourceArtifact.deleted_at.is_(None))
                           .order_by(SourceArtifact.created_at.desc()).limit(10)).all()
    fields = []
    for prop in db.scalars(select(ExtractionProposal).where(ExtractionProposal.patient_id == patient.id)
                           .order_by(ExtractionProposal.created_at.desc()).limit(5)).all():
        fields += [dict(S.field_dict(f), proposal_id=str(prop.id), proposal_status=prop.status) for f in prop.fields]
    requests = db.scalars(select(AppointmentRequest).where(AppointmentRequest.patient_id == patient.id,
                                                           AppointmentRequest.failure_reason != "SUPERSEDED")
                          .order_by(AppointmentRequest.created_at.desc()).limit(5)).all()
    msgs = db.scalars(select(OutboundMessage).where(OutboundMessage.patient_id == patient.id,
                                                    OutboundMessage.status != MessageStatus.SCHEDULED)
                      .order_by(OutboundMessage.created_at.desc()).limit(6)).all()
    reported = [S.task_dict(t) for t in tasks if t.patient_statement and t.category in (
        "BARRIER", "CLINICAL_QUESTION", "URGENT_CONCERN", "CALLBACK")]
    audit(db, clinic_id=clinic.id, action="VIEW_VISIT_CAPSULE", actor=staff, object_type="patient",
          object_id=patient.id, patient_id=patient.id)
    return {
        "patient": S.patient_brief(patient),
        "generated_note": "Assembled from recorded events. Nothing here is a clinical finding.",
        "reason_for_contact": {
            "patient_words": (reason.corrected_text or reason.text or reason.transcript) if reason else None,
            "ai_gloss": (reason.understanding or {}).get("english_gloss") if reason else None,
            "ai_intents": (reason.understanding or {}).get("intents") if reason else None,
            "at": S.iso(reason.created_at) if reason else None,
            "reply_id": str(reason.id) if reason else None,
        },
        "plan": S.plan_dict(plan, today, approver) if plan else None,
        "timeline_since_last_visit": timeline_for(db, patient, staff=staff, since=since, limit=40),
        "documents": [S.artifact_dict(a) for a in artifacts],
        "extracted_fields": fields,
        "patient_reported": reported,
        "requests": [S.request_dict(r) for r in requests],
        "appointments": appointments_for(db, clinic, patient.id),
        "open_tasks": [S.task_dict(t, assignee=names.get(t.assignee_user_id)) for t in tasks if t.status in OPEN_TASK_STATES],
        "recent_messages": [S.message_dict(m) for m in msgs],
    }


def care_passport(db: Session, clinic: Clinic, patient: Patient) -> dict[str, Any]:
    """The patient's own, permissioned view: approved plan, real statuses, what they told us."""
    from app.services.patients import consent_state

    today = clinic_today(clinic)
    plan = active_plan(db, patient.id)
    requests = db.scalars(select(AppointmentRequest).where(AppointmentRequest.patient_id == patient.id,
                                                           AppointmentRequest.failure_reason != "SUPERSEDED")
                          .order_by(AppointmentRequest.created_at.desc()).limit(5)).all()
    tasks = db.scalars(select(CareTask).where(CareTask.patient_id == patient.id)
                       .order_by(CareTask.created_at.desc()).limit(10)).all()
    docs = db.scalars(select(SourceArtifact).where(SourceArtifact.patient_id == patient.id,
                                                   SourceArtifact.uploaded_by_patient.is_(True),
                                                   SourceArtifact.source_type != "VOICE_NOTE",
                                                   SourceArtifact.deleted_at.is_(None))
                      .order_by(SourceArtifact.created_at.desc()).limit(10)).all()
    document_proposals = db.scalars(select(ExtractionProposal).where(
        ExtractionProposal.patient_id == patient.id,
        ExtractionProposal.clinic_id == clinic.id,
        ExtractionProposal.artifact_id.in_([d.id for d in docs]))).all() if docs else []
    document_status = {p.artifact_id: p.status for p in document_proposals}
    msgs = db.scalars(select(OutboundMessage).where(OutboundMessage.patient_id == patient.id,
                                                    OutboundMessage.status != MessageStatus.SCHEDULED)
                      .order_by(OutboundMessage.created_at.desc()).limit(5)).all()
    checklist = []
    if plan:
        for i in plan.items:
            if i.status in (ItemStatus.COMPLETED, ItemStatus.CANCELLED):
                continue
            checklist.append({"label": i.label, "due_date": S.iso(i.due_date), "status": i.status})
    you_told_us = [{"what": t.title, "your_words": t.patient_statement, "barrier": t.barrier_category,
                    "status": "Closed" if t.status not in OPEN_TASK_STATES else "Clinic is working on it",
                    "at": S.iso(t.created_at)} for t in tasks if t.patient_statement or t.barrier_category]
    return {
        "patient": {"name": patient.display_name, "language": patient.preferred_language,
                    "opted_out": patient.opted_out},
        "clinic": {"name": clinic.name, "phone": clinic.phone},
        "plan": S.plan_dict(plan, today) if plan else None,
        "checklist": checklist,
        "appointments": appointments_for(db, clinic, patient.id),
        "requests": [S.request_dict(r) for r in requests],
        "you_told_us": you_told_us,
        "documents": [{"filename": d.filename, "uploaded_at": S.iso(d.created_at),
                       "status": document_status.get(d.id, "RECEIVED")} for d in docs],
        "messages": [{"kind": m.kind, "status_label": S.STATUS_LABEL.get(m.status), "at": S.iso(m.created_at),
                      "channel": m.channel} for m in msgs],
        "consents": consent_state(db, patient.id),
        "timeline": timeline_for(db, patient, staff=None, limit=30),
    }


def patient_detail(db: Session, staff: Staff, clinic: Clinic, patient: Patient) -> dict[str, Any]:
    from app.services.patients import consent_state

    today = clinic_today(clinic)
    plans = db.scalars(select(FollowUpPlan).where(FollowUpPlan.patient_id == patient.id)
                       .order_by(FollowUpPlan.created_at.desc()).limit(10)).all()
    names = _names(db, {p.approved_by_user_id for p in plans if p.approved_by_user_id})
    replies = db.scalars(select(PatientReply).where(PatientReply.patient_id == patient.id)
                         .order_by(PatientReply.created_at.desc()).limit(20)).all()
    msgs = db.scalars(select(OutboundMessage).where(OutboundMessage.patient_id == patient.id)
                      .order_by(OutboundMessage.scheduled_for.desc()).limit(40)).all()
    tasks = db.scalars(select(CareTask).where(CareTask.patient_id == patient.id, visible_task_filter(staff))
                       .order_by(CareTask.created_at.desc()).limit(40)).all()
    audit(db, clinic_id=clinic.id, action="VIEW_PATIENT", actor=staff, object_type="patient", object_id=patient.id,
          patient_id=patient.id)
    tnames = _names(db, {t.assignee_user_id for t in tasks if t.assignee_user_id})
    return {
        "patient": S.patient_brief(patient),
        "consents": consent_state(db, patient.id),
        "plans": [S.plan_dict(p, today, names.get(p.approved_by_user_id)) for p in plans],
        "replies": [S.reply_dict(r) for r in replies],
        "messages": [S.message_dict(m) for m in msgs],
        "tasks": [S.task_dict(t, assignee=tnames.get(t.assignee_user_id), with_events=True) for t in tasks],
        "appointments": appointments_for(db, clinic, patient.id),
        "today": today.isoformat(),
    }


def field_by_id(db: Session, clinic_id: uuid.UUID, field_id: uuid.UUID) -> ExtractedField | None:
    f = db.get(ExtractedField, field_id)
    return f if f and f.clinic_id == clinic_id else None


def week_dates(today: date, n: int = 14) -> list[str]:
    return [(today + timedelta(days=i)).isoformat() for i in range(n)]
