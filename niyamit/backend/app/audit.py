"""Audit trail (who did what) and patient timeline (factual, source-linked history)."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.context import correlation_id
from app.enums import ActorType, Provenance
from app.models import AuditEvent, TimelineEvent
from app.security import Staff


def audit(
    db: Session,
    *,
    clinic_id: uuid.UUID | None,
    action: str,
    actor: Staff | None = None,
    actor_type: str | None = None,
    actor_id: str = "",
    object_type: str = "",
    object_id: object = "",
    patient_id: uuid.UUID | None = None,
    outcome: str = "SUCCESS",
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditEvent(
            clinic_id=clinic_id,
            actor_type=actor_type or (ActorType.USER if actor else ActorType.SYSTEM),
            actor_id=str(actor.user_id) if actor else actor_id,
            actor_role=actor.role if actor else "",
            action=action,
            object_type=object_type,
            object_id=str(object_id) if object_id else "",
            patient_id=patient_id,
            outcome=outcome,
            correlation_id=correlation_id.get(),
            detail=detail or {},
        )
    )


def timeline(
    db: Session,
    *,
    clinic_id: uuid.UUID,
    patient_id: uuid.UUID,
    event_type: str,
    summary: str,
    provenance: Provenance,
    actor_type: ActorType = ActorType.SYSTEM,
    actor_label: str = "System",
    patient_words: str | None = None,
    source_type: str = "",
    source_id: object = "",
    visibility: str = "PATIENT_AND_STAFF",
) -> None:
    db.add(
        TimelineEvent(
            clinic_id=clinic_id,
            patient_id=patient_id,
            event_type=event_type,
            actor_type=actor_type,
            actor_label=actor_label,
            provenance=provenance,
            summary=summary,
            patient_words=patient_words,
            source_type=source_type,
            source_id=str(source_id) if source_id else "",
            visibility=visibility,
        )
    )
