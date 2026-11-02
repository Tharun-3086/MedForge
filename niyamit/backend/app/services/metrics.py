"""Operational metrics (PRD 17.1), computed from recorded events only. Each metric carries its definition,
numerator and denominator. With synthetic data these demonstrate the measurement, not real-world results."""
from __future__ import annotations

import statistics
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import MessageStatus, OPEN_TASK_STATES
from app.models import (
    CareTask,
    Clinic,
    ExtractedField,
    FollowUpItem,
    OutboundMessage,
    Patient,
    PatientReply,
)
from app.services.common import clinic_today


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def compute(db: Session, clinic: Clinic) -> dict[str, Any]:
    today = clinic_today(clinic)
    items = db.scalars(select(FollowUpItem).where(FollowUpItem.clinic_id == clinic.id,
                                                  FollowUpItem.status != "CANCELLED")).all()
    # 1. follow-up completion within 14 days of the due date (only items whose 14-day window has closed)
    eligible = [i for i in items if i.due_date <= today - timedelta(days=14)]
    done14 = [i for i in eligible if i.completed_at and i.completed_at.date() <= i.due_date + timedelta(days=14)]
    # 2. overdue contact within 48h: patient reply or a closed contact task within 48h after the due date
    overdue = [i for i in items if i.due_date <= today - timedelta(days=2) and (
        i.completed_at is None or i.completed_at.date() > i.due_date)]
    contacted = 0
    for i in overdue:
        start = i.due_date
        end = i.due_date + timedelta(days=2)
        reply = db.scalar(select(func.count()).select_from(PatientReply).where(
            PatientReply.patient_id == i.patient_id, func.date(PatientReply.created_at) >= start,
            func.date(PatientReply.created_at) <= end))
        call = db.scalar(select(func.count()).select_from(CareTask).where(
            CareTask.patient_id == i.patient_id, CareTask.outcome.in_(["REACHED_PATIENT", "FOLLOW_UP_COMPLETED", "BOOKED"]),
            func.date(CareTask.resolved_at) >= start, func.date(CareTask.resolved_at) <= end))
        contacted += int(bool(reply or call))
    # 3. missed-visit reason coverage
    missed = [i for i in items if i.due_date < today and i.status in ("PENDING", "CONFIRMED_BY_PATIENT")]
    with_reason = 0
    for i in missed:
        n = db.scalar(select(func.count()).select_from(CareTask).where(
            CareTask.patient_id == i.patient_id, CareTask.barrier_category.is_not(None)))
        with_reason += int(bool(n))
    # 4. tasks
    tasks = db.scalars(select(CareTask).where(CareTask.clinic_id == clinic.id)).all()
    closed = [t for t in tasks if t.resolved_at]
    hours = sorted((t.resolved_at - t.created_at).total_seconds() / 3600 for t in closed)
    open_tasks = [t for t in tasks if t.status in OPEN_TASK_STATES]
    # 5. messages
    counts = dict(db.execute(select(OutboundMessage.status, func.count()).where(OutboundMessage.clinic_id == clinic.id)
                             .group_by(OutboundMessage.status)).all())
    sent = sum(counts.get(s, 0) for s in (MessageStatus.SENT_TO_PROVIDER, MessageStatus.DELIVERED, MessageStatus.FAILED))
    # 6. AI corrections
    reviewed = db.scalars(select(ExtractedField).where(ExtractedField.clinic_id == clinic.id,
                                                       ExtractedField.reviewed_at.is_not(None))).all()
    corrected = [f for f in reviewed if f.status == "REJECTED" or (f.status == "APPROVED" and f.value != f.proposed_value)]
    voice = db.scalar(select(func.count()).select_from(PatientReply).where(
        PatientReply.clinic_id == clinic.id, PatientReply.input_mode == "VOICE")) or 0
    voice_corrected = db.scalar(select(func.count()).select_from(PatientReply).where(
        PatientReply.clinic_id == clinic.id, PatientReply.input_mode == "VOICE",
        PatientReply.corrected_text.is_not(None))) or 0
    completed_followups = len([i for i in items if i.completed_at])
    synthetic = db.scalar(select(func.count()).select_from(Patient).where(
        Patient.clinic_id == clinic.id, Patient.is_synthetic.is_(False))) == 0
    cost = round(sent * clinic.message_unit_cost_inr, 2)
    return {
        "data_label": "Synthetic demo data — demonstrates measurement, not real-world results" if synthetic else "Live data",
        "today": today.isoformat(),
        "metrics": [
            _m("Follow-up completion within 14 days", len(done14), len(eligible),
               "Due follow-ups with a staff-verified completion within 14 days of the due date ÷ follow-ups whose 14-day window has closed."),
            _m("Overdue contact within 48 hours", contacted, len(overdue),
               "Overdue follow-ups with a patient reply or a closed contact task within 48 h of the due date ÷ overdue follow-ups. A sent message does not count."),
            _m("Missed-visit reason coverage", with_reason, len(missed),
               "Missed follow-ups whose patient has a recorded barrier reason ÷ missed follow-ups. Reasons are never inferred."),
            _m("Task resolution rate", len(closed), len(tasks), "Closed tasks ÷ created tasks."),
            _m("AI field correction rate", len(corrected), len(reviewed),
               "Reviewed extracted fields that staff corrected or rejected ÷ reviewed fields."),
            _m("Voice transcript correction rate", voice_corrected, voice,
               "Voice replies corrected by the patient ÷ voice replies."),
        ],
        "tasks": {"open": len(open_tasks), "escalated": len([t for t in open_tasks if t.escalated_at]),
                  "median_hours_to_close": round(statistics.median(hours), 1) if hours else None,
                  "p90_hours_to_close": round(hours[int(0.9 * (len(hours) - 1))], 1) if hours else None,
                  "oldest_open_hours": round(max(((t.updated_at - t.created_at).total_seconds() / 3600
                                                  for t in open_tasks), default=0), 1)},
        "messages": {k: counts.get(k, 0) for k in MessageStatus},
        "cost": {"messages_sent": sent, "unit_cost_inr": clinic.message_unit_cost_inr,
                 "estimated_messaging_cost_inr": cost, "completed_follow_ups": completed_followups,
                 "cost_per_completed_follow_up_inr": round(cost / completed_followups, 2) if completed_followups else None,
                 "note": "Estimate from the configured per-message rate; excludes AI, SMS, voice and hosting costs."},
    }


def _m(name: str, num: int, den: int, definition: str) -> dict[str, Any]:
    return {"name": name, "numerator": num, "denominator": den, "value": _ratio(num, den), "definition": definition}
