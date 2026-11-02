"""Doctor Connect (PRD 7.5): offer only slots the availability source returns; confirm only after a
successful commit with a booking reference. Every failure is honest and creates an owned task."""
from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import audit, timeline
from app.db import utcnow
from app.enums import (
    ActorType,
    AppointmentStatus,
    ItemStatus,
    MessageKind,
    Provenance,
    RequestStatus,
    SlotStatus,
    TaskCategory,
    TaskQueue,
    TimeWindow,
)
from app.models import Appointment, AppointmentRequest, AvailabilitySlot, Clinic, FollowUpItem, Patient
from app.services import messaging
from app.services.common import active_faults, clinic_today, clinic_tz, local_dt, same_visit_items, slot_label
from app.services.tasks import create_task

WINDOW_HOURS = {TimeWindow.MORNING: (0, 12), TimeWindow.AFTERNOON: (12, 16), TimeWindow.EVENING: (16, 24)}


class BookingUnavailable(Exception):
    pass


@dataclass
class BookingResult:
    booked: bool
    appointment: Appointment | None
    reason: str  # BOOKED | SLOT_UNAVAILABLE | PROVIDER_UNAVAILABLE | ALREADY_BOOKED
    task_id: uuid.UUID | None = None


PATIENT_LEAD = timedelta(minutes=90)  # times offered to patients start at least this far ahead


def list_slots(db: Session, clinic: Clinic, *, day: date | None = None, window: str | None = None,
               days_ahead: int = 14, limit: int = 40, lead: timedelta = timedelta(0)) -> list[AvailabilitySlot]:
    if "BOOKING_PROVIDER_DOWN" in active_faults(db):
        raise BookingUnavailable()
    now = utcnow() + lead
    start = local_dt(clinic, day, 0) if day else now
    end = local_dt(clinic, day + timedelta(days=1), 0) if day else now + timedelta(days=days_ahead)
    slots = db.scalars(select(AvailabilitySlot).where(
        AvailabilitySlot.clinic_id == clinic.id, AvailabilitySlot.status == SlotStatus.OPEN,
        AvailabilitySlot.starts_at >= max(start, now), AvailabilitySlot.starts_at < end)
        .order_by(AvailabilitySlot.starts_at).limit(200)).all()
    if window in WINDOW_HOURS:
        lo, hi = WINDOW_HOURS[window]
        slots = [s for s in slots if lo <= s.starts_at.astimezone(clinic_tz(clinic)).hour < hi]
    return list(slots[:limit])


def create_request(db: Session, clinic: Clinic, patient: Patient, *, item: FollowUpItem | None,
                   reply_id: uuid.UUID | None, requested_by: str, day_text: str | None, requested: date | None,
                   window: str | None, statement: str | None) -> AppointmentRequest:
    if reply_id:
        existing = db.scalar(select(AppointmentRequest).where(AppointmentRequest.reply_id == reply_id))
        if existing:
            return existing
    # A newer request replaces older ones that are still waiting on the patient (staff-owned ones stay).
    for old in db.scalars(select(AppointmentRequest).where(
            AppointmentRequest.patient_id == patient.id,
            AppointmentRequest.status.in_([RequestStatus.REQUESTED, RequestStatus.NEEDS_CLARIFICATION,
                                           RequestStatus.SLOTS_OFFERED]))).all():
        old.status, old.failure_reason = RequestStatus.CANCELLED, "SUPERSEDED"
    req = AppointmentRequest(clinic_id=clinic.id, patient_id=patient.id, item_id=item.id if item else None,
                             reply_id=reply_id, requested_by=requested_by, requested_date=requested,
                             requested_day_text=day_text, requested_time_window=window,
                             patient_statement=(statement or "").strip() or None, status=RequestStatus.REQUESTED)
    db.add(req)
    db.flush()
    actor = {"CAREGIVER": ActorType.CAREGIVER, "STAFF": ActorType.USER}.get(requested_by, ActorType.PATIENT)
    timeline(db, clinic_id=clinic.id, patient_id=patient.id, event_type="RESCHEDULE_REQUESTED",
             summary="Request for a new appointment time received (not yet booked)",
             provenance=Provenance.STAFF_CONFIRMED if requested_by == "STAFF" else Provenance.PATIENT_REPORTED,
             actor_type=actor, actor_label=requested_by.title(),
             patient_words=statement if requested_by != "STAFF" else None, source_type="appointment_request",
             source_id=req.id)
    return req


def _spread(slots: list[AvailabilitySlot], clinic: Clinic, per_day: int, total: int) -> list[AvailabilitySlot]:
    """A few times on each of the next days, so a patient without a day in mind sees real choices."""
    taken: dict[date, int] = {}
    out: list[AvailabilitySlot] = []
    for s in slots:
        d = s.starts_at.astimezone(clinic_tz(clinic)).date()
        if taken.get(d, 0) < per_day:
            taken[d] = taken.get(d, 0) + 1
            out.append(s)
        if len(out) >= total:
            break
    return out


def offer_slots(db: Session, clinic: Clinic, req: AppointmentRequest, *, day: date | None = None,
                days: list[date] | None = None) -> list[AvailabilitySlot]:
    """Offer slots on the requested day (or on each of the days the patient is choosing between); if there are
    none, a few times on each of the next open days. Provider down -> staff task."""
    window = req.requested_time_window
    try:
        slots: list[AvailabilitySlot] = []
        for d in (days or ([day] if day else [])):
            slots += list_slots(db, clinic, day=d, window=window, limit=8 if not days else 4, lead=PATIENT_LEAD)
        if not slots:
            pool = (list_slots(db, clinic, window=window, limit=60, lead=PATIENT_LEAD)
                    or list_slots(db, clinic, limit=60, lead=PATIENT_LEAD))
            slots = _spread(pool, clinic, per_day=3, total=9)
    except BookingUnavailable:
        _hand_to_staff(db, clinic, req, "PROVIDER_UNAVAILABLE")
        return []
    req.offered_slot_ids = [str(s.id) for s in slots]
    req.status = RequestStatus.SLOTS_OFFERED if slots else RequestStatus.HANDED_TO_STAFF
    if not slots:
        _hand_to_staff(db, clinic, req, "NO_SLOTS")
    return slots


def _hand_to_staff(db: Session, clinic: Clinic, req: AppointmentRequest, reason: str) -> uuid.UUID:
    patient = db.get(Patient, req.patient_id)
    title = {"PROVIDER_UNAVAILABLE": "Booking system unavailable — book a time with the patient",
             "NO_SLOTS": "No open slots — arrange a time with the patient",
             "SLOT_UNAVAILABLE": "Chosen slot was taken — arrange a time"}.get(reason, "Arrange a time")
    task, _ = create_task(db, clinic=clinic, patient=patient,
                          category=TaskCategory.BOOKING_FAILED if reason == "PROVIDER_UNAVAILABLE" else TaskCategory.RESCHEDULE,
                          queue=TaskQueue.RECEPTION, title=title, dedupe_key=f"booking:{req.id}",
                          statement=req.patient_statement, source_type="appointment_request", source_id=req.id)
    req.status, req.failure_reason, req.task_id = RequestStatus.HANDED_TO_STAFF, reason, task.id
    return task.id


def commit_booking(db: Session, clinic: Clinic, patient: Patient, *, slot_id: uuid.UUID,
                   request_id: uuid.UUID | None, idempotency_key: str, created_by: str,
                   staff_label: str | None = None) -> BookingResult:
    """Transactional booking. Same idempotency key -> same result; a slot can never be double-booked."""
    existing = db.scalar(select(Appointment).where(Appointment.idempotency_key == idempotency_key))
    if existing:
        return BookingResult(True, existing, "ALREADY_BOOKED")
    req = db.get(AppointmentRequest, request_id) if request_id else None
    if req and (req.patient_id != patient.id or req.clinic_id != clinic.id):
        req = None
    if "BOOKING_PROVIDER_DOWN" in active_faults(db):
        task_id = _hand_to_staff(db, clinic, req, "PROVIDER_UNAVAILABLE") if req else _orphan_task(db, clinic, patient)
        _notify_not_booked(db, clinic, patient, idempotency_key)
        return BookingResult(False, None, "PROVIDER_UNAVAILABLE", task_id)
    slot = db.scalar(select(AvailabilitySlot).where(AvailabilitySlot.id == slot_id).with_for_update()
                   .execution_options(populate_existing=True))
    if slot is None or slot.clinic_id != clinic.id or slot.status != SlotStatus.OPEN or slot.starts_at <= utcnow():
        if req:
            req.failure_reason = "SLOT_UNAVAILABLE"
        return BookingResult(False, None, "SLOT_UNAVAILABLE")
    item = db.get(FollowUpItem, req.item_id) if req and req.item_id else None
    appt = Appointment(clinic_id=clinic.id, patient_id=patient.id, slot_id=slot.id, item_id=item.id if item else None,
                       request_id=req.id if req else None, status=AppointmentStatus.CONFIRMED,
                       booking_reference="NYM-" + secrets.token_hex(3).upper(), idempotency_key=idempotency_key,
                       created_by=created_by)
    try:
        with db.begin_nested():
            slot.status = SlotStatus.BOOKED
            db.add(appt)
            db.flush()
    except IntegrityError:
        return BookingResult(False, None, "SLOT_UNAVAILABLE")
    if req:
        req.status, req.appointment_id = RequestStatus.BOOKED, appt.id
        _close_request_tasks(db, req, appt)
    if item:
        for it in same_visit_items(db, item):
            if it.status in (ItemStatus.PENDING, ItemStatus.CONFIRMED_BY_PATIENT):
                it.status = ItemStatus.BOOKED
    when = slot_label(slot.starts_at.astimezone(clinic_tz(clinic)))
    timeline(db, clinic_id=clinic.id, patient_id=patient.id, event_type="APPOINTMENT_BOOKED",
             summary=f"Appointment booked for {when} with {slot.provider_label} — ref {appt.booking_reference}",
             provenance=Provenance.SYSTEM_EVENT if not staff_label else Provenance.STAFF_CONFIRMED,
             actor_type=ActorType.USER if staff_label else ActorType.SYSTEM, actor_label=staff_label or "Booking service",
             source_type="appointment", source_id=appt.id)
    audit(db, clinic_id=clinic.id, action="BOOKING_COMMITTED", actor_type=ActorType.SYSTEM,
          object_type="appointment", object_id=appt.id, patient_id=patient.id,
          detail={"ref": appt.booking_reference, "by": created_by})
    messaging.queue_message(db, clinic=clinic, patient=patient, kind=MessageKind.BOOKING_UPDATE,
                            template_key="BOOKING_CONFIRMED", idempotency_key=f"booked:{appt.id}",
                            values={"slot_time": slot.starts_at.astimezone(clinic_tz(clinic)), "ref": appt.booking_reference})
    return BookingResult(True, appt, "BOOKED")


def cancel_appointment(db: Session, clinic: Clinic, appt: Appointment, *, reason: str, actor_label: str,
                       actor_type: ActorType = ActorType.USER) -> Appointment:
    """Cancelling frees the slot and puts the linked follow-up back to pending (it still needs a visit)."""
    if appt.status != AppointmentStatus.CONFIRMED:
        return appt
    appt.status = AppointmentStatus.CANCELLED
    slot = db.get(AvailabilitySlot, appt.slot_id)
    if slot and slot.status == SlotStatus.BOOKED and slot.starts_at > utcnow():
        slot.status = SlotStatus.OPEN  # the freed time can be offered again
    item = db.get(FollowUpItem, appt.item_id) if appt.item_id else None
    if item:
        for it in same_visit_items(db, item):
            if it.status == ItemStatus.BOOKED:
                it.status = ItemStatus.PENDING
    timeline(db, clinic_id=clinic.id, patient_id=appt.patient_id, event_type="APPOINTMENT_CANCELLED",
             summary=f"Appointment {appt.booking_reference} cancelled: {reason[:200]}",
             provenance=Provenance.STAFF_CONFIRMED if actor_type == ActorType.USER else Provenance.PATIENT_REPORTED,
             actor_type=actor_type, actor_label=actor_label, source_type="appointment", source_id=appt.id)
    audit(db, clinic_id=clinic.id, action="APPOINTMENT_CANCELLED", actor_type=actor_type, object_type="appointment",
          object_id=appt.id, patient_id=appt.patient_id, detail={"reason": reason[:200], "by": actor_label})
    return appt


def _close_request_tasks(db: Session, req: AppointmentRequest, appt: Appointment) -> None:
    """A staff task opened for this request is closed with outcome BOOKED once a booking commits."""
    from app.enums import OPEN_TASK_STATES, TaskStatus
    from app.models import CareTask, TaskEvent

    for task in db.scalars(select(CareTask).where(CareTask.clinic_id == req.clinic_id,
                                                  CareTask.dedupe_key == f"booking:{req.id}",
                                                  CareTask.status.in_([s.value for s in OPEN_TASK_STATES]))).all():
        db.add(TaskEvent(clinic_id=task.clinic_id, task_id=task.id, actor_type=ActorType.SYSTEM, actor_label="System",
                         from_status=task.status, to_status=TaskStatus.RESOLVED,
                         note=f"Closed automatically: booked, ref {appt.booking_reference}"))
        task.status, task.outcome, task.resolved_at = TaskStatus.RESOLVED, "BOOKED", utcnow()


def _orphan_task(db: Session, clinic: Clinic, patient: Patient) -> uuid.UUID:
    task, _ = create_task(db, clinic=clinic, patient=patient, category=TaskCategory.BOOKING_FAILED,
                          queue=TaskQueue.RECEPTION, title="Booking system unavailable — book a time with the patient",
                          dedupe_key=f"bookingdown:{patient.id}")
    return task.id


def _notify_not_booked(db: Session, clinic: Clinic, patient: Patient, key: str) -> None:
    messaging.queue_message(db, clinic=clinic, patient=patient, kind=MessageKind.BOOKING_UPDATE,
                            template_key="BOOKING_NOT_DONE", idempotency_key=f"notbooked:{key}")


def slot_dict(slot: AvailabilitySlot, clinic: Clinic) -> dict:
    local: datetime = slot.starts_at.astimezone(clinic_tz(clinic))
    return {"id": str(slot.id), "starts_at": slot.starts_at.isoformat(), "provider": slot.provider_label,
            "label": slot_label(local), "date": local.date().isoformat(),
            "source": slot.source}


def today_for(clinic: Clinic) -> date:
    return clinic_today(clinic)
