"""Plain-dict views of models for the API. Provenance labels travel with the data so the UI can show
'patient said' vs 'AI proposed' vs 'staff confirmed' vs 'clinician approved' everywhere."""
from __future__ import annotations

import re

from datetime import date, datetime
from typing import Any

from app.ai.contracts import FIELD_LABELS
from app.enums import ITEM_LABELS, ItemKind
from app.models import (
    Appointment,
    AppointmentRequest,
    CareTask,
    ExtractedField,
    ExtractionProposal,
    FollowUpItem,
    FollowUpPlan,
    OutboundMessage,
    Patient,
    PatientReply,
    SourceArtifact,
    TimelineEvent,
)
from app.storage import sign


def iso(v: datetime | date | None) -> str | None:
    return v.isoformat() if v else None


def patient_brief(p: Patient) -> dict[str, Any]:
    return {"id": str(p.id), "name": p.display_name, "phone": p.phone_e164, "language": p.preferred_language,
            "channel": p.preferred_channel, "opted_out": p.opted_out, "is_synthetic": p.is_synthetic,
            "external_ref": p.external_ref, "birth_year": p.birth_year, "last_visit_at": iso(p.last_visit_at)}


def item_dict(i: FollowUpItem, today: date | None = None) -> dict[str, Any]:
    overdue = (today - i.due_date).days if today and i.due_date < today and i.status not in ("COMPLETED", "CANCELLED") else 0
    return {"id": str(i.id), "kind": i.kind, "label": i.label or ITEM_LABELS[ItemKind(i.kind)],
            "due_date": iso(i.due_date), "status": i.status, "days_overdue": overdue,
            "source_field_id": str(i.source_field_id) if i.source_field_id else None,
            "patient_confirmed_at": iso(i.patient_confirmed_at), "completed_at": iso(i.completed_at)}


def plan_dict(p: FollowUpPlan, today: date | None = None, approver: str | None = None) -> dict[str, Any]:
    return {"id": str(p.id), "status": p.status, "version": p.version, "source": p.source,
            "approved_at": iso(p.approved_at), "approved_by": approver, "notes": p.notes,
            "proposal_id": str(p.proposal_id) if p.proposal_id else None,
            "source_artifact_id": str(p.source_artifact_id) if p.source_artifact_id else None,
            "items": [item_dict(i, today) for i in p.items], "created_at": iso(p.created_at)}


def task_dict(t: CareTask, patient: Patient | None = None, assignee: str | None = None,
              with_events: bool = False) -> dict[str, Any]:
    out = {"id": str(t.id), "patient_id": str(t.patient_id), "category": t.category, "queue": t.queue,
           "priority": t.priority, "status": t.status, "title": t.title, "barrier_category": t.barrier_category,
           "patient_statement": t.patient_statement, "assignee_user_id": str(t.assignee_user_id) if t.assignee_user_id else None,
           "assignee": assignee, "due_at": iso(t.due_at), "escalated_at": iso(t.escalated_at), "outcome": t.outcome,
           "outcome_note": t.outcome_note, "created_at": iso(t.created_at), "resolved_at": iso(t.resolved_at),
           "source_type": t.source_type, "source_id": t.source_id}
    if patient:
        out["patient"] = {"id": str(patient.id), "name": patient.display_name, "phone": patient.phone_e164,
                          "language": patient.preferred_language}
    if with_events:
        out["events"] = [{"from": e.from_status, "to": e.to_status, "by": e.actor_label, "note": e.note,
                          "at": iso(e.created_at)} for e in t.events]
    return out


STATUS_LABEL = {
    "SCHEDULED": "Scheduled", "QUEUED": "Queued", "SENDING": "Sending",
    "SENT_TO_PROVIDER": "Sent to provider (delivery not confirmed)", "DELIVERED": "Delivered (provider confirmed)",
    "FAILED": "Failed", "SUPPRESSED": "Suppressed (not sent)", "UNKNOWN": "Status unknown",
}


_ACCESS_LINK = re.compile(r"(/(?:p|c)/)[A-Za-z0-9_\-.~]{8,}")


def mask_links(text: str) -> str:
    """Staff screens never show a patient's or helper's private access token (the link itself is audited)."""
    return _ACCESS_LINK.sub(r"\1[private link]", text or "")


def message_dict(m: OutboundMessage, patient: Patient | None = None) -> dict[str, Any]:
    out = {"id": str(m.id), "patient_id": str(m.patient_id), "kind": m.kind, "template_key": m.template_key,
           "language": m.language, "channel": m.channel, "simulated": m.channel == "SIMULATED",
           "body": mask_links(m.body),
           "status": m.status, "status_label": STATUS_LABEL.get(m.status, m.status), "essential": m.essential,
           "scheduled_for": iso(m.scheduled_for), "sent_at": iso(m.sent_at), "delivered_at": iso(m.delivered_at),
           "failed_at": iso(m.failed_at), "attempts": m.attempts, "last_error_code": m.last_error_code,
           "suppressed_reason": m.suppressed_reason, "created_at": iso(m.created_at)}
    if patient:
        out["patient_name"] = patient.display_name
    return out


def reply_dict(r: PatientReply) -> dict[str, Any]:
    from app.services.labels import CHOICE_LABELS

    choice = CHOICE_LABELS.get((r.text or "").upper()) if r.input_mode == "BUTTON" else None
    return {"id": str(r.id), "patient_id": str(r.patient_id), "channel": r.channel, "input_mode": r.input_mode,
            "choice_label": choice,
            "status": r.status, "text": r.text, "transcript": r.transcript, "corrected_text": r.corrected_text,
            "detected_language": r.detected_language, "language_confidence": r.language_confidence,
            "asr_provider": r.asr_provider, "understanding": r.understanding,
            "understanding_source": r.understanding_source, "provider_notes": r.provider_notes,
            "actions": r.actions, "error_code": r.error_code, "via_caregiver": bool(r.caregiver_grant_id),
            "created_at": iso(r.created_at), "processed_at": iso(r.processed_at)}


def artifact_dict(a: SourceArtifact) -> dict[str, Any]:
    return {"id": str(a.id), "filename": a.filename, "mime_type": a.mime_type, "size_bytes": a.size_bytes,
            "page_count": a.page_count, "source_type": a.source_type, "uploaded_by_patient": a.uploaded_by_patient,
            "is_synthetic": a.is_synthetic, "created_at": iso(a.created_at),
            "content_url": f"/v1/artifacts/{a.id}/content?{sign(str(a.id))}",
            "page_url": f"/v1/artifacts/{a.id}/page/{{page}}?{sign(str(a.id))}"}


def field_dict(f: ExtractedField) -> dict[str, Any]:
    return {"id": str(f.id), "name": f.name, "label": FIELD_LABELS.get(f.name, f.name), "value": f.value,
            "proposed_value": f.proposed_value, "extracted_value": f.extracted_value, "status": f.status, "confidence": f.confidence,
            "evidence": f.evidence, "review_reasons": f.review_reasons, "reviewed_at": iso(f.reviewed_at),
            "provenance": "STAFF_CONFIRMED" if f.status == "APPROVED" else "AI_PROPOSED"}


def proposal_dict(p: ExtractionProposal, artifact: SourceArtifact | None, patient: Patient | None,
                  with_blocks: bool = False) -> dict[str, Any]:
    out = {"id": str(p.id), "status": p.status, "created_at": iso(p.created_at), "processed_at": iso(p.processed_at),
           "ocr_provider": p.ocr_provider, "extractor": p.llm_provider, "model_version": p.model_version,
           "pipeline_version": p.pipeline_version, "error_code": p.error_code, "notes": p.provider_notes,
           "plan_id": str(p.plan_id) if p.plan_id else None, "fields": [field_dict(f) for f in p.fields],
           "artifact": artifact_dict(artifact) if artifact else None,
           "patient": patient_brief(patient) if patient else None, "page_sizes": p.page_sizes}
    if with_blocks:
        out["blocks"] = p.blocks
    return out


def timeline_dict(e: TimelineEvent) -> dict[str, Any]:
    return {"id": str(e.id), "type": e.event_type, "summary": e.summary, "provenance": e.provenance,
            "actor_type": e.actor_type, "actor": e.actor_label, "patient_words": e.patient_words,
            "source_type": e.source_type, "source_id": e.source_id, "visibility": e.visibility,
            "at": iso(e.occurred_at)}


def appointment_dict(a: Appointment, slot_label: str | None = None) -> dict[str, Any]:
    return {"id": str(a.id), "status": a.status, "reference": a.booking_reference, "slot_label": slot_label,
            "created_by": a.created_by, "committed_at": iso(a.committed_at)}


def request_dict(r: AppointmentRequest) -> dict[str, Any]:
    labels = {"REQUESTED": "Request received", "NEEDS_CLARIFICATION": "Waiting for a day choice",
              "SLOTS_OFFERED": "Waiting for slot choice", "BOOKED": "Booked", "NOT_BOOKED": "Not booked",
              "HANDED_TO_STAFF": "Waiting for clinic (staff will call)", "CANCELLED": "Cancelled"}
    return {"id": str(r.id), "status": r.status, "status_label": labels.get(r.status, r.status),
            "requested_day_text": r.requested_day_text, "requested_date": iso(r.requested_date),
            "requested_time_window": r.requested_time_window, "patient_statement": r.patient_statement,
            "requested_by": r.requested_by, "failure_reason": r.failure_reason, "created_at": iso(r.created_at)}
