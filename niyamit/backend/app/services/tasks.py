"""Care Rescue Loop (PRD 7.6): every actionable barrier, callback, question or failure becomes an owned task
with a queue, due time, status history and outcome. Duplicate signals never create duplicate tasks."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import audit, timeline
from app.db import utcnow
from app.enums import (
    CLINICAL_TASK_CATEGORIES,
    OPEN_TASK_STATES,
    ActorType,
    BarrierCategory,
    ItemStatus,
    PlanStatus,
    Provenance,
    Role,
    TaskCategory,
    TaskQueue,
    TaskStatus,
    check_transition,
)
from app.models import CareTask, Clinic, FollowUpItem, FollowUpPlan, Patient, TaskEvent, User
from app.security import Staff

# Deterministic barrier routing (PRD 7.6). No promise of transport or financial help is ever generated.
BARRIER_ROUTING: dict[str, tuple[str, str]] = {
    BarrierCategory.TIMING: (TaskQueue.RECEPTION, "Patient cannot make the current time"),
    BarrierCategory.TRANSPORT: (TaskQueue.RECEPTION, "Patient reports a transport difficulty"),
    BarrierCategory.COST: (TaskQueue.RECEPTION, "Patient reports a cost difficulty — navigation call"),
    BarrierCategory.CONFUSION: (TaskQueue.NURSE, "Patient is unsure about the next step — explain"),
    BarrierCategory.FEELING_WELL: (TaskQueue.NURSE, "Patient feels well and sees no need to come"),
    BarrierCategory.CAREGIVER_LOGISTICS: (TaskQueue.RECEPTION, "Patient has no one to accompany them"),
    BarrierCategory.OTHER: (TaskQueue.RECEPTION, "Patient reports a difficulty attending"),
    BarrierCategory.PREFER_NOT_TO_SAY: (TaskQueue.RECEPTION, "Patient cannot attend (reason not shared)"),
}


def create_task(
    db: Session,
    *,
    clinic: Clinic,
    patient: Patient,
    category: TaskCategory,
    queue: str,
    title: str,
    dedupe_key: str,
    statement: str | None = None,
    barrier: str | None = None,
    priority: str = "NORMAL",
    source_type: str = "SYSTEM",
    source_id: object = "",
    due_hours: int | None = None,
) -> tuple[CareTask, bool]:
    """Returns (task, created). If an open task with the same dedupe key exists, it is returned instead."""
    existing = db.scalar(select(CareTask).where(
        CareTask.clinic_id == clinic.id, CareTask.dedupe_key == dedupe_key,
        CareTask.status.in_([s.value for s in OPEN_TASK_STATES])))
    if existing:
        return existing, False
    hours = due_hours if due_hours is not None else (2 if priority == "URGENT" else clinic.task_due_hours)
    task = CareTask(
        clinic_id=clinic.id, patient_id=patient.id, category=category, queue=queue, title=title[:200],
        patient_statement=(statement or "").strip() or None, barrier_category=barrier, priority=priority, status=TaskStatus.OPEN,
        source_type=source_type, source_id=str(source_id or ""), dedupe_key=dedupe_key,
        due_at=utcnow() + timedelta(hours=hours),
    )
    try:
        with db.begin_nested():
            db.add(task)
            db.flush()
    except IntegrityError:  # a concurrent worker created it first
        existing = db.scalar(select(CareTask).where(CareTask.clinic_id == clinic.id, CareTask.dedupe_key == dedupe_key,
                                                    CareTask.status.in_([s.value for s in OPEN_TASK_STATES])))
        assert existing is not None
        return existing, False
    db.add(TaskEvent(clinic_id=clinic.id, task_id=task.id, actor_type=ActorType.SYSTEM, actor_label="System",
                     from_status=None, to_status=TaskStatus.OPEN, note=f"Created in {queue} queue"))
    visibility = "CLINICAL" if category in CLINICAL_TASK_CATEGORIES else "STAFF"
    timeline(db, clinic_id=clinic.id, patient_id=patient.id, event_type="TASK_CREATED",
             summary=f"Task opened for {queue.lower()} team: {title}", provenance=Provenance.SYSTEM_EVENT,
             source_type="care_task", source_id=task.id, visibility=visibility)
    return task, True


def can_see(staff: Staff, task: CareTask) -> bool:
    return task.category not in CLINICAL_TASK_CATEGORIES or staff.is_clinical or staff.role == Role.ADMIN


def _event(db: Session, task: CareTask, staff: Staff | None, new: str, note: str = "") -> None:
    db.add(TaskEvent(clinic_id=task.clinic_id, task_id=task.id,
                     actor_type=ActorType.USER if staff else ActorType.SYSTEM,
                     actor_user_id=staff.user_id if staff else None,
                     actor_label=staff.label if staff else "System",
                     from_status=task.status, to_status=new, note=note))


def transition(db: Session, staff: Staff, task: CareTask, new: TaskStatus, *, note: str = "",
               outcome: str = "", assignee: uuid.UUID | None = None) -> CareTask:
    if not can_see(staff, task):
        raise HTTPException(403, "Only clinical staff can act on clinical questions.")
    if task.category in CLINICAL_TASK_CATEGORIES and new == TaskStatus.RESOLVED and not staff.is_clinical:
        raise HTTPException(403, "A clinician must close clinical questions.")
    if new == TaskStatus.OPEN and task.status in OPEN_TASK_STATES:
        raise HTTPException(409, "Task is already open.")
    try:
        check_transition(TaskStatus, task.status, new)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    if new in (TaskStatus.RESOLVED, TaskStatus.UNABLE_TO_RESOLVE) and not (outcome or note):
        raise HTTPException(422, "Record an outcome before closing the task.")
    if new == TaskStatus.OPEN and not note:
        raise HTTPException(422, "Give a reason for reopening.")
    if assignee is not None:
        user = db.get(User, assignee)
        if user is None or not any(m.clinic_id == task.clinic_id for m in user.memberships):
            raise HTTPException(404, "Staff member not found.")
        task.assignee_user_id = assignee
    _event(db, task, staff, new, note or outcome)
    task.status = new
    if new in (TaskStatus.RESOLVED, TaskStatus.UNABLE_TO_RESOLVE):
        task.outcome, task.outcome_note = outcome[:60], note
        task.resolved_at, task.resolved_by_user_id = utcnow(), staff.user_id
    if new == TaskStatus.OPEN:  # reopen keeps the full history in task_events
        task.resolved_at = None
    audit(db, clinic_id=task.clinic_id, action=f"TASK_{new}", actor=staff, object_type="care_task",
          object_id=task.id, patient_id=task.patient_id, detail={"outcome": outcome[:60]})
    if new in (TaskStatus.RESOLVED, TaskStatus.UNABLE_TO_RESOLVE):
        visibility = "CLINICAL" if task.category in CLINICAL_TASK_CATEGORIES else "STAFF"
        timeline(db, clinic_id=task.clinic_id, patient_id=task.patient_id, event_type="TASK_CLOSED",
                 summary=f"{task.title} — {new.replace('_', ' ').lower()}: {outcome or note}"[:300],
                 provenance=Provenance.STAFF_CONFIRMED, actor_type=ActorType.USER, actor_label=staff.label,
                 source_type="care_task", source_id=task.id, visibility=visibility)
    return task


def escalate_unassigned(db: Session, now: datetime | None = None) -> int:
    """Unassigned tasks past their due time are flagged (never silently dropped)."""
    now = now or utcnow()
    tasks = db.scalars(select(CareTask).where(
        CareTask.status == TaskStatus.OPEN, CareTask.assignee_user_id.is_(None),
        CareTask.due_at < now, CareTask.escalated_at.is_(None))).all()
    for t in tasks:
        t.escalated_at = now
        db.add(TaskEvent(clinic_id=t.clinic_id, task_id=t.id, actor_type=ActorType.SYSTEM, actor_label="System",
                         from_status=t.status, to_status=t.status, note="Escalated: unassigned and past due"))
    return len(tasks)


def create_overdue_tasks(db: Session, now: datetime | None = None) -> int:
    """Items overdue beyond the clinic threshold get one owned follow-up task each."""
    from app.services.common import clinic_today

    created = 0
    for clinic in db.scalars(select(Clinic)).all():
        today = clinic_today(clinic)
        cutoff = today - timedelta(days=clinic.overdue_task_after_days)
        rows = db.execute(
            select(FollowUpItem, Patient)
            .join(FollowUpPlan, FollowUpItem.plan_id == FollowUpPlan.id)
            .join(Patient, Patient.id == FollowUpItem.patient_id)
            .where(FollowUpItem.clinic_id == clinic.id, FollowUpPlan.status == PlanStatus.ACTIVE,
                   FollowUpItem.status.in_([ItemStatus.PENDING, ItemStatus.CONFIRMED_BY_PATIENT]),
                   FollowUpItem.due_date <= cutoff)
        ).all()
        for item, patient in rows:
            days = (today - item.due_date).days
            _, was_new = create_task(
                db, clinic=clinic, patient=patient, category=TaskCategory.OVERDUE_FOLLOWUP,
                queue=TaskQueue.RECEPTION, title=f"{item.label} overdue by {days} days — contact patient",
                dedupe_key=f"overdue:{item.id}", source_type="follow_up_item", source_id=item.id)
            created += int(was_new)
    return created
