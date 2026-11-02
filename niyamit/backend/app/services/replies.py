"""Voice Bridge (PRD 7.3, 8): patient text/voice -> transcript -> constrained understanding -> deterministic
actions. The AI proposes; this module decides. Clinical and urgent messages always go to a human."""
from __future__ import annotations

import copy
import hashlib
import logging
import uuid
from datetime import timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import storage
from app.ai import pipeline
from app.ai.contracts import ReplyUnderstanding
from app.ai.dates import resolve_day_expression
from app.ai.providers.base import ProviderError
from app.audit import timeline
from app.config import settings
from app.db import utcnow
from app.enums import (
    ActorType,
    BarrierCategory,
    Channel,
    ConsentPurpose,
    InputMode,
    Intent,
    MessageKind,
    Provenance,
    ReplyStatus,
    RequestStatus,
    SourceType,
    TaskCategory,
    TaskQueue,
)
from app.jobs import defer
from app.models import AppointmentRequest, Clinic, Patient, PatientReply, SourceArtifact
from app.services import booking, messaging, patients, plans
from app.services.common import active_faults, clinic_today, current_item, day_label
from app.services.labels import CHOICE_LABELS
from app.services.links import has_consent
from app.services.tasks import BARRIER_ROUTING, create_task
from app.services.templates import TemplateNotApproved, render

log = logging.getLogger("niyamit.replies")

# Explicit choices are deterministic (no AI): app buttons, and short replies to messages ("1", "STOP").
EXPLICIT: dict[str, tuple[Intent | str, str | None]] = {
    "CONFIRM": (Intent.CONFIRM_FOLLOWUP, None), "1": (Intent.CONFIRM_FOLLOWUP, None),
    "RESCHEDULE": (Intent.RESCHEDULE_REQUEST, None), "2": (Intent.RESCHEDULE_REQUEST, None),
    "CALLBACK": (Intent.CALLBACK_REQUEST, None), "3": (Intent.CALLBACK_REQUEST, None),
    "UPLOAD": (Intent.REPORT_UPLOAD_INTENT, None),
    "STOP": (Intent.OPT_OUT, None), "OPT_OUT": (Intent.OPT_OUT, None),
    "START": ("START", None),
    **{f"BARRIER:{b.value}": (Intent.BARRIER_REPORTED, b.value) for b in BarrierCategory},
}
ORDER = [Intent.URGENT_CONCERN, Intent.CLINICAL_QUESTION, Intent.OPT_OUT, Intent.CALLBACK_REQUEST,
         Intent.BARRIER_REPORTED, Intent.RESCHEDULE_REQUEST, Intent.CONFIRM_FOLLOWUP, Intent.REPORT_UPLOAD_INTENT,
         Intent.OTHER_OR_UNCLEAR]
SAFETY = {Intent.URGENT_CONCERN, Intent.CLINICAL_QUESTION, Intent.OPT_OUT}
INTENT_LABEL = {
    Intent.CONFIRM_FOLLOWUP: "Confirm follow-up", Intent.RESCHEDULE_REQUEST: "Change date / time",
    Intent.REPORT_UPLOAD_INTENT: "Share a report", Intent.CALLBACK_REQUEST: "Call me back",
    Intent.BARRIER_REPORTED: "Difficulty attending", Intent.CLINICAL_QUESTION: "Question for the clinic",
    Intent.URGENT_CONCERN: "Possible urgent concern", Intent.OPT_OUT: "Stop messages",
    Intent.OTHER_OR_UNCLEAR: "Not clear",
}


def ingest(db: Session, clinic: Clinic, patient: Patient, *, channel: str, mode: str, idempotency_key: str,
           text: str | None = None, audio: tuple[bytes, str] | None = None,
           provider_event_id: uuid.UUID | None = None, caregiver_grant_id: uuid.UUID | None = None
           ) -> tuple[PatientReply, bool]:
    """Store the inbound reply first (fast), process later. Same idempotency key -> same reply."""
    existing = db.scalar(select(PatientReply).where(PatientReply.idempotency_key == idempotency_key))
    if existing:
        return existing, False
    if mode == InputMode.TEXT and not (text or "").strip():
        raise HTTPException(422, "Message is empty.")
    reply = PatientReply(clinic_id=clinic.id, patient_id=patient.id, channel=channel, input_mode=mode,
                         idempotency_key=idempotency_key, provider_event_id=provider_event_id,
                         caregiver_grant_id=caregiver_grant_id, text=(text or "").strip()[:2000] or None,
                         status=ReplyStatus.RECEIVED)
    if audio is not None:
        data, filename = audio
        vf = storage.validate_audio(data, filename)
        art_id = uuid.uuid4()
        db.add(SourceArtifact(id=art_id, clinic_id=clinic.id, patient_id=patient.id, uploaded_by_patient=True,
                              source_type=SourceType.VOICE_NOTE, filename=vf.filename, mime_type=vf.mime,
                              size_bytes=len(vf.data), sha256=vf.sha256,
                              storage_key=storage.store(clinic.id, art_id, vf.data),
                              retention_until=utcnow() + timedelta(days=clinic.audio_retention_days)))
        reply.audio_artifact_id = art_id
    db.add(reply)
    db.flush()
    if mode == InputMode.BUTTON and channel == Channel.PATIENT_APP:
        # A tapped button needs no AI, so it is answered at once; the worker remains the fallback.
        try:
            with db.begin_nested():
                process_reply(db, reply.id)
            return reply, True
        except Exception:
            log.exception("Inline processing of a button reply failed; handing it to the worker.")
    defer(db, "process_reply", reply.id)
    return reply, True


def explicit_choice(text: str | None) -> tuple[Intent | str, str | None] | None:
    key = (text or "").strip().upper().rstrip(".!")
    return EXPLICIT.get(key)


def process_reply(db: Session, reply_id: uuid.UUID) -> None:
    reply = db.get(PatientReply, reply_id, with_for_update=True, populate_existing=True)
    if reply is None or reply.status != ReplyStatus.RECEIVED:
        return  # already processed: duplicate deliveries do nothing
    patient = db.get(Patient, reply.patient_id)
    clinic = db.get(Clinic, reply.clinic_id)
    faults = active_faults(db)
    reply.status = ReplyStatus.VALIDATED
    text = reply.text or ""
    via = "Caregiver" if reply.caregiver_grant_id else "Patient"
    # Patient content goes to an external AI provider only with recorded consent; otherwise offline rules.
    ai_ok = has_consent(db, patient.id, ConsentPurpose.AI_PROCESSING)

    if reply.input_mode == InputMode.VOICE:
        art = db.get(SourceArtifact, reply.audio_artifact_id)
        try:
            if not ai_ok:
                raise ProviderError("speech", "NO_AI_CONSENT", "Voice notes need consent for AI processing")
            try:
                audio = storage.load(art.storage_key)
            except storage.StorageUnavailable:
                raise ProviderError("storage", "STORAGE_UNREADABLE") from None
            tr = pipeline.transcribe(audio, art.mime_type, art.filename, patient.preferred_language, faults)
        except ProviderError as exc:
            reply.status, reply.error_code = ReplyStatus.TRANSCRIPTION_FAILED, exc.code
            reply.provider_notes = [f"Speech-to-text failed ({exc.provider}: {exc.code}). No transcript was invented."]
            reply.processed_at = utcnow()
            timeline(db, clinic_id=clinic.id, patient_id=patient.id, event_type="PATIENT_REPLY",
                     summary=f"{via} sent a voice note that could not be transcribed ({exc.code}); text, buttons and callback offered",
                     provenance=Provenance.PATIENT_REPORTED, actor_type=ActorType.PATIENT, actor_label=via,
                     source_type="patient_reply", source_id=reply.id)
            if reply.channel != Channel.PATIENT_APP:
                _send(db, clinic, patient, reply, "VOICE_FAILED", MessageKind.CLARIFICATION)
            return
        reply.transcript, reply.detected_language = tr.text, tr.language_code
        reply.language_confidence, reply.asr_provider = tr.language_probability, f"{tr.provider}:{tr.model}"
        text = tr.text

    choice = explicit_choice(text) if reply.input_mode in (InputMode.BUTTON, InputMode.TEXT) else None
    if choice and choice[0] == "START":
        patients.opt_in(db, patient, method="MESSAGE" if reply.channel != Channel.PATIENT_APP else "PATIENT_APP")
        reply.understanding = {"intents": ["OPT_IN"], "confidence": 1.0}
        reply.understanding_source, reply.status, reply.processed_at = "BUTTON", ReplyStatus.ACTION_SUCCEEDED, utcnow()
        return
    if choice:
        intent, barrier = choice
        u = ReplyUnderstanding(intents=[intent], barrier_category=barrier, confidence=1.0, source_text=text,
                               opt_out_present=intent == Intent.OPT_OUT)
        source, notes = "BUTTON", []
    else:
        res = pipeline.understand_reply(text, today=clinic_today(clinic), preferred_language=patient.preferred_language,
                                        faults=faults, provider=None if ai_ok else "rules")
        u, source, notes = res.understanding, res.source, res.notes
        if not ai_ok:
            notes = ["No consent for AI processing on record; understood with offline rules only.", *notes]
    reply.understanding = u.model_dump(mode="json")
    reply.understanding_source, reply.provider_notes = source, notes
    reply.status = ReplyStatus.CLASSIFIED
    where = REPLY_CHANNELS.get(reply.channel, "via " + reply.channel.lower())
    if choice:
        # A tapped button or a numbered shortcut is a choice, not the patient's own words: describe it, don't quote it.
        label = CHOICE_LABELS.get(text.strip().upper().rstrip(".!"), text)
        summary = (f"{via} tapped “{label}” {where}" if reply.input_mode == InputMode.BUTTON
                   else f"{via} replied “{text.strip()[:40]}” ({label}) {where}")
        words = ""
    else:
        summary = f"{via} replied {REPLY_MODES.get(reply.input_mode, 'by ' + reply.input_mode.lower())} {where}"
        words = text
    timeline(db, clinic_id=clinic.id, patient_id=patient.id, event_type="PATIENT_REPLY", summary=summary,
             provenance=Provenance.PATIENT_REPORTED, actor_type=ActorType.CAREGIVER if via == "Caregiver" else ActorType.PATIENT,
             actor_label=via, patient_words=words[:1000] or None, source_type="patient_reply", source_id=reply.id)
    execute(db, clinic, patient, reply, u, explicit=choice is not None, text=words)
    reply.processed_at = utcnow()


REPLY_MODES = {"TEXT": "by text", "VOICE": "by voice note", "BUTTON": "with a quick-reply button"}
REPLY_CHANNELS = {"SIMULATED": "on the simulated phone", "WHATSAPP": "on WhatsApp", "PATIENT_APP": "in the patient app"}


def execute(db: Session, clinic: Clinic, patient: Patient, reply: PatientReply, u: ReplyUnderstanding, *,
            explicit: bool, text: str) -> None:
    actions: list[dict[str, Any]] = []
    item = current_item(db, patient.id)
    intents = [i for i in ORDER if i in u.intents]
    low_conf = (not explicit) and u.confidence < settings.clarify_confidence_threshold
    app = reply.channel == Channel.PATIENT_APP

    # Low confidence and nothing safety-related: ask, do not act ("never guess the barrier or action").
    if low_conf and not (set(intents) & SAFETY):
        actions.append(_clarify_action(db, clinic, patient, reply, intents, item))
        _finish(db, reply, actions)
        return

    for intent in intents:
        if intent == Intent.URGENT_CONCERN:
            task, _ = create_task(db, clinic=clinic, patient=patient, category=TaskCategory.URGENT_CONCERN,
                                  queue=clinic.urgent_queue, priority="URGENT", statement=text,
                                  title="Possible urgent concern reported — clinician to call now",
                                  dedupe_key=f"urgent:{reply.id}", source_type="patient_reply", source_id=reply.id)
            actions.append(_act(intent, "DONE", task_id=task.id,
                                patient_text=_text(db, clinic, patient, "URGENT_ESCALATION")))
            _send(db, clinic, patient, reply, "URGENT_ESCALATION", MessageKind.URGENT_ESCALATION, force=app)
        elif intent == Intent.CLINICAL_QUESTION:
            task, _ = create_task(db, clinic=clinic, patient=patient, category=TaskCategory.CLINICAL_QUESTION,
                                  queue=clinic.clinical_queue, statement=text,
                                  title="Patient asked a clinical question — clinician to respond",
                                  dedupe_key=f"clinical:{reply.id}", source_type="patient_reply", source_id=reply.id)
            actions.append(_act(intent, "HANDED_TO_CLINICIAN", task_id=task.id,
                                patient_text=_text(db, clinic, patient, "CLINICAL_ACK")))
            if not app:
                _send(db, clinic, patient, reply, "CLINICAL_ACK", MessageKind.ACKNOWLEDGEMENT)
        elif intent == Intent.OPT_OUT:
            if explicit:
                patients.opt_out(db, clinic, patient, method="PATIENT_APP" if app else "MESSAGE")
                actions.append(_act(intent, "DONE", patient_text=_text(db, clinic, patient, "OPT_OUT_CONFIRMED")))
            else:
                actions.append(_act(intent, "AWAITING_CONFIRMATION",
                                    question="Do you want to stop all reminder messages from the clinic?",
                                    question_key="CONFIRM_OPT_OUT"))
        elif intent == Intent.CALLBACK_REQUEST:
            task, _ = create_task(db, clinic=clinic, patient=patient, category=TaskCategory.CALLBACK,
                                  queue=TaskQueue.RECEPTION, statement=text, title="Patient asked for a call back",
                                  dedupe_key=f"callback:{patient.id}", source_type="patient_reply", source_id=reply.id)
            actions.append(_act(intent, "DONE", task_id=task.id, patient_text=_text(db, clinic, patient, "CALLBACK_ACK")))
            if not app:
                _send(db, clinic, patient, reply, "CALLBACK_ACK", MessageKind.ACKNOWLEDGEMENT)
        elif intent == Intent.BARRIER_REPORTED:
            cat = u.barrier_category or BarrierCategory.OTHER
            queue, title = BARRIER_ROUTING.get(cat, BARRIER_ROUTING[BarrierCategory.OTHER])
            task, _ = create_task(db, clinic=clinic, patient=patient, category=TaskCategory.BARRIER, queue=queue,
                                  barrier=cat, statement=text, title=title, dedupe_key=f"barrier:{patient.id}:{cat}",
                                  source_type="patient_reply", source_id=reply.id)
            actions.append(_act(intent, "DONE", task_id=task.id, barrier=cat,
                                patient_text=_text(db, clinic, patient, "BARRIER_ACK")))
            if not app:
                _send(db, clinic, patient, reply, "BARRIER_ACK", MessageKind.ACKNOWLEDGEMENT)
        elif intent == Intent.RESCHEDULE_REQUEST:
            actions.append(_reschedule(db, clinic, patient, reply, u, item, text))
            if not app and actions[-1]["status"] == "AWAITING_SLOT_CHOICE":
                _send(db, clinic, patient, reply, "RESCHEDULE_OPTIONS", MessageKind.ACKNOWLEDGEMENT)
        elif intent == Intent.CONFIRM_FOLLOWUP:
            question = _confirmation_question(u, text, item, clinic_today(clinic)) if item and not explicit else None
            if item is None:
                actions.append(_act(intent, "NO_OPEN_FOLLOW_UP"))
            elif question:  # "I'll come next week" is not a confirmation of a different date: ask first
                actions.append(_act(intent, "AWAITING_CONFIRMATION", item_id=item.id, question=question,
                                    question_key="CONFIRM_MISMATCH", options=["CONFIRM", "RESCHEDULE"],
                                    due_date=item.due_date.isoformat(), day_words=u.requested_day_text))
            else:
                changed = plans.record_patient_confirmation(db, patient, item, text,
                                                            via="Caregiver" if reply.caregiver_grant_id else "Patient")
                due = item.due_date
                actions.append(_act(intent, "DONE" if changed else "ALREADY_RECORDED", item_id=item.id,
                                    patient_text=_text(db, clinic, patient, "CONFIRM_ACK", due_date=due)))
                if not app and changed:
                    _send(db, clinic, patient, reply, "CONFIRM_ACK", MessageKind.ACKNOWLEDGEMENT, due_date=due)
        elif intent == Intent.REPORT_UPLOAD_INTENT:
            actions.append(_act(intent, "AWAITING_UPLOAD"))
            if not app:
                _send(db, clinic, patient, reply, "REPORT_UPLOAD_LINK", MessageKind.ACKNOWLEDGEMENT)
        elif intent == Intent.OTHER_OR_UNCLEAR:
            actions.append(_clarify_action(db, clinic, patient, reply, [], item))
    _finish(db, reply, actions)


def _confirmation_question(u: ReplyUnderstanding, text: str, item, today) -> str | None:
    """A confirmation that names a day must name the due date; otherwise the patient is asked."""
    res = resolve_day_expression(u.requested_date.isoformat() if u.requested_date else (u.requested_day_text or text),
                                 today)
    if res.kind == "NONE" or res.candidate == item.due_date:
        return None
    due = day_label(item.due_date, "%A")
    said = f"'{res.matched}'" if res.matched else "a different day"
    return f"Your follow-up is on {due}. You mentioned {said} — keep {due}, or change the date?"


def _act(intent: Intent | str, status: str, **extra: Any) -> dict[str, Any]:
    out = {"intent": str(intent), "label": INTENT_LABEL.get(intent, str(intent)), "status": status}
    out.update({k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in extra.items()})
    return out


def _text(db: Session, clinic: Clinic, patient: Patient, key: str, **values: object) -> str | None:
    try:
        body, _ = render(db, clinic.id, key, patient.preferred_language, clinic=clinic.short_name,
                         clinic_phone=clinic.phone, link="", **values)
        return body.replace(" or open: ", "").rstrip(": ").strip()
    except TemplateNotApproved:
        return None


def _send(db: Session, clinic: Clinic, patient: Patient, reply: PatientReply, key: str, kind: MessageKind, *,
          force: bool = False, **values: object) -> None:
    if reply.channel == Channel.PATIENT_APP and not force:
        return
    messaging.queue_message(db, clinic=clinic, patient=patient, kind=kind, template_key=key,
                            idempotency_key=f"ack:{reply.id}:{key}", values=values, reply_id=reply.id)


def _reschedule(db: Session, clinic: Clinic, patient: Patient, reply: PatientReply, u: ReplyUnderstanding,
                item, text: str) -> dict[str, Any]:
    today = clinic_today(clinic)
    if u.requested_date and u.requested_date >= today:
        res = resolve_day_expression(u.requested_date.isoformat(), today)
    else:
        res = resolve_day_expression(u.requested_day_text or text, today)
    req = booking.create_request(db, clinic, patient, item=item, reply_id=reply.id,
                                 requested_by="CAREGIVER" if reply.caregiver_grant_id else "PATIENT",
                                 day_text=u.requested_day_text or res.matched, requested=res.candidate,
                                 window=u.requested_time_window, statement=text)
    slots = booking.offer_slots(db, clinic, req, day=res.candidate, days=res.options or None)
    if req.status == RequestStatus.HANDED_TO_STAFF:
        return _act(Intent.RESCHEDULE_REQUEST, "HANDED_TO_STAFF", request_id=req.id, task_id=req.task_id,
                    reason=req.failure_reason, patient_text=_text(db, clinic, patient, "BOOKING_NOT_DONE"))
    on_day = bool(res.candidate) and any(booking.slot_dict(s, clinic)["date"] == res.candidate.isoformat() for s in slots)
    date_options: list[str] = []
    if res.options:
        req.status = RequestStatus.NEEDS_CLARIFICATION
        question, key = res.question or "Which of these days do you mean?", "WHICH_DAY"
        date_options = [d.isoformat() for d in res.options]
    elif res.kind in ("VAGUE", "AMBIGUOUS") or not res.candidate:
        req.status = RequestStatus.NEEDS_CLARIFICATION
        question, key = res.question or "Which day suits you? Pick one of the available times below.", "PICK_DAY"
    elif on_day:
        question = f"You asked for {res.matched}. Is {day_label(res.candidate, '%A')} right? Pick a time to book it."
        key = "CONFIRM_DAY"
    else:
        question = f"No open slots on {day_label(res.candidate, '%A')}. These are the next available times."
        key = "NO_SLOTS_ON_DAY"
    return _act(Intent.RESCHEDULE_REQUEST, "AWAITING_SLOT_CHOICE", request_id=req.id, question=question,
                question_key=key, date_options=date_options,
                candidate_date=res.candidate.isoformat() if res.candidate else None, day_words=res.matched,
                slots=[booking.slot_dict(s, clinic) for s in slots])


def _clarify_action(db: Session, clinic: Clinic, patient: Patient, reply: PatientReply, guesses: list[Intent],
                    item) -> dict[str, Any]:
    recent = db.scalar(select(func.count()).select_from(PatientReply).where(
        PatientReply.patient_id == patient.id, PatientReply.status == ReplyStatus.NEEDS_CLARIFICATION,
        PatientReply.created_at > utcnow() - timedelta(hours=24), PatientReply.id != reply.id)) or 0
    if recent >= 1:  # second unclear message: a person takes over instead of another bot question
        task, _ = create_task(db, clinic=clinic, patient=patient, category=TaskCategory.UNCLEAR_INPUT,
                              queue=TaskQueue.RECEPTION, statement=reply.text or reply.transcript,
                              title="Patient message unclear twice — please call", dedupe_key=f"unclear:{patient.id}",
                              source_type="patient_reply", source_id=reply.id)
        return _act(Intent.OTHER_OR_UNCLEAR, "HANDED_TO_STAFF", task_id=task.id,
                    patient_text=_text(db, clinic, patient, "CALLBACK_ACK"))
    if reply.channel != Channel.PATIENT_APP:
        _send(db, clinic, patient, reply, "CLARIFY", MessageKind.CLARIFICATION)
    options = ["CONFIRM", "RESCHEDULE", "CALLBACK"]
    return _act(Intent.OTHER_OR_UNCLEAR, "AWAITING_CLARIFICATION",
                suggestions=[str(g) for g in guesses if g != Intent.OTHER_OR_UNCLEAR],
                question="Sorry, we are not sure what you need. Please choose one:", question_key="CLARIFY",
                options=options,
                due_date=item.due_date.isoformat() if item else None)


def _finish(db: Session, reply: PatientReply, actions: list[dict[str, Any]]) -> None:
    reply.actions = actions
    statuses = {a["status"] for a in actions}
    intents = {a["intent"] for a in actions}
    if Intent.URGENT_CONCERN in intents or "HANDED_TO_CLINICIAN" in statuses:
        reply.status = ReplyStatus.HUMAN_HANDOFF
    elif statuses & {"AWAITING_CONFIRMATION", "AWAITING_SLOT_CHOICE"}:
        reply.status = ReplyStatus.NEEDS_CONFIRMATION
    elif "AWAITING_CLARIFICATION" in statuses:
        reply.status = ReplyStatus.NEEDS_CLARIFICATION
    elif "HANDED_TO_STAFF" in statuses:
        reply.status = ReplyStatus.HUMAN_HANDOFF
    elif any(a.get("task_id") for a in actions):
        reply.status = ReplyStatus.ROUTED
    else:
        reply.status = ReplyStatus.ACTION_SUCCEEDED


# ------------------------------------------------------------------ follow-ups from the patient app
def confirm_opt_out(db: Session, clinic: Clinic, patient: Patient, reply: PatientReply, confirm: bool) -> None:
    acts = copy.deepcopy(reply.actions)  # new objects so the JSON column change is detected
    found = False
    for a in acts:
        if a["intent"] == Intent.OPT_OUT and a["status"] == "AWAITING_CONFIRMATION":
            found = True
            if confirm:
                patients.opt_out(db, clinic, patient, method="PATIENT_APP")
                a["status"], a["patient_text"] = "DONE", _text(db, clinic, patient, "OPT_OUT_CONFIRMED")
            else:
                a["status"] = "DECLINED"
    if not found:
        raise HTTPException(409, "Nothing is waiting for confirmation.")
    reply.actions = acts
    _refresh_status(reply)


def booking_outcome(db: Session, req: AppointmentRequest, result: booking.BookingResult) -> None:
    if not req.reply_id:
        return
    reply = db.get(PatientReply, req.reply_id)
    if reply is None:
        return
    acts = copy.deepcopy(reply.actions)  # new objects so the JSON column change is detected
    for a in acts:
        if a.get("request_id") == str(req.id):
            if result.booked:
                a["status"], a["appointment_id"] = "DONE", str(result.appointment.id)
                a["booking_reference"] = result.appointment.booking_reference
            elif result.reason == "PROVIDER_UNAVAILABLE":
                a["status"], a["task_id"] = "HANDED_TO_STAFF", str(result.task_id) if result.task_id else None
            else:
                a["status"], a["note"] = "AWAITING_SLOT_CHOICE", "That time was just taken. Please pick another."
    reply.actions = acts
    _refresh_status(reply)


def _refresh_status(reply: PatientReply) -> None:
    statuses = {a["status"] for a in reply.actions}
    if statuses & {"AWAITING_CONFIRMATION", "AWAITING_SLOT_CHOICE"}:
        reply.status = ReplyStatus.NEEDS_CONFIRMATION
    elif "HANDED_TO_STAFF" in statuses or "HANDED_TO_CLINICIAN" in statuses:
        reply.status = ReplyStatus.HUMAN_HANDOFF
    else:
        reply.status = ReplyStatus.ACTION_SUCCEEDED


def correct(db: Session, clinic: Clinic, patient: Patient, reply: PatientReply, new_text: str) -> PatientReply:
    """Patient corrects 'what I heard'. The original stays in history; a new reply is processed."""
    if reply.status not in (ReplyStatus.TRANSCRIPTION_FAILED, ReplyStatus.NEEDS_CLARIFICATION,
                            ReplyStatus.NEEDS_CONFIRMATION, ReplyStatus.CLASSIFIED, ReplyStatus.ROUTED,
                            ReplyStatus.ACTION_SUCCEEDED):
        raise HTTPException(409, "This message can no longer be corrected; send a new one.")
    new_text = (new_text or "").strip()
    if not new_text:
        raise HTTPException(422, "Type the corrected message.")
    reply.corrected_text = new_text[:2000]
    acts = [dict(a, status="SUPERSEDED") if a["status"] in ("AWAITING_SLOT_CHOICE", "AWAITING_CONFIRMATION",
                                                              "AWAITING_CLARIFICATION") else a for a in reply.actions]
    reply.actions = acts
    key = f"correct:{reply.id}:{hashlib.sha256(new_text.encode()).hexdigest()[:12]}"
    new, _ = ingest(db, clinic, patient, channel=reply.channel, mode=InputMode.TEXT, idempotency_key=key, text=new_text,
                    caregiver_grant_id=reply.caregiver_grant_id)
    timeline(db, clinic_id=clinic.id, patient_id=patient.id, event_type="TRANSCRIPT_CORRECTED",
             summary="Patient corrected what the system understood", provenance=Provenance.PATIENT_REPORTED,
             actor_type=ActorType.PATIENT, actor_label="Patient", patient_words=new_text[:500],
             source_type="patient_reply", source_id=new.id)
    return new
