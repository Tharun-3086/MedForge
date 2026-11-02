"""Job reconciliation (PRD 12.3, 15): work that was stored but never processed (for example because the queue was
down at the time) is re-dispatched; work that stays stuck is moved to a visible failed state and handed to staff
instead of waiting silently."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.enums import ProposalStatus, ReplyStatus, TaskCategory, TaskQueue
from app.jobs import defer
from app.models import Clinic, ExtractionProposal, Patient, PatientReply

RETRY_AFTER = timedelta(minutes=2)
GIVE_UP_AFTER = timedelta(minutes=30)


def _once_per(key: str, seconds: int) -> bool:
    """Re-dispatch a given job at most once per interval (Redis SET NX); without Redis, always allow."""
    try:
        from app.redis_client import get_redis

        return bool(get_redis().set(f"recover:{key}", "1", nx=True, ex=seconds))
    except Exception:  # noqa: BLE001
        return True


def recover(db: Session) -> int:
    from app.services.tasks import create_task

    now = utcnow()
    count = 0
    for reply in db.scalars(select(PatientReply).where(PatientReply.status == ReplyStatus.RECEIVED,
                                                       PatientReply.created_at < now - RETRY_AFTER).limit(100)).all():
        if reply.created_at < now - GIVE_UP_AFTER:
            reply.status, reply.error_code = ReplyStatus.ACTION_FAILED, "PROCESSING_TIMEOUT"
            reply.provider_notes = ["Automatic processing did not complete; handed to staff."]
            create_task(db, clinic=db.get(Clinic, reply.clinic_id), patient=db.get(Patient, reply.patient_id),
                        category=TaskCategory.UNCLEAR_INPUT, queue=TaskQueue.RECEPTION,
                        title="Patient message could not be processed automatically — please read and act",
                        statement=reply.text, dedupe_key=f"stuck:{reply.id}", source_type="patient_reply",
                        source_id=reply.id)
            count += 1
        elif _once_per(f"reply:{reply.id}", 120):
            defer(db, "process_reply", reply.id)
            count += 1
    for prop in db.scalars(select(ExtractionProposal).where(
            ExtractionProposal.status == ProposalStatus.EXTRACTION_PENDING,
            ExtractionProposal.created_at < now - RETRY_AFTER).limit(50)).all():
        if prop.created_at < now - GIVE_UP_AFTER:
            prop.status, prop.error_code = ProposalStatus.EXTRACTION_FAILED, "PROCESSING_TIMEOUT"
            prop.provider_notes = ["Extraction did not complete; retry from the Report Inbox."]
            count += 1
        elif _once_per(f"proposal:{prop.id}", 180):
            defer(db, "process_extraction", prop.id)
            count += 1
    return count
