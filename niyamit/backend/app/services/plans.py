"""Follow-up plans (PRD 10.1). Only an approved, ACTIVE plan can drive reminders. Changing a plan creates a
new version and supersedes the old one; nothing is overwritten silently."""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit, timeline
from app.db import utcnow
from app.enums import (
    ITEM_LABELS,
    ActorType,
    ItemKind,
    ItemStatus,
    MessageKind,
    OPEN_TASK_STATES,
    PlanStatus,
    Provenance,
    Role,
    TaskStatus,
    check_transition,
)
from app.models import CareTask, Clinic, FollowUpItem, FollowUpPlan, Patient, TaskEvent
from app.security import Staff
from app.services import messaging
from app.services.common import clinic_today, day_label, local_dt, same_visit_items


def _set(plan: FollowUpPlan, new: PlanStatus) -> None:
    try:
        check_transition(PlanStatus, plan.status, new)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    plan.status = new


def can_approve(staff: Staff, clinic: Clinic) -> bool:
    return staff.role in clinic.plan_approver_roles


def create_plan(db: Session, staff: Staff, clinic: Clinic, patient: Patient, items: list[dict], *,
                notes: str = "", source: str = "MANUAL", artifact_id: uuid.UUID | None = None,
                proposal_id: uuid.UUID | None = None) -> FollowUpPlan:
    if not items:
        raise HTTPException(422, "Add at least one follow-up item.")
    today = clinic_today(clinic)
    plan = FollowUpPlan(clinic_id=clinic.id, patient_id=patient.id, status=PlanStatus.DRAFT, source=source,
                        source_artifact_id=artifact_id, proposal_id=proposal_id, created_by_user_id=staff.user_id,
                        notes=notes[:2000])
    db.add(plan)
    db.flush()
    for it in items:
        kind = ItemKind(it["kind"])
        due: date = it["due_date"]
        if due < today - timedelta(days=365) or due > today + timedelta(days=730):
            raise HTTPException(422, f"Due date {due} is outside the allowed range.")
        db.add(FollowUpItem(clinic_id=clinic.id, plan_id=plan.id, patient_id=patient.id, kind=kind,
                            label=(it.get("label") or ITEM_LABELS[kind])[:120], due_date=due,
                            source_field_id=it.get("source_field_id")))
    _set(plan, PlanStatus.NEEDS_REVIEW)
    db.flush()
    db.refresh(plan)
    audit(db, clinic_id=clinic.id, action="PLAN_CREATED", actor=staff, object_type="follow_up_plan",
          object_id=plan.id, patient_id=patient.id, detail={"source": source, "items": len(items)})
    return plan


def approve_plan(db: Session, staff: Staff, clinic: Clinic, plan: FollowUpPlan) -> FollowUpPlan:
    """APPROVED -> ACTIVE in one step. Supersedes the previous active plan and schedules reminders."""
    if not can_approve(staff, clinic):
        raise HTTPException(403, "Your role cannot approve follow-up plans in this clinic.")
    _set(plan, PlanStatus.APPROVED)
    plan.approved_by_user_id, plan.approved_at = staff.user_id, utcnow()
    previous = db.scalar(select(FollowUpPlan).where(FollowUpPlan.patient_id == plan.patient_id,
                                                    FollowUpPlan.status == PlanStatus.ACTIVE,
                                                    FollowUpPlan.id != plan.id))
    if previous:
        _set(previous, PlanStatus.SUPERSEDED)
        plan.previous_plan_id, plan.version = previous.id, previous.version + 1
        for item in previous.items:
            if item.status not in (ItemStatus.COMPLETED,):
                item.status = ItemStatus.CANCELLED
    _set(plan, PlanStatus.ACTIVE)
    patient = db.get(Patient, plan.patient_id)
    scheduled = schedule_reminders(db, clinic, patient, plan)
    who = "CLINICIAN_APPROVED" if staff.role == Role.DOCTOR else "STAFF_CONFIRMED"
    items_txt = ", ".join(f"{i.label} by {day_label(i.due_date)} {i.due_date.year}" for i in plan.items)
    timeline(db, clinic_id=clinic.id, patient_id=plan.patient_id, event_type="PLAN_APPROVED",
             summary=f"Follow-up plan v{plan.version} approved: {items_txt}", provenance=Provenance(who),
             actor_type=ActorType.USER, actor_label=staff.label, source_type="follow_up_plan", source_id=plan.id)
    audit(db, clinic_id=clinic.id, action="PLAN_APPROVED", actor=staff, object_type="follow_up_plan",
          object_id=plan.id, patient_id=plan.patient_id,
          detail={"version": plan.version, "reminders_scheduled": scheduled,
                  "superseded": str(previous.id) if previous else None})
    return plan


def schedule_reminders(db: Session, clinic: Clinic, patient: Patient, plan: FollowUpPlan) -> int:
    """Reminders before/on the due date and overdue nudges after it, at the clinic's send hour."""
    now = utcnow()
    count = 0
    planned: set[tuple[date, date]] = set()  # (send day, due date): follow-ups due together share one reminder
    for item in sorted(plan.items, key=lambda i: i.due_date):
        if item.status in (ItemStatus.COMPLETED, ItemStatus.CANCELLED):
            continue
        offsets = [(o, MessageKind.REMINDER_PRE_DUE if o < 0 else MessageKind.REMINDER_DUE,
                    "REMINDER_PRE_DUE" if o < 0 else "REMINDER_DUE") for o in clinic.reminder_offsets_days]
        offsets += [(o, MessageKind.REMINDER_OVERDUE, "REMINDER_OVERDUE") for o in clinic.overdue_nudge_days]
        for offset, kind, key in offsets:
            send_day = item.due_date + timedelta(days=offset)
            when = local_dt(clinic, send_day, clinic.reminder_send_hour)
            if when <= now or (send_day, item.due_date) in planned:
                continue
            planned.add((send_day, item.due_date))
            messaging.queue_message(
                db, clinic=clinic, patient=patient, kind=kind, template_key=key,
                idempotency_key=f"rem:{item.id}:{offset}",
                values={"due_date": item.due_date}, scheduled_for=when,
                plan_id=plan.id, item_id=item.id)
            count += 1
    return count


def complete_item(db: Session, staff: Staff, clinic: Clinic, item: FollowUpItem, note: str = "") -> FollowUpItem:
    """Verified completion recorded by staff (the only way an item becomes COMPLETED)."""
    if item.status == ItemStatus.COMPLETED:
        return item
    if item.status == ItemStatus.CANCELLED:
        raise HTTPException(409, "This item was cancelled.")
    item.status = ItemStatus.COMPLETED
    item.completed_at, item.completed_by_user_id = utcnow(), staff.user_id
    patient = db.get(Patient, item.patient_id)
    patient.last_visit_at = utcnow() if item.kind == ItemKind.REVIEW_VISIT else patient.last_visit_at
    # Close the overdue task for this item, if any (with an outcome, never silently)
    for task in db.scalars(select(CareTask).where(CareTask.dedupe_key == f"overdue:{item.id}",
                                                  CareTask.status.in_([s.value for s in OPEN_TASK_STATES]))).all():
        db.add(TaskEvent(clinic_id=task.clinic_id, task_id=task.id, actor_type=ActorType.USER,
                         actor_user_id=staff.user_id, actor_label=staff.label, from_status=task.status,
                         to_status=TaskStatus.RESOLVED, note="Follow-up completed"))
        task.status, task.outcome, task.resolved_at = TaskStatus.RESOLVED, "FOLLOW_UP_COMPLETED", utcnow()
        task.resolved_by_user_id = staff.user_id
    timeline(db, clinic_id=clinic.id, patient_id=item.patient_id, event_type="FOLLOW_UP_COMPLETED",
             summary=f"{item.label} completed (verified by staff){': ' + note if note else ''}",
             provenance=Provenance.STAFF_CONFIRMED, actor_type=ActorType.USER, actor_label=staff.label,
             source_type="follow_up_item", source_id=item.id)
    audit(db, clinic_id=clinic.id, action="ITEM_COMPLETED", actor=staff, object_type="follow_up_item",
          object_id=item.id, patient_id=item.patient_id)
    plan = db.get(FollowUpPlan, item.plan_id)
    if plan and all(i.status in (ItemStatus.COMPLETED, ItemStatus.CANCELLED) for i in plan.items):
        _set(plan, PlanStatus.COMPLETED)
    return item


def cancel_plan(db: Session, staff: Staff, clinic: Clinic, plan: FollowUpPlan, reason: str) -> FollowUpPlan:
    if not reason.strip():
        raise HTTPException(422, "Give a reason for cancelling the plan.")
    if plan.status in (PlanStatus.ACTIVE, PlanStatus.APPROVED) and not can_approve(staff, clinic):
        raise HTTPException(403, "Only staff who can approve plans can cancel an active plan.")
    _set(plan, PlanStatus.CANCELLED)
    for item in plan.items:
        if item.status != ItemStatus.COMPLETED:
            item.status = ItemStatus.CANCELLED
    patient = db.get(Patient, plan.patient_id)
    # Pending reminders for this plan are suppressed at dispatch time (FOLLOW_UP_CLOSED); do it now too.
    from sqlalchemy import update

    from app.enums import MessageStatus
    from app.models import OutboundMessage

    db.execute(update(OutboundMessage).where(OutboundMessage.plan_id == plan.id,
                                             OutboundMessage.status.in_([MessageStatus.SCHEDULED, MessageStatus.QUEUED]))
               .values(status=MessageStatus.SUPPRESSED, suppressed_reason="PLAN_CANCELLED"))
    timeline(db, clinic_id=clinic.id, patient_id=patient.id, event_type="PLAN_CANCELLED",
             summary=f"Follow-up plan v{plan.version} cancelled: {reason[:200]}", provenance=Provenance.STAFF_CONFIRMED,
             actor_type=ActorType.USER, actor_label=staff.label, source_type="follow_up_plan", source_id=plan.id)
    audit(db, clinic_id=clinic.id, action="PLAN_CANCELLED", actor=staff, object_type="follow_up_plan",
          object_id=plan.id, patient_id=plan.patient_id, detail={"reason": reason[:200]})
    return plan


def manual_reminder(db: Session, staff: Staff, clinic: Clinic, patient: Patient, item: FollowUpItem,
                    client_key: str | None = None):
    """Staff-triggered reminder for one open item. Consent, opt-out and quiet hours still apply.
    A repeated click (same client key, or within the same minute) returns the same message."""
    if item.status in (ItemStatus.COMPLETED, ItemStatus.CANCELLED):
        raise HTTPException(409, "This follow-up is already closed.")
    today = clinic_today(clinic)
    key = "REMINDER_OVERDUE" if item.due_date < today else ("REMINDER_DUE" if item.due_date == today else "REMINDER_PRE_DUE")
    token = client_key or utcnow().strftime("%Y%m%d%H%M")
    msg = messaging.queue_message(db, clinic=clinic, patient=patient, kind=MessageKind.REMINDER_MANUAL,
                                  template_key=key, idempotency_key=f"manual:{item.id}:{token}",
                                  values={"due_date": item.due_date}, plan_id=item.plan_id,
                                  item_id=item.id)
    audit(db, clinic_id=clinic.id, action="REMINDER_SENT_MANUALLY", actor=staff, object_type="outbound_message",
          object_id=msg.id, patient_id=patient.id, detail={"status": msg.status})
    return msg


def record_patient_confirmation(db: Session, patient: Patient, item: FollowUpItem, statement: str | None,
                                via: str = "Patient") -> bool:
    """A response event only: the clinician-approved plan is not changed. Repeats are no-ops.
    Follow-ups due on the same day are one visit, so a confirmation covers all of them."""
    changed = [i for i in same_visit_items(db, item) if i.status == ItemStatus.PENDING]
    if not changed:
        return False
    for i in changed:
        i.status = ItemStatus.CONFIRMED_BY_PATIENT
        i.patient_confirmed_at = utcnow()
    labels = " and ".join(i.label for i in changed)
    timeline(db, clinic_id=patient.clinic_id, patient_id=patient.id, event_type="PATIENT_CONFIRMED",
             summary=f"{via} confirmed attending: {labels} on {day_label(item.due_date)} {item.due_date.year}",
             provenance=Provenance.PATIENT_REPORTED, actor_type=ActorType.PATIENT, actor_label=via,
             patient_words=(statement or "").strip() or None, source_type="follow_up_item", source_id=item.id)
    return True
