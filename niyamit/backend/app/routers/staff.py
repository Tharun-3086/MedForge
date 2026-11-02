"""Clinic dashboard API: worklist, patients, plans, tasks, messages, booking, settings, audit and metrics.

Every handler resolves ids through `app.services.guards`, so records from another clinic are never returned."""
from __future__ import annotations

import string
import uuid
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app import serializers as S
from app.ai.pipeline import provider_status
from app.audit import audit
from app.config import settings
from app.db import get_db, utcnow
from app.enums import (
    CLINICAL_TASK_CATEGORIES,
    OPEN_TASK_STATES,
    ConsentPurpose,
    ConsentStatus,
    ItemKind,
    ItemStatus,
    MessageStatus,
    PlanStatus,
    ProposalStatus,
    ReplyStatus,
    Role,
    TaskStatus,
)
from app.models import (
    AppointmentRequest,
    AuditEvent,
    CareTask,
    Clinic,
    ExtractionProposal,
    FollowUpItem,
    FollowUpPlan,
    Membership,
    MessageTemplate,
    OutboundMessage,
    Patient,
    PatientReply,
    ProviderEvent,
    User,
)
from app.security import Staff, current_staff, require_roles, require_staff
from app.services import booking, guards, messaging, metrics, patients, plans, tasks, views
from app.services.common import clinic_today, current_item, get_clinic
from app.services.templates import TEMPLATES

router = APIRouter(prefix="/v1", tags=["clinic"])

TASK_OUTCOMES = {
    "REACHED_PATIENT": "Reached the patient",
    "BOOKED": "New time booked",
    "FOLLOW_UP_COMPLETED": "Follow-up completed",
    "ANSWERED_BY_CLINICIAN": "Clinician answered",
    "PATIENT_WILL_ATTEND": "Patient will attend",
    "PATIENT_DECLINED": "Patient declined",
    "NO_ANSWER": "No answer after attempts",
    "WRONG_NUMBER": "Wrong or unreachable number",
    "REFERRED": "Referred elsewhere",
    "OTHER": "Other (see note)",
}
CATEGORY_LABELS = {
    "RESCHEDULE": "Reschedule", "CALLBACK": "Call back", "BARRIER": "Barrier", "CLINICAL_QUESTION": "Clinical question",
    "URGENT_CONCERN": "Possible urgent concern", "UNCLEAR_INPUT": "Unclear message", "MESSAGE_FAILURE": "Message failed",
    "OVERDUE_FOLLOWUP": "Overdue follow-up", "DOCUMENT_REVIEW": "Document to review", "BOOKING_FAILED": "Booking failed",
}


def clinic_of(db: Session, staff: Staff) -> Clinic:
    return get_clinic(db, staff.clinic_id)


# ------------------------------------------------------------------ dashboard
@router.get("/dashboard")
def dashboard(staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    clinic = clinic_of(db, staff)
    today = clinic_today(clinic)
    base = (select(func.count()).select_from(FollowUpItem)
            .join(FollowUpPlan, FollowUpItem.plan_id == FollowUpPlan.id)
            .where(FollowUpItem.clinic_id == clinic.id, FollowUpPlan.status == PlanStatus.ACTIVE))
    open_states = [ItemStatus.PENDING, ItemStatus.CONFIRMED_BY_PATIENT]
    overdue = db.scalar(base.where(FollowUpItem.status.in_(open_states + [ItemStatus.BOOKED]),
                                   FollowUpItem.due_date < today)) or 0
    due_week = db.scalar(base.where(FollowUpItem.status.in_(open_states + [ItemStatus.BOOKED]),
                                    FollowUpItem.due_date >= today,
                                    FollowUpItem.due_date <= today + timedelta(days=7))) or 0
    task_rows = db.execute(select(CareTask.queue, CareTask.priority, func.count())
                           .where(CareTask.clinic_id == clinic.id,
                                  CareTask.status.in_([s.value for s in OPEN_TASK_STATES]),
                                  views.visible_task_filter(staff))
                           .group_by(CareTask.queue, CareTask.priority)).all()
    by_queue: dict[str, int] = {}
    urgent = 0
    for queue, priority, n in task_rows:
        by_queue[queue] = by_queue.get(queue, 0) + n
        urgent += n if priority == "URGENT" else 0
    failed = db.scalar(select(func.count()).select_from(OutboundMessage).where(
        OutboundMessage.clinic_id == clinic.id, OutboundMessage.status.in_([MessageStatus.FAILED, MessageStatus.UNKNOWN]),
        OutboundMessage.created_at > utcnow() - timedelta(days=7))) or 0
    to_review = db.scalar(select(func.count()).select_from(ExtractionProposal).where(
        ExtractionProposal.clinic_id == clinic.id,
        ExtractionProposal.status.in_([ProposalStatus.NEEDS_REVIEW, ProposalStatus.EXTRACTION_FAILED,
                                       ProposalStatus.EXTRACTION_PENDING]))) or 0
    waiting = db.scalar(select(func.count()).select_from(PatientReply).where(
        PatientReply.clinic_id == clinic.id,
        PatientReply.status.in_([ReplyStatus.NEEDS_CONFIRMATION, ReplyStatus.NEEDS_CLARIFICATION]),
        PatientReply.created_at > utcnow() - timedelta(days=7))) or 0
    return {"today": today.isoformat(), "overdue": overdue, "due_this_week": due_week,
            "open_tasks": sum(by_queue.values()), "open_tasks_by_queue": by_queue, "urgent_open": urgent,
            "failed_messages_7d": failed, "documents_to_review": to_review, "waiting_on_patient_choice": waiting}


@router.get("/worklists/{view}")
def worklist(view: Literal["attention", "overdue", "upcoming", "all"],
             days_ahead: int = Query(7, ge=0, le=60), queue: str | None = None, channel_failures: bool = False,
             staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    clinic = clinic_of(db, staff)
    return views.worklist(db, staff, clinic, view=view, days_ahead=days_ahead, queue=queue,
                          channel_failures=channel_failures)


# ------------------------------------------------------------------ patients
class PatientIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(max_length=32)
    birth_year: int | None = Field(default=None, ge=1900, le=2026)
    preferred_language: Literal["en", "hi", "te"] = "en"
    preferred_channel: Literal["SIMULATED", "WHATSAPP"] = "SIMULATED"
    external_ref: str = Field(default="", max_length=60)
    consent_reminders: bool = False
    consent_ai: bool = False


class PatientPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    birth_year: int | None = Field(default=None, ge=1900, le=2026)
    preferred_language: Literal["en", "hi", "te"] | None = None
    preferred_channel: Literal["SIMULATED", "WHATSAPP"] | None = None
    external_ref: str | None = Field(default=None, max_length=60)


@router.get("/patients")
def list_patients(q: str = "", limit: int = Query(100, ge=1, le=500), staff: Staff = Depends(require_staff),
                  db: Session = Depends(get_db)) -> dict:
    clinic = clinic_of(db, staff)
    today = clinic_today(clinic)
    stmt = select(Patient).where(Patient.clinic_id == clinic.id)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Patient.display_name.ilike(like), Patient.phone_e164.ilike(like),
                              Patient.external_ref.ilike(like)))
    rows = db.scalars(stmt.order_by(Patient.display_name).limit(limit)).all()
    ids = [p.id for p in rows]
    open_counts = dict(db.execute(select(CareTask.patient_id, func.count()).where(
        CareTask.patient_id.in_(ids), CareTask.status.in_([s.value for s in OPEN_TASK_STATES]),
        views.visible_task_filter(staff)).group_by(CareTask.patient_id)).all()) if ids else {}
    out = []
    for p in rows:
        item = current_item(db, p.id)
        out.append({**S.patient_brief(p), "next_item": S.item_dict(item, today) if item else None,
                    "open_tasks": open_counts.get(p.id, 0)})
    return {"patients": out}


@router.post("/patients", status_code=201)
def create_patient(body: PatientIn, staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    clinic = clinic_of(db, staff)
    p = patients.create_patient(db, staff, clinic, name=body.display_name, phone=body.phone,
                                birth_year=body.birth_year, language=body.preferred_language,
                                channel=body.preferred_channel, external_ref=body.external_ref,
                                consent_reminders=body.consent_reminders, consent_ai=body.consent_ai)
    db.commit()
    return S.patient_brief(p)


@router.get("/patients/{patient_id}")
def get_patient(patient_id: str, staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    p = guards.get_patient(db, staff, patient_id)
    out = views.patient_detail(db, staff, clinic_of(db, staff), p)
    db.commit()  # view audit row
    return out


@router.patch("/patients/{patient_id}")
def update_patient(patient_id: str, body: PatientPatch, staff: Staff = Depends(require_staff),
                   db: Session = Depends(get_db)) -> dict:
    p = guards.get_patient(db, staff, patient_id)
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(p, k, v.strip() if isinstance(v, str) else v)
    audit(db, clinic_id=p.clinic_id, action="PATIENT_UPDATED", actor=staff, object_type="patient", object_id=p.id,
          patient_id=p.id, detail={"fields": sorted(changes)})
    db.commit()
    return S.patient_brief(p)


@router.get("/patients/{patient_id}/timeline")
def patient_timeline(patient_id: str, staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    p = guards.get_patient(db, staff, patient_id)
    return {"events": views.timeline_for(db, p, staff=staff)}


@router.get("/patients/{patient_id}/capsule")
def visit_capsule(patient_id: str, staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    p = guards.get_patient(db, staff, patient_id)
    out = views.visit_capsule(db, staff, clinic_of(db, staff), p)
    db.commit()
    return out


class ConsentIn(BaseModel):
    purpose: Literal["REMINDERS", "AI_PROCESSING", "REPORT_SHARING"]
    granted: bool


@router.post("/patients/{patient_id}/consents")
def record_consent(patient_id: str, body: ConsentIn, staff: Staff = Depends(require_staff),
                   db: Session = Depends(get_db)) -> dict:
    p = guards.get_patient(db, staff, patient_id)
    patients.record_consent(db, p, ConsentPurpose(body.purpose),
                            ConsentStatus.GRANTED if body.granted else ConsentStatus.WITHDRAWN,
                            method="STAFF_RECORDED", staff=staff)
    if body.purpose == "REMINDERS" and not body.granted:
        messaging.suppress_pending(db, p, "NO_MESSAGING_CONSENT")
    db.commit()
    return {"consents": patients.consent_state(db, p.id)}


@router.post("/patients/{patient_id}/opt-out")
def staff_opt_out(patient_id: str, staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    p = guards.get_patient(db, staff, patient_id)
    suppressed = patients.opt_out(db, clinic_of(db, staff), p, method="STAFF_RECORDED", staff=staff)
    db.commit()
    return {"opted_out": True, "suppressed": suppressed}


@router.post("/patients/{patient_id}/opt-in")
def staff_opt_in(patient_id: str, staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    p = guards.get_patient(db, staff, patient_id)
    patients.opt_in(db, p, method="STAFF_RECORDED", staff=staff)
    db.commit()
    return {"opted_out": False}


@router.post("/patients/{patient_id}/access-link")
def access_link(patient_id: str, staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    p = guards.get_patient(db, staff, patient_id)
    link = patients.staff_access_link(db, staff, p)
    db.commit()
    return {"link": link, "expires_in_hours": 24, "note": "Share only with the patient. The link asks for the year of birth."}


class ReminderIn(BaseModel):
    item_id: str | None = None
    client_key: str | None = Field(default=None, max_length=64)


@router.post("/patients/{patient_id}/reminders")
def send_reminder(patient_id: str, body: ReminderIn, staff: Staff = Depends(require_staff),
                  db: Session = Depends(get_db)) -> dict:
    p = guards.get_patient(db, staff, patient_id)
    item = guards.get_item(db, staff, body.item_id) if body.item_id else current_item(db, p.id)
    if item is None or item.patient_id != p.id:
        raise HTTPException(409, "This patient has no open follow-up to remind about.")
    msg = plans.manual_reminder(db, staff, clinic_of(db, staff), p, item, client_key=body.client_key)
    db.commit()
    return S.message_dict(msg)


# ------------------------------------------------------------------ plans
class PlanItemIn(BaseModel):
    kind: ItemKind
    due_date: date
    label: str | None = Field(default=None, max_length=120)


class PlanIn(BaseModel):
    patient_id: str
    items: list[PlanItemIn] = Field(min_length=1, max_length=12)
    notes: str = Field(default="", max_length=2000)
    approve: bool = True


class ReasonIn(BaseModel):
    reason: str = Field(default="", max_length=500)


class NoteIn(BaseModel):
    note: str = Field(default="", max_length=2000)


@router.post("/follow-up-plans", status_code=201)
def create_plan(body: PlanIn, staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    """Staff enter a plan by hand. It becomes ACTIVE only if the author's role may approve plans."""
    clinic = clinic_of(db, staff)
    p = guards.get_patient(db, staff, body.patient_id)
    plan = plans.create_plan(db, staff, clinic, p, [i.model_dump() for i in body.items], notes=body.notes)
    if body.approve and plans.can_approve(staff, clinic):
        plans.approve_plan(db, staff, clinic, plan)
    db.commit()
    return S.plan_dict(plan, clinic_today(clinic))


@router.post("/follow-up-plans/{plan_id}/approve")
def approve_plan(plan_id: str, staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    clinic = clinic_of(db, staff)
    plan = guards.get_plan(db, staff, plan_id)
    plans.approve_plan(db, staff, clinic, plan)
    db.commit()
    return S.plan_dict(plan, clinic_today(clinic))


@router.post("/follow-up-plans/{plan_id}/cancel")
def cancel_plan(plan_id: str, body: ReasonIn, staff: Staff = Depends(require_staff),
                db: Session = Depends(get_db)) -> dict:
    clinic = clinic_of(db, staff)
    plan = guards.get_plan(db, staff, plan_id)
    plans.cancel_plan(db, staff, clinic, plan, body.reason)
    db.commit()
    return S.plan_dict(plan, clinic_today(clinic))


@router.post("/follow-up-items/{item_id}/complete")
def complete_item(item_id: str, body: NoteIn, staff: Staff = Depends(require_staff),
                  db: Session = Depends(get_db)) -> dict:
    clinic = clinic_of(db, staff)
    item = guards.get_item(db, staff, item_id)
    plans.complete_item(db, staff, clinic, item, body.note)
    db.commit()
    return S.item_dict(item, clinic_today(clinic))


# ------------------------------------------------------------------ tasks
@router.get("/tasks/meta")
def task_meta(_: Staff = Depends(require_staff)) -> dict:
    return {"outcomes": TASK_OUTCOMES, "categories": CATEGORY_LABELS, "queues": ["RECEPTION", "NURSE", "DOCTOR"]}


@router.get("/tasks")
def list_tasks(status: Literal["open", "closed", "all"] = "open", queue: str | None = None,
               category: str | None = None, mine: bool = False, patient_id: str | None = None,
               limit: int = Query(200, ge=1, le=500), staff: Staff = Depends(require_staff),
               db: Session = Depends(get_db)) -> dict:
    stmt = select(CareTask, Patient).join(Patient, Patient.id == CareTask.patient_id).where(
        CareTask.clinic_id == staff.clinic_id, views.visible_task_filter(staff))
    open_values = [s.value for s in OPEN_TASK_STATES]
    if status == "open":
        stmt = stmt.where(CareTask.status.in_(open_values))
    elif status == "closed":
        stmt = stmt.where(CareTask.status.notin_(open_values))
    if queue:
        stmt = stmt.where(CareTask.queue == queue)
    if category:
        stmt = stmt.where(CareTask.category == category)
    if mine:
        stmt = stmt.where(CareTask.assignee_user_id == staff.user_id)
    if patient_id:
        stmt = stmt.where(CareTask.patient_id == guards.get_patient(db, staff, patient_id).id)
    priority = case((CareTask.priority == "URGENT", 0), (CareTask.priority == "HIGH", 1), else_=2)
    rows = db.execute(stmt.order_by(priority, CareTask.due_at).limit(limit)).all()
    names = views._names(db, {t.assignee_user_id for t, _ in rows if t.assignee_user_id})
    now = utcnow()
    return {"tasks": [{**S.task_dict(t, p, names.get(t.assignee_user_id)),
                       "category_label": CATEGORY_LABELS.get(t.category, t.category),
                       "overdue": t.status in open_values and t.due_at < now} for t, p in rows]}


def _task_detail(db: Session, staff: Staff, task: CareTask) -> dict:
    db.expire(task, ["events"])  # events are added as rows; reload the collection to include them
    patient = db.get(Patient, task.patient_id)
    names = views._names(db, {task.assignee_user_id} if task.assignee_user_id else set())
    out = S.task_dict(task, patient, names.get(task.assignee_user_id), with_events=True)
    out["category_label"] = CATEGORY_LABELS.get(task.category, task.category)
    if task.source_type == "patient_reply" and task.source_id:
        reply = db.get(PatientReply, uuid.UUID(task.source_id))
        out["source"] = S.reply_dict(reply) if reply and reply.clinic_id == staff.clinic_id else None
    elif task.source_type == "appointment_request" and task.source_id:
        req = db.get(AppointmentRequest, uuid.UUID(task.source_id))
        out["source"] = S.request_dict(req) if req and req.clinic_id == staff.clinic_id else None
    elif task.source_type == "outbound_message" and task.source_id:
        m = db.get(OutboundMessage, uuid.UUID(task.source_id))
        out["source"] = S.message_dict(m) if m and m.clinic_id == staff.clinic_id else None
    return out


@router.get("/tasks/{task_id}")
def get_task(task_id: str, staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    return _task_detail(db, staff, guards.get_task(db, staff, task_id))


class AssignIn(BaseModel):
    assignee_user_id: str | None = None
    note: str = Field(default="", max_length=500)


class CloseIn(BaseModel):
    outcome: str = Field(default="", max_length=60)
    note: str = Field(default="", max_length=2000)


@router.post("/tasks/{task_id}/assign")
def assign_task(task_id: str, body: AssignIn, staff: Staff = Depends(require_staff),
                db: Session = Depends(get_db)) -> dict:
    task = guards.get_task(db, staff, task_id)
    assignee = guards._uuid(body.assignee_user_id) if body.assignee_user_id else staff.user_id
    if assignee is None:
        raise HTTPException(422, "Unknown staff member.")
    tasks.transition(db, staff, task, TaskStatus.ASSIGNED, note=body.note or "Assigned", assignee=assignee)
    db.commit()
    return _task_detail(db, staff, task)


@router.post("/tasks/{task_id}/start")
def start_task(task_id: str, staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    task = guards.get_task(db, staff, task_id)
    tasks.transition(db, staff, task, TaskStatus.IN_PROGRESS, note="Started",
                     assignee=task.assignee_user_id or staff.user_id)
    db.commit()
    return _task_detail(db, staff, task)


def _close(db: Session, staff: Staff, task_id: str, new: TaskStatus, body: CloseIn) -> dict:
    task = guards.get_task(db, staff, task_id)
    if new in (TaskStatus.RESOLVED, TaskStatus.UNABLE_TO_RESOLVE) and body.outcome not in TASK_OUTCOMES:
        raise HTTPException(422, "Choose an outcome.")
    if body.outcome == "OTHER" and not body.note.strip():
        raise HTTPException(422, "Add a note when the outcome is 'Other'.")
    tasks.transition(db, staff, task, new, note=body.note.strip(), outcome=body.outcome)
    db.commit()
    return _task_detail(db, staff, task)


@router.post("/tasks/{task_id}/resolve")
def resolve_task(task_id: str, body: CloseIn, staff: Staff = Depends(require_staff),
                 db: Session = Depends(get_db)) -> dict:
    return _close(db, staff, task_id, TaskStatus.RESOLVED, body)


@router.post("/tasks/{task_id}/unable")
def unable_task(task_id: str, body: CloseIn, staff: Staff = Depends(require_staff),
                db: Session = Depends(get_db)) -> dict:
    return _close(db, staff, task_id, TaskStatus.UNABLE_TO_RESOLVE, body)


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str, body: CloseIn, staff: Staff = Depends(require_staff),
                db: Session = Depends(get_db)) -> dict:
    if not body.note.strip():
        raise HTTPException(422, "Give a reason for cancelling the task.")
    return _close(db, staff, task_id, TaskStatus.CANCELLED, body)


@router.post("/tasks/{task_id}/reopen")
def reopen_task(task_id: str, body: CloseIn, staff: Staff = Depends(require_staff),
                db: Session = Depends(get_db)) -> dict:
    return _close(db, staff, task_id, TaskStatus.OPEN, body)


# ------------------------------------------------------------------ messages
MESSAGE_GROUPS: tuple[tuple[str, str, tuple[str, ...], bool], ...] = (
    # key, title, statuses, upcoming (soonest first) vs history (latest first)
    ("attention", "Needs attention", (MessageStatus.FAILED, MessageStatus.UNKNOWN), False),
    ("sent", "Sent", (MessageStatus.DELIVERED, MessageStatus.SENT_TO_PROVIDER, MessageStatus.SENDING), False),
    ("upcoming", "Coming up", (MessageStatus.SCHEDULED, MessageStatus.QUEUED), True),
    ("not_sent", "Not sent", (MessageStatus.SUPPRESSED,), False),
)


@router.get("/messages")
def list_messages(group: str | None = None, patient_id: str | None = None, limit: int = Query(25, ge=1, le=500),
                  staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    """Messages in four groups: failures first, then what was sent (latest first), what is coming (soonest first)
    and what was held back. Without a group, each group shows its first `limit` rows and its total."""
    base = select(OutboundMessage, Patient).join(Patient, Patient.id == OutboundMessage.patient_id).where(
        OutboundMessage.clinic_id == staff.clinic_id)
    count_q = select(OutboundMessage.status, func.count()).where(OutboundMessage.clinic_id == staff.clinic_id)
    if patient_id:
        pid = guards.get_patient(db, staff, patient_id).id
        base, count_q = base.where(OutboundMessage.patient_id == pid), count_q.where(OutboundMessage.patient_id == pid)
    counts = {str(k): v for k, v in db.execute(count_q.group_by(OutboundMessage.status)).all()}
    if group and group not in {g[0] for g in MESSAGE_GROUPS}:
        raise HTTPException(422, "Unknown message group.")
    latest = func.coalesce(OutboundMessage.failed_at, OutboundMessage.delivered_at, OutboundMessage.sent_at,
                           OutboundMessage.scheduled_for)
    out = []
    for key, title, statuses, upcoming in MESSAGE_GROUPS:
        if group and key != group:
            continue
        order = (OutboundMessage.scheduled_for.asc(),) if upcoming else (latest.desc(),)
        rows = db.execute(base.where(OutboundMessage.status.in_(statuses)).order_by(*order)
                          .limit(500 if group else limit)).all()
        out.append({"key": key, "title": title, "total": sum(counts.get(s, 0) for s in statuses),
                    "messages": [S.message_dict(m, p) for m, p in rows]})
    return {"groups": out, "counts": counts, "status_labels": S.STATUS_LABEL}


@router.post("/messages/{message_id}/retry")
def retry_message(message_id: str, staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    m = guards.get_message(db, staff, message_id)
    if m.status != MessageStatus.FAILED:
        raise HTTPException(409, "Only failed messages can be retried.")
    try:
        messaging.retry_failed(db, m)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    audit(db, clinic_id=m.clinic_id, action="MESSAGE_RETRY", actor=staff, object_type="outbound_message",
          object_id=m.id, patient_id=m.patient_id)
    db.commit()
    return S.message_dict(m)


# ------------------------------------------------------------------ booking
@router.get("/availability")
def availability(day: date | None = Query(None, alias="date"), window: str | None = None,
                 staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    clinic = clinic_of(db, staff)
    try:
        slots = booking.list_slots(db, clinic, day=day, window=window, limit=60)
    except booking.BookingUnavailable:
        raise HTTPException(503, "The booking service is unavailable. Arrange the time by phone.") from None
    return {"slots": [booking.slot_dict(s, clinic) for s in slots], "source": "Seeded demo availability"}


@router.get("/appointment-requests")
def appointment_requests(status: Literal["open", "all"] = "open", staff: Staff = Depends(require_staff),
                         db: Session = Depends(get_db)) -> dict:
    stmt = select(AppointmentRequest, Patient).join(Patient, Patient.id == AppointmentRequest.patient_id).where(
        AppointmentRequest.clinic_id == staff.clinic_id)
    if status == "open":
        stmt = stmt.where(AppointmentRequest.status.in_(["REQUESTED", "NEEDS_CLARIFICATION", "SLOTS_OFFERED",
                                                         "HANDED_TO_STAFF"]))
    rows = db.execute(stmt.order_by(AppointmentRequest.created_at.desc()).limit(200)).all()
    return {"requests": [{**S.request_dict(r), "patient": S.patient_brief(p)} for r, p in rows]}


class RequestIn(BaseModel):
    patient_id: str
    day_text: str = Field(default="", max_length=80)
    window: Literal["MORNING", "AFTERNOON", "EVENING"] | None = None
    note: str = Field(default="", max_length=500)


@router.post("/appointment-requests", status_code=201)
def create_request(body: RequestIn, staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    """A request is not a booking: it records what was asked and which real slots were offered."""
    from app.ai.dates import resolve_day_expression

    clinic = clinic_of(db, staff)
    p = guards.get_patient(db, staff, body.patient_id)
    res = resolve_day_expression(body.day_text, clinic_today(clinic)) if body.day_text.strip() else None
    req = booking.create_request(db, clinic, p, item=current_item(db, p.id), reply_id=None, requested_by="STAFF",
                                 day_text=body.day_text.strip() or None, requested=res.candidate if res else None,
                                 window=body.window, statement=body.note or None)
    offered = booking.offer_slots(db, clinic, req, day=res.candidate if res else None, days=res.options if res else None)
    audit(db, clinic_id=clinic.id, action="APPOINTMENT_REQUEST_CREATED", actor=staff, object_type="appointment_request",
          object_id=req.id, patient_id=p.id)
    db.commit()
    return {"request": S.request_dict(req), "slots": [booking.slot_dict(s, clinic) for s in offered],
            "question": res.question if res and res.question else None}


class BookIn(BaseModel):
    patient_id: str
    slot_id: str
    request_id: str | None = None
    client_key: str | None = Field(default=None, max_length=64)


@router.post("/appointments")
def staff_book(body: BookIn, staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    """Commit a booking for a server-validated slot. Same patient + slot is idempotent."""
    clinic = clinic_of(db, staff)
    p = guards.get_patient(db, staff, body.patient_id)
    req = guards.get_request(db, staff, body.request_id) if body.request_id else None
    if req and req.patient_id != p.id:
        raise HTTPException(422, "That request belongs to another patient.")
    slot_id = guards._uuid(body.slot_id)
    if slot_id is None:
        raise HTTPException(422, "Unknown slot.")
    auto_request = req is None
    if auto_request:  # keep the trail: which follow-up this booking is for, and who asked
        req = booking.create_request(db, clinic, p, item=current_item(db, p.id), reply_id=None, requested_by="STAFF",
                                     day_text=None, requested=None, window=None, statement=None)
    key = f"staff:{p.id}:{body.client_key or slot_id}"
    result = booking.commit_booking(db, clinic, p, slot_id=slot_id, request_id=req.id, idempotency_key=key,
                                    created_by="STAFF", staff_label=staff.label)
    if auto_request and not result.booked and req.status != "HANDED_TO_STAFF":
        req.status = "NOT_BOOKED"
    from app.services.replies import booking_outcome

    booking_outcome(db, req, result)
    db.commit()
    if not result.booked:
        msg = {"PROVIDER_UNAVAILABLE": "Booking service unavailable — not booked. A task was created.",
               "SLOT_UNAVAILABLE": "That slot is no longer available — not booked."}.get(result.reason, "Not booked.")
        raise HTTPException(409, msg)
    return {"booked": True, "reason": result.reason, "appointment": S.appointment_dict(result.appointment)}


@router.post("/appointments/{appointment_id}/cancel")
def cancel_appointment(appointment_id: str, body: ReasonIn, staff: Staff = Depends(require_staff),
                       db: Session = Depends(get_db)) -> dict:
    appt = guards.get_appointment(db, staff, appointment_id)
    if not body.reason.strip():
        raise HTTPException(422, "Give a reason for cancelling.")
    booking.cancel_appointment(db, clinic_of(db, staff), appt, reason=body.reason, actor_label=staff.label)
    db.commit()
    return S.appointment_dict(appt)


# ------------------------------------------------------------------ clinic settings & templates
class ClinicPatch(BaseModel):
    phone: str | None = Field(default=None, max_length=32)
    quiet_hours_start: int | None = Field(default=None, ge=0, le=23)
    quiet_hours_end: int | None = Field(default=None, ge=0, le=23)
    reminder_send_hour: int | None = Field(default=None, ge=6, le=20)
    reminder_offsets_days: list[int] | None = Field(default=None, max_length=5)
    overdue_nudge_days: list[int] | None = Field(default=None, max_length=5)
    overdue_task_after_days: int | None = Field(default=None, ge=1, le=60)
    plan_approver_roles: list[Literal["DOCTOR", "NURSE"]] | None = None
    clinical_queue: Literal["NURSE", "DOCTOR"] | None = None
    urgent_queue: Literal["NURSE", "DOCTOR"] | None = None
    task_due_hours: int | None = Field(default=None, ge=1, le=168)
    require_patient_verification: bool | None = None
    audio_retention_days: int | None = Field(default=None, ge=1, le=365)
    document_retention_days: int | None = Field(default=None, ge=30, le=3650)
    message_unit_cost_inr: float | None = Field(default=None, ge=0, le=10)


CLINIC_FIELDS = list(ClinicPatch.model_fields)


@router.get("/clinic")
def get_clinic_settings(staff: Staff = Depends(current_staff), db: Session = Depends(get_db)) -> dict:
    clinic = clinic_of(db, staff)
    return {"id": str(clinic.id), "name": clinic.name, "short_name": clinic.short_name, "timezone": clinic.timezone,
            "languages": clinic.languages, **{f: getattr(clinic, f) for f in CLINIC_FIELDS}}


@router.patch("/clinic")
def update_clinic(body: ClinicPatch, staff: Staff = Depends(require_roles(Role.ADMIN)),
                  db: Session = Depends(get_db)) -> dict:
    clinic = clinic_of(db, staff)
    changes = body.model_dump(exclude_none=True)
    if "reminder_offsets_days" in changes and any(not -14 <= d <= 0 for d in changes["reminder_offsets_days"]):
        raise HTTPException(422, "Reminder offsets must be between -14 and 0 days.")
    if "overdue_nudge_days" in changes and any(not 1 <= d <= 30 for d in changes["overdue_nudge_days"]):
        raise HTTPException(422, "Overdue nudges must be between 1 and 30 days after the due date.")
    if "plan_approver_roles" in changes and not changes["plan_approver_roles"]:
        raise HTTPException(422, "At least one role must be able to approve plans.")
    before = {k: getattr(clinic, k) for k in changes}
    for k, v in changes.items():
        setattr(clinic, k, sorted(set(v)) if isinstance(v, list) else v)
    audit(db, clinic_id=clinic.id, action="CLINIC_SETTINGS_CHANGED", actor=staff, object_type="clinic",
          object_id=clinic.id, detail={"before": before, "after": changes})
    db.commit()
    return get_clinic_settings(staff, db)


@router.get("/clinic/staff")
def clinic_staff(staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    rows = db.execute(select(User, Membership).join(Membership, Membership.user_id == User.id)
                      .where(Membership.clinic_id == staff.clinic_id, Membership.role != Role.OPERATOR,
                             User.is_active.is_(True)).order_by(User.name)).all()
    return {"staff": [{"id": str(u.id), "name": u.name, "role": m.role} for u, m in rows]}


@router.get("/clinic/templates")
def list_templates(staff: Staff = Depends(require_staff), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(MessageTemplate).where(MessageTemplate.clinic_id == staff.clinic_id)
                      .order_by(MessageTemplate.key, MessageTemplate.language, MessageTemplate.version.desc())).all()
    return {"templates": [{"id": str(t.id), "key": t.key, "language": t.language, "version": t.version,
                           "body": t.body, "status": t.status, "approved_by": t.approved_by_label,
                           "approved_at": S.iso(t.approved_at), "placeholders": _placeholders(t.body)} for t in rows]}


def _placeholders(body: str) -> list[str]:
    return sorted({f for _, f, _, _ in string.Formatter().parse(body) if f})


class TemplateIn(BaseModel):
    key: str = Field(max_length=40)
    language: Literal["en", "hi", "te"]
    body: str = Field(min_length=5, max_length=900)


@router.post("/clinic/templates", status_code=201)
def draft_template(body: TemplateIn, staff: Staff = Depends(require_roles(Role.ADMIN, Role.DOCTOR)),
                   db: Session = Depends(get_db)) -> dict:
    if body.key not in TEMPLATES:
        raise HTTPException(422, "Unknown template.")
    try:
        used = set(_placeholders(body.body))
    except ValueError:
        raise HTTPException(422, "Unbalanced { } in the text.") from None
    allowed = set(_placeholders(TEMPLATES[body.key]["en"])) | {"first_name", "clinic", "clinic_phone"}
    if used - allowed:
        raise HTTPException(422, f"Unknown placeholder(s): {', '.join(sorted(used - allowed))}.")
    latest = db.scalar(select(func.max(MessageTemplate.version)).where(
        MessageTemplate.clinic_id == staff.clinic_id, MessageTemplate.key == body.key,
        MessageTemplate.language == body.language)) or 0
    t = MessageTemplate(clinic_id=staff.clinic_id, key=body.key, language=body.language, version=latest + 1,
                        body=body.body.strip(), status="DRAFT")
    db.add(t)
    db.flush()
    audit(db, clinic_id=staff.clinic_id, action="TEMPLATE_DRAFTED", actor=staff, object_type="message_template",
          object_id=t.id, detail={"key": t.key, "language": t.language, "version": t.version})
    db.commit()
    return {"id": str(t.id), "version": t.version, "status": t.status}


@router.post("/clinic/templates/{template_id}/approve")
def approve_template(template_id: str, staff: Staff = Depends(require_roles(Role.ADMIN, Role.DOCTOR)),
                     db: Session = Depends(get_db)) -> dict:
    t = guards.scoped(db, staff, MessageTemplate, template_id, "message_template")
    if t.status != "DRAFT":
        raise HTTPException(409, "Only drafts can be approved.")
    for old in db.scalars(select(MessageTemplate).where(
            MessageTemplate.clinic_id == t.clinic_id, MessageTemplate.key == t.key,
            MessageTemplate.language == t.language, MessageTemplate.status == "APPROVED")).all():
        old.status = "RETIRED"
    t.status, t.approved_by_label, t.approved_at = "APPROVED", staff.label, utcnow()
    audit(db, clinic_id=t.clinic_id, action="TEMPLATE_APPROVED", actor=staff, object_type="message_template",
          object_id=t.id, detail={"key": t.key, "language": t.language, "version": t.version})
    db.commit()
    return {"id": str(t.id), "status": t.status}


# ------------------------------------------------------------------ audit, metrics, providers, ops
@router.get("/audit-events")
def audit_events(action: str | None = None, limit: int = Query(200, ge=1, le=1000),
                 staff: Staff = Depends(require_roles(Role.ADMIN, Role.OPERATOR)),
                 db: Session = Depends(get_db)) -> dict:
    stmt = select(AuditEvent).where(AuditEvent.clinic_id == staff.clinic_id)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    rows = db.scalars(stmt.order_by(AuditEvent.created_at.desc()).limit(limit)).all()
    mask = staff.role == Role.OPERATOR  # operators see operational metadata, never patient identifiers
    names = views._names(db, {uuid.UUID(e.actor_id) for e in rows if e.actor_type == "USER" and _is_uuid(e.actor_id)})
    return {"masked": mask, "events": [{
        "id": str(e.id), "at": S.iso(e.created_at), "action": e.action, "outcome": e.outcome,
        "actor_type": e.actor_type, "actor_role": e.actor_role,
        "actor": names.get(uuid.UUID(e.actor_id)) if e.actor_type == "USER" and _is_uuid(e.actor_id) else e.actor_type.title(),
        "object_type": e.object_type, "object_id": "•••" if mask and e.object_id else e.object_id,
        "patient_id": None if mask or not e.patient_id else str(e.patient_id),
        "correlation_id": e.correlation_id, "detail": {} if mask else e.detail} for e in rows]}


def _is_uuid(v: str) -> bool:
    return guards._uuid(v) is not None


@router.get("/metrics")
def get_metrics(staff: Staff = Depends(require_roles(Role.ADMIN, Role.DOCTOR, Role.NURSE, Role.OPERATOR)),
                db: Session = Depends(get_db)) -> dict:
    return metrics.compute(db, clinic_of(db, staff))


@router.get("/providers")
def providers(_: Staff = Depends(current_staff)) -> dict:
    return {**provider_status(),
            "whatsapp": {"enabled": settings.whatsapp_enabled,
                         "configured": bool(settings.whatsapp_access_token and settings.whatsapp_phone_number_id),
                         "reminder_template": settings.whatsapp_reminder_template or None},
            "demo_mode": settings.demo_mode, "tasks_mode": "inline" if settings.tasks_eager else "celery"}


@router.get("/ops/health")
def ops_health(staff: Staff = Depends(require_roles(Role.ADMIN, Role.OPERATOR)), db: Session = Depends(get_db)) -> dict:
    """Operational view with no patient content (PRD role: platform operator)."""
    now = utcnow()
    cid = staff.clinic_id
    msg_counts = dict(db.execute(select(OutboundMessage.status, func.count()).where(
        OutboundMessage.clinic_id == cid).group_by(OutboundMessage.status)).all())
    stuck_q = db.scalar(select(func.count()).select_from(OutboundMessage).where(
        OutboundMessage.clinic_id == cid, OutboundMessage.status == MessageStatus.QUEUED,
        OutboundMessage.queued_at < now - timedelta(minutes=2))) or 0
    reply_counts = dict(db.execute(select(PatientReply.status, func.count()).where(
        PatientReply.clinic_id == cid).group_by(PatientReply.status)).all())
    events = dict(db.execute(select(ProviderEvent.processing_status, func.count()).where(
        or_(ProviderEvent.clinic_id == cid, ProviderEvent.clinic_id.is_(None)))
        .group_by(ProviderEvent.processing_status)).all())
    dupes = db.scalar(select(func.coalesce(func.sum(ProviderEvent.duplicate_count), 0)).where(
        ProviderEvent.clinic_id == cid)) or 0
    proposals = dict(db.execute(select(ExtractionProposal.status, func.count()).where(
        ExtractionProposal.clinic_id == cid).group_by(ExtractionProposal.status)).all())
    overdue_tasks = db.scalar(select(func.count()).select_from(CareTask).where(
        CareTask.clinic_id == cid, CareTask.status.in_([s.value for s in OPEN_TASK_STATES]),
        CareTask.due_at < now)) or 0
    return {"messages": msg_counts, "stuck_queued": stuck_q, "replies": reply_counts,
            "provider_events": events, "duplicate_events_ignored": int(dupes), "extractions": proposals,
            "tasks_past_due": overdue_tasks, "providers": provider_status(), "checked_at": now.isoformat(),
            "clinical_task_categories": sorted(c.value for c in CLINICAL_TASK_CATEGORIES)}
