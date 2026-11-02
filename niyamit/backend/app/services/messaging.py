r"""Outbound messages: transactional outbox, policy checks at every step, bounded retries, truthful states.

SCHEDULED -> QUEUED -> SENDING -> SENT_TO_PROVIDER -> DELIVERED (only when the provider confirms)
                                   \-> FAILED (task for staff)   SUPPRESSED (opt-out/consent)   UNKNOWN
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.audit import timeline
from app.channels.base import ChannelError, get_channel
from app.channels.simulated import SimulatedChannel
from app.db import utcnow
from app.enums import (
    ESSENTIAL_KINDS,
    ItemStatus,
    MessageKind,
    MessageStatus,
    PlanStatus,
    Provenance,
    TaskCategory,
    TaskQueue,
    check_transition,
)
from app.jobs import defer
from app.models import Clinic, FollowUpItem, FollowUpPlan, OutboundMessage, Patient
from app.services.common import active_faults, clinic_tz, first_name, local_dt, next_allowed_send_time
from app.services.links import patient_link, reminders_allowed
from app.services.templates import approved_template, render

log = logging.getLogger("niyamit.messaging")

REMINDER_KINDS = {MessageKind.REMINDER_PRE_DUE, MessageKind.REMINDER_DUE, MessageKind.REMINDER_OVERDUE,
                  MessageKind.REMINDER_MANUAL}
CHANNEL_LABEL = {"SIMULATED": "Simulated channel (demo phone)", "WHATSAPP": "WhatsApp"}


def _set(m: OutboundMessage, new: MessageStatus) -> None:
    check_transition(MessageStatus, m.status, new)
    m.status = new


def queue_message(
    db: Session,
    *,
    clinic: Clinic,
    patient: Patient,
    kind: MessageKind,
    template_key: str,
    idempotency_key: str,
    values: dict[str, object] | None = None,
    scheduled_for: datetime | None = None,
    plan_id: uuid.UUID | None = None,
    item_id: uuid.UUID | None = None,
    reply_id: uuid.UUID | None = None,
    caregiver_grant_id: uuid.UUID | None = None,
    to_phone_channel: str | None = None,
) -> OutboundMessage:
    """Create a message in the outbox (idempotent). Only approved templates can be rendered."""
    existing = db.scalar(select(OutboundMessage).where(OutboundMessage.idempotency_key == idempotency_key))
    if existing:
        return existing
    vals: dict[str, object] = {"first_name": first_name(patient), "clinic": clinic.short_name,
                               "clinic_phone": clinic.phone, **(values or {})}
    tpl = approved_template(db, clinic.id, template_key, patient.preferred_language)
    if "{link}" in tpl.body and "link" not in vals:
        vals["link"] = patient_link(db, patient)
    body, tpl = render(db, clinic.id, template_key, patient.preferred_language, **vals)
    essential = kind in ESSENTIAL_KINDS
    msg = OutboundMessage(
        clinic_id=clinic.id, patient_id=patient.id, caregiver_grant_id=caregiver_grant_id, kind=kind,
        template_key=template_key, template_version=tpl.version, language=tpl.language,
        channel=to_phone_channel or patient.preferred_channel, body=body, essential=essential,
        status=MessageStatus.SCHEDULED, scheduled_for=scheduled_for or utcnow(), idempotency_key=idempotency_key,
        plan_id=plan_id, item_id=item_id, reply_id=reply_id,
    )
    allowed, reason = reminders_allowed(db, patient)
    if not essential and not allowed:
        msg.status, msg.suppressed_reason = MessageStatus.SUPPRESSED, reason
    db.add(msg)
    db.flush()
    if msg.status == MessageStatus.SCHEDULED and msg.scheduled_for <= utcnow() + timedelta(seconds=5):
        _dispatch_one(db, msg, clinic, utcnow())
    return msg


def _dispatch_one(db: Session, m: OutboundMessage, clinic: Clinic, now: datetime) -> None:
    """Policy check at dispatch time; SCHEDULED -> QUEUED (+ send job after commit) or SUPPRESSED."""
    patient = db.get(Patient, m.patient_id)
    assert patient is not None
    allowed, reason = reminders_allowed(db, patient)
    if not m.essential and not allowed:
        _set(m, MessageStatus.SUPPRESSED)
        m.suppressed_reason = reason
        return
    if m.kind in REMINDER_KINDS and m.item_id:
        item = db.get(FollowUpItem, m.item_id)
        plan = db.get(FollowUpPlan, item.plan_id) if item else None
        if item is None or plan is None or plan.status != PlanStatus.ACTIVE or item.status in (
                ItemStatus.COMPLETED, ItemStatus.CANCELLED):
            _set(m, MessageStatus.SUPPRESSED)
            m.suppressed_reason = "FOLLOW_UP_CLOSED"
            return
        if m.kind == MessageKind.REMINDER_PRE_DUE and item.status in (ItemStatus.CONFIRMED_BY_PATIENT, ItemStatus.BOOKED):
            _set(m, MessageStatus.SUPPRESSED)
            m.suppressed_reason = "PATIENT_ALREADY_CONFIRMED"
            return
    if m.kind in REMINDER_KINDS:
        allowed_at = next_allowed_send_time(clinic, now)
        if allowed_at > now:  # quiet hours: stay scheduled, move to the end of quiet hours
            m.scheduled_for = allowed_at
            return
    if m.kind in REMINDER_KINDS and m.idempotency_key.startswith("rem:") and _reminded_today(db, m, clinic, now):
        # At most one scheduled reminder a day per patient (two follow-ups can fall on the same day).
        _set(m, MessageStatus.SUPPRESSED)
        m.suppressed_reason = "ALREADY_REMINDED_TODAY"
        return
    _set(m, MessageStatus.QUEUED)
    m.queued_at = now
    db.flush()
    defer(db, "send_message", m.id)


def _reminded_today(db: Session, m: OutboundMessage, clinic: Clinic, now: datetime) -> bool:
    start = local_dt(clinic, now.astimezone(clinic_tz(clinic)).date(), 0)
    return bool(db.scalar(select(func.count()).select_from(OutboundMessage).where(
        OutboundMessage.patient_id == m.patient_id, OutboundMessage.id != m.id,
        OutboundMessage.kind.in_(REMINDER_KINDS), OutboundMessage.queued_at >= start,
        OutboundMessage.queued_at < start + timedelta(days=1),
        OutboundMessage.status.in_([MessageStatus.QUEUED, MessageStatus.SENDING, MessageStatus.SENT_TO_PROVIDER,
                                    MessageStatus.DELIVERED, MessageStatus.UNKNOWN]))))


def dispatch_due(db: Session, now: datetime | None = None, limit: int = 200) -> int:
    now = now or utcnow()
    rows = db.scalars(
        select(OutboundMessage)
        .where(OutboundMessage.status == MessageStatus.SCHEDULED, OutboundMessage.scheduled_for <= now)
        .order_by(OutboundMessage.scheduled_for).limit(limit).with_for_update(skip_locked=True).execution_options(populate_existing=True)
    ).all()
    clinics: dict[uuid.UUID, Clinic] = {}
    for m in rows:
        clinic = clinics.get(m.clinic_id) or db.get(Clinic, m.clinic_id)
        clinics[m.clinic_id] = clinic
        _dispatch_one(db, m, clinic, now)
    return len(rows)


def send(db: Session, message_id: uuid.UUID) -> None:
    """Send one queued message. Safe to call twice: anything not QUEUED is left alone."""
    m = db.scalar(select(OutboundMessage).where(OutboundMessage.id == message_id).with_for_update()
                  .execution_options(populate_existing=True))
    if m is None or m.status != MessageStatus.QUEUED:
        db.rollback()
        return
    patient = db.get(Patient, m.patient_id)
    allowed, reason = reminders_allowed(db, patient)
    if not m.essential and not allowed:  # opted out after queueing: suppress before dispatch
        _set(m, MessageStatus.SUPPRESSED)
        m.suppressed_reason = reason
        db.commit()
        return
    _set(m, MessageStatus.SENDING)
    m.attempts += 1
    m.sending_started_at = utcnow()
    db.commit()

    faults = active_faults(db)
    try:
        channel = SimulatedChannel(fail=True) if (m.channel == "SIMULATED" and "CHANNEL_SEND_FAIL" in faults) \
            else get_channel(m.channel)
        result = channel.send(m, patient)
    except ChannelError as exc:
        m = db.scalar(select(OutboundMessage).where(OutboundMessage.id == message_id).with_for_update()
                  .execution_options(populate_existing=True))
        m.last_error_code = exc.code
        if exc.retriable and m.attempts < m.max_attempts:
            _set(m, MessageStatus.QUEUED)
            m.queued_at = utcnow()
            defer(db, "send_message", m.id, countdown=10 * 3 ** (m.attempts - 1))
        else:
            _fail(db, m, patient, exc.code)
        db.commit()
        return

    m = db.scalar(select(OutboundMessage).where(OutboundMessage.id == message_id).with_for_update()
                  .execution_options(populate_existing=True))
    _set(m, MessageStatus.SENT_TO_PROVIDER)
    m.provider_message_id = result.provider_message_id
    m.sent_at = utcnow()
    what = "Reminder" if m.kind in REMINDER_KINDS else "Message"
    timeline(db, clinic_id=m.clinic_id, patient_id=m.patient_id, event_type="MESSAGE_SENT",
             summary=f"{what} handed to {CHANNEL_LABEL.get(m.channel, m.channel)} — delivery not yet confirmed",
             provenance=Provenance.SYSTEM_EVENT, source_type="outbound_message", source_id=m.id)
    if m.channel == "SIMULATED":
        defer(db, "simulated_delivery", m.id, countdown=2)
    db.commit()


def _fail(db: Session, m: OutboundMessage, patient: Patient, code: str) -> None:
    from app.services.tasks import create_task

    _set(m, MessageStatus.FAILED)
    m.failed_at = utcnow()
    m.last_error_code = code
    clinic = db.get(Clinic, m.clinic_id)
    create_task(db, clinic=clinic, patient=patient, category=TaskCategory.MESSAGE_FAILURE, queue=TaskQueue.RECEPTION,
                title=f"Message could not be sent ({code}) — contact patient another way",
                dedupe_key=f"msgfail:{patient.id}", source_type="outbound_message", source_id=m.id)
    timeline(db, clinic_id=m.clinic_id, patient_id=m.patient_id, event_type="MESSAGE_FAILED",
             summary=f"Message failed ({code}); a staff task was created", provenance=Provenance.SYSTEM_EVENT,
             source_type="outbound_message", source_id=m.id, visibility="STAFF")


def apply_delivery_status(db: Session, provider_message_id: str, status: str, error_code: str | None = None) -> str:
    """Idempotent: late or repeated callbacks never move a final state backwards."""
    m = db.scalar(select(OutboundMessage).where(OutboundMessage.provider_message_id == provider_message_id)
                  .with_for_update().execution_options(populate_existing=True))
    if m is None:
        return "UNKNOWN_MESSAGE"
    status = (status or "").lower()
    if status in ("delivered", "read") and m.status in (MessageStatus.SENT_TO_PROVIDER, MessageStatus.UNKNOWN):
        _set(m, MessageStatus.DELIVERED)
        m.delivered_at = utcnow()
        return "DELIVERED"
    if status == "failed" and m.status in (MessageStatus.SENT_TO_PROVIDER, MessageStatus.UNKNOWN):
        _fail(db, m, db.get(Patient, m.patient_id), f"PROVIDER_{error_code or 'FAILED'}")
        return "FAILED"
    if status == "sent" and m.status == MessageStatus.UNKNOWN:
        _set(m, MessageStatus.SENT_TO_PROVIDER)
        return "SENT_TO_PROVIDER"
    return "NO_CHANGE"


def recover_stuck(db: Session, now: datetime | None = None) -> int:
    """Re-dispatch queued jobs that never ran; mark long-running sends UNKNOWN (never auto-resend those)."""
    now = now or utcnow()
    count = 0
    for m in db.scalars(select(OutboundMessage).where(
            OutboundMessage.status == MessageStatus.QUEUED,
            OutboundMessage.queued_at < now - timedelta(minutes=2)).with_for_update(skip_locked=True).execution_options(populate_existing=True)).all():
        m.queued_at = now
        defer(db, "send_message", m.id)
        count += 1
    for m in db.scalars(select(OutboundMessage).where(
            OutboundMessage.status == MessageStatus.SENDING,
            OutboundMessage.sending_started_at < now - timedelta(minutes=5)).with_for_update(skip_locked=True).execution_options(populate_existing=True)).all():
        _set(m, MessageStatus.UNKNOWN)
        from app.services.tasks import create_task

        create_task(db, clinic=db.get(Clinic, m.clinic_id), patient=db.get(Patient, m.patient_id),
                    category=TaskCategory.MESSAGE_FAILURE, queue=TaskQueue.RECEPTION,
                    title="Message status unknown — check before resending", dedupe_key=f"msgunknown:{m.id}",
                    source_type="outbound_message", source_id=m.id)
        count += 1
    return count


def suppress_pending(db: Session, patient: Patient, reason: str) -> int:
    """Opt-out propagates to the queue: pending non-essential messages are invalidated immediately."""
    res = db.execute(
        update(OutboundMessage)
        .where(OutboundMessage.patient_id == patient.id, OutboundMessage.essential.is_(False),
               OutboundMessage.status.in_([MessageStatus.SCHEDULED, MessageStatus.QUEUED]))
        .values(status=MessageStatus.SUPPRESSED, suppressed_reason=reason)
    )
    return res.rowcount or 0


def retry_failed(db: Session, m: OutboundMessage) -> None:
    patient = db.get(Patient, m.patient_id)
    allowed, reason = reminders_allowed(db, patient)
    if not m.essential and not allowed:
        raise ValueError(f"Cannot retry: {reason}")
    _set(m, MessageStatus.QUEUED)
    m.attempts = 0
    m.queued_at = utcnow()
    defer(db, "send_message", m.id)
