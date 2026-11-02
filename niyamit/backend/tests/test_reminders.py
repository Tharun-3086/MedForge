"""Reminder volume rules: follow-ups due together share reminders, and a patient gets at most one a day."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Clinic, FollowUpItem, OutboundMessage
from app.services import messaging
from app.services.common import local_dt
from tests.conftest import clinic_today, new_patient, patient_session


def _plan(client, pid: str, *due_offsets: int) -> None:
    today = clinic_today(client)
    items = [{"kind": kind, "due_date": (today + timedelta(days=d)).isoformat()}
             for kind, d in zip(["REVIEW_VISIT", "KIDNEY_TEST", "FOOT_EXAM"], due_offsets)]
    r = client.post("/v1/follow-up-plans", json={"patient_id": pid, "items": items})
    assert r.status_code == 201 and r.json()["status"] == "ACTIVE", r.text


def _scheduled(pid: str) -> list[OutboundMessage]:
    with SessionLocal() as db:
        return list(db.scalars(select(OutboundMessage).where(
            OutboundMessage.patient_id == uuid.UUID(pid), OutboundMessage.idempotency_key.like("rem:%"))
            .order_by(OutboundMessage.scheduled_for)).all())


def test_follow_ups_due_the_same_day_share_one_reminder_per_day(nurse, seeded):
    pid = new_patient(nurse, "Same Day Pair", "+919000300101", plan_days=None)
    _plan(nurse, pid, 12, 12)
    msgs = _scheduled(pid)
    days = [m.scheduled_for for m in msgs]
    assert msgs and len(days) == len(set(days))  # one reminder per send day, not one per follow-up


def test_a_patient_gets_at_most_one_scheduled_reminder_a_day(nurse, seeded):
    # Review due in 10 days, kidney test due in 12: the review's "1 day before" and the test's
    # "3 days before" fall on the same day (day 9).
    pid = new_patient(nurse, "Overlap Pair", "+919000300102", plan_days=None)
    _plan(nurse, pid, 10, 12)
    msgs = _scheduled(pid)
    with SessionLocal() as db:
        clinic = db.get(Clinic, uuid.UUID(seeded["clinic_a"]))
        day9 = clinic_today(nurse) + timedelta(days=9)
        send_at = local_dt(clinic, day9, clinic.reminder_send_hour)
        same_day = [db.get(OutboundMessage, m.id) for m in msgs if m.scheduled_for == send_at]
        assert len(same_day) == 2
        for m in same_day:
            messaging._dispatch_one(db, m, clinic, send_at + timedelta(minutes=1))
        statuses = sorted((m.status, m.suppressed_reason) for m in same_day)
        db.rollback()  # leave the shared test database as it was
    assert statuses == [("QUEUED", ""), ("SUPPRESSED", "ALREADY_REMINDED_TODAY")]


def test_confirming_covers_every_follow_up_due_that_day(nurse, seeded):
    pid = new_patient(nurse, "Confirm Pair", "+919000300103", plan_days=None)
    _plan(nurse, pid, 6, 6)
    patient_session(nurse, "nurse@sunrise.demo", pid)
    r = nurse.post("/v1/p/replies/button", json={"choice": "CONFIRM", "client_key": "confirm-pair-0001"})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        items = db.scalars(select(FollowUpItem).where(FollowUpItem.patient_id == uuid.UUID(pid))).all()
        assert len(items) == 2 and {i.status for i in items} == {"CONFIRMED_BY_PATIENT"}
