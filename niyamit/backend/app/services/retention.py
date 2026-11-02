"""Retention: voice notes and documents are deleted when their retention period ends (clinic setting)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.audit import audit
from app.db import utcnow
from app.models import SourceArtifact


def purge_expired(db: Session) -> int:
    rows = db.scalars(select(SourceArtifact).where(SourceArtifact.retention_until < utcnow(),
                                                   SourceArtifact.deleted_at.is_(None)).limit(200)).all()
    for a in rows:
        storage.delete(a.storage_key)
        a.deleted_at = utcnow()
        audit(db, clinic_id=a.clinic_id, action="ARTIFACT_PURGED", object_type="source_artifact", object_id=a.id,
              patient_id=a.patient_id, detail={"reason": "retention period ended", "type": a.source_type})
    return len(rows)
