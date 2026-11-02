"""Background jobs. Side effects are deferred until the database transaction commits (outbox pattern):
`defer(db, ...)` records the job and it is enqueued only after a successful commit.

With TASKS_EAGER=true jobs run inline right after commit (tests and no-Redis mode); otherwise they go to Celery.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.config import settings
from app.context import correlation_id, new_correlation_id
from app.db import SessionLocal

log = logging.getLogger("niyamit.jobs")


def defer(db: Session, name: str, *args: object, countdown: float | None = None) -> None:
    db.info.setdefault("deferred_jobs", []).append((name, [str(a) for a in args], countdown, correlation_id.get()))


@event.listens_for(Session, "after_commit")
def _after_commit(session: Session) -> None:
    jobs = session.info.pop("deferred_jobs", [])
    for name, args, countdown, cid in jobs:
        dispatch(name, args, countdown, cid)


@event.listens_for(Session, "after_rollback")
def _after_rollback(session: Session) -> None:
    session.info.pop("deferred_jobs", None)


def dispatch(name: str, args: list[str], countdown: float | None = None, cid: str = "") -> None:
    if settings.tasks_eager:
        run_job(name, args, cid)
        return
    from app.worker import celery_app

    try:
        celery_app.send_task(f"niyamit.{name}", args=args, countdown=countdown, headers={"cid": cid})
    except Exception:  # noqa: BLE001 - broker down: the periodic recovery job re-dispatches from the DB
        log.exception("enqueue failed; recovery job will retry", extra={"event": name})


def run_job(name: str, args: list[str], cid: str = "") -> None:
    token = correlation_id.set(cid or new_correlation_id())
    try:
        JOBS[name](*args)
    finally:
        correlation_id.reset(token)


# ------------------------------------------------------------------ job bodies
def _with_session(fn: Callable[[Session], object]) -> object:
    with SessionLocal() as db:
        result = fn(db)
        db.commit()
        return result


def process_reply(reply_id: str) -> None:
    from app.services.replies import process_reply as run

    _with_session(lambda db: run(db, uuid.UUID(reply_id)))


def process_extraction(proposal_id: str) -> None:
    from app.services.intake import run_extraction

    _with_session(lambda db: run_extraction(db, uuid.UUID(proposal_id)))


def send_message(message_id: str) -> None:
    from app.services.messaging import send

    with SessionLocal() as db:
        send(db, uuid.UUID(message_id))


def simulated_delivery(message_id: str) -> None:
    from app.services.inbound import simulate_delivery_callback

    _with_session(lambda db: simulate_delivery_callback(db, uuid.UUID(message_id)))


def run_eval(run_id: str) -> None:
    from app.services.evaluation import execute_run

    _with_session(lambda db: execute_run(db, uuid.UUID(run_id)))


def periodic() -> dict[str, int]:
    """One scheduler tick: dispatch due messages, recover stuck jobs, create/escalate tasks, retention."""
    from app.services import messaging, recovery, retention, tasks

    out: dict[str, int] = {}
    with SessionLocal() as db:
        out["dispatched"] = messaging.dispatch_due(db)
        db.commit()
        out["recovered"] = messaging.recover_stuck(db)
        db.commit()
        out["reconciled"] = recovery.recover(db)
        db.commit()
        out["overdue_tasks"] = tasks.create_overdue_tasks(db)
        out["escalated"] = tasks.escalate_unassigned(db)
        db.commit()
        out["purged_audio"] = retention.purge_expired(db)
        db.commit()
    return out


JOBS: dict[str, Callable[..., object]] = {
    "process_reply": process_reply,
    "process_extraction": process_extraction,
    "send_message": send_message,
    "simulated_delivery": simulated_delivery,
    "run_eval": run_eval,
}
