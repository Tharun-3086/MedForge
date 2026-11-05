"""Patient web app (Voice Bridge, slot picker, Care Passport) and the caregiver view.

Patients arrive through a magic link and confirm their year of birth before any health detail is shown.
Caregivers get only the scopes the patient granted, re-checked on every request."""
from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import serializers as S
from app.ai import pipeline
from app.ai.dates import resolve_day_expression
from app.ai.providers.base import ProviderError
from app.audit import audit
from app.config import settings
from app.db import get_db, utcnow
from app.enums import ActorType, CaregiverScope, ConsentPurpose, ConsentStatus, InputMode, ReplyStatus
from app.models import Appointment, AppointmentRequest, AvailabilitySlot, CaregiverGrant, Clinic, Patient, PatientReply, SourceArtifact, ExtractionProposal
from app.routers.intake import read_limited
from app.security import (
    CAREGIVER_COOKIE,
    PATIENT_COOKIE,
    CaregiverPrincipal,
    PatientPrincipal,
    client_ip,
    current_caregiver,
    current_patient,
    decode_session,
    hash_token,
    issue_session,
    rate_limit,
    set_cookie,
)
from app.services import booking, caregivers, guards, intake, patients, replies, views, patient_otp
from app.services.common import active_items, clinic_today, clinic_tz, current_item, first_name, slot_label
from app.services.replies import EXPLICIT

router = APIRouter(prefix="/v1/p", tags=["patient-app"])
caregiver_router = APIRouter(prefix="/v1/c", tags=["caregiver"])

CLIENT_KEY = re.compile(r"^[A-Za-z0-9-]{8,64}$")
PROCESSING = {ReplyStatus.RECEIVED, ReplyStatus.VALIDATED}


def _ctx(db: Session, me: PatientPrincipal) -> tuple[Patient, Clinic]:
    patient = db.get(Patient, me.patient_id)
    return patient, db.get(Clinic, patient.clinic_id)


def _key(patient_id: object, client_key: str) -> str:
    if not CLIENT_KEY.match(client_key or ""):
        raise HTTPException(422, "Invalid request key.")
    return f"app:{patient_id}:{client_key}"


def reply_view(r: PatientReply) -> dict:
    """What the patient sees: their words, what the system understood, and what happens next."""
    u = r.understanding or {}
    return {
        "id": str(r.id), "status": r.status, "processing": r.status in PROCESSING, "input_mode": r.input_mode,
        "text": r.text, "transcript": r.transcript, "corrected_text": r.corrected_text,
        "detected_language": r.detected_language, "error_code": r.error_code or None,
        "understood": {"intents": u.get("intents", []), "day_words": u.get("requested_day_text"),
                       "time_window": u.get("requested_time_window"), "barrier": u.get("barrier_category"),
                       "source": "BUTTON" if r.understanding_source == "BUTTON" else
                       ("AI" if r.understanding_source.startswith("LLM") else "RULES")},
        "actions": [{k: a.get(k) for k in ("intent", "label", "status", "patient_text", "question", "question_key",
                                            "slots", "request_id", "barrier", "booking_reference", "options", "note",
                                            "candidate_date", "day_words", "due_date", "date_options")
                     if a.get(k) is not None}
                    for a in (r.actions or [])],
        "can_correct": r.status in (ReplyStatus.TRANSCRIPTION_FAILED, ReplyStatus.NEEDS_CLARIFICATION,
                                    ReplyStatus.NEEDS_CONFIRMATION, ReplyStatus.CLASSIFIED, ReplyStatus.ROUTED,
                                    ReplyStatus.ACTION_SUCCEEDED) and r.input_mode != InputMode.BUTTON,
        "via_caregiver": bool(r.caregiver_grant_id), "created_at": S.iso(r.created_at),
    }


def _upcoming_appointments(db: Session, clinic: Clinic, patient_id) -> list[dict]:
    rows = db.execute(select(Appointment, AvailabilitySlot).join(AvailabilitySlot, AvailabilitySlot.id == Appointment.slot_id)
                      .where(Appointment.patient_id == patient_id, Appointment.status == "CONFIRMED",
                             AvailabilitySlot.starts_at > utcnow()).order_by(AvailabilitySlot.starts_at)).all()
    tz = clinic_tz(clinic)
    return [{"id": str(a.id), "reference": a.booking_reference, "starts_at": s.starts_at.isoformat(),
             "date": s.starts_at.astimezone(tz).date().isoformat(), "item_id": str(a.item_id) if a.item_id else None,
             "label": slot_label(s.starts_at.astimezone(tz)), "with": s.provider_label}
            for a, s in rows]


def home_payload(db: Session, patient: Patient, clinic: Clinic) -> dict:
    today = clinic_today(clinic)
    pending = db.scalar(select(PatientReply).where(
        PatientReply.patient_id == patient.id, PatientReply.caregiver_grant_id.is_(None),
        PatientReply.status.in_([ReplyStatus.NEEDS_CONFIRMATION, ReplyStatus.NEEDS_CLARIFICATION]),
        PatientReply.created_at > utcnow() - timedelta(days=7))
        .order_by(PatientReply.created_at.desc()).limit(1))
    return {
        "patient": {"first_name": first_name(patient), "language": patient.preferred_language,
                    "opted_out": patient.opted_out},
        "clinic": {"name": clinic.name, "short_name": clinic.short_name, "phone": clinic.phone},
        "items": [S.item_dict(i, today) for i in active_items(db, patient.id)],
        "appointments": _upcoming_appointments(db, clinic, patient.id),
        "pending": reply_view(pending) if pending else None,
        "consents": patients.consent_state(db, patient.id),
        "voice_available": pipeline.get_asr() is not None,
        "tts_available": pipeline.get_tts() is not None,
        "today": today.isoformat(),
    }


# ------------------------------------------------------------------ session
class OtpRequestIn(BaseModel):
    phone: str = Field(min_length=8, max_length=32)


class OtpVerifyIn(OtpRequestIn):
    challenge_id: uuid.UUID
    code: str = Field(pattern=r"^\d{6}$")


@router.get("/otp/config")
def otp_config():
    return {"available": patient_otp.available(), "development": patient_otp.available()}


@router.post("/otp/request")
def otp_request(body: OtpRequestIn, request: Request, db: Session = Depends(get_db)):
    rate_limit(f"otp-request:{client_ip(request)}", 10, 3600)
    rate_limit(f"otp-phone:{patient_otp.digest(patient_otp.phone_number(body.phone))}", 5, 3600)
    return patient_otp.request_code(db, body.phone)


@router.post("/otp/verify")
def otp_verify(body: OtpVerifyIn, request: Request, response: Response, db: Session = Depends(get_db)):
    rate_limit(f"otp-verify:{client_ip(request)}", 30, 300)
    matches = patient_otp.verify_code(db, body.phone, body.challenge_id, body.code)
    response.delete_cookie(PATIENT_COOKIE, path="/")
    response.delete_cookie("nyt_patient_choice", path="/")
    if not matches:
        return {"authenticated": False, "profiles": [], "message": "No synthetic clinic record is linked to this number. Ask your clinic to register the correct number."}
    if len(matches) == 1:
        p = matches[0]
        set_cookie(response, PATIENT_COOKIE, issue_session("patient", str(p.id), str(p.clinic_id)))
        audit(db, clinic_id=p.clinic_id, action="PATIENT_OTP_LOGIN", actor_type=ActorType.PATIENT,
              actor_id=str(p.id), patient_id=p.id, detail={"mode": "development"})
        db.commit()
        return {"authenticated": True}
    ticket = issue_session("patient-choice", "verified-phone", "", ids=[str(p.id) for p in matches],
                           exp=int((utcnow()+timedelta(minutes=5)).timestamp()))
    set_cookie(response, "nyt_patient_choice", ticket)
    return {"authenticated": False, "profiles": [{"id": str(p.id), "clinic": db.get(Clinic, p.clinic_id).name} for p in matches]}


class ProfileChoiceIn(BaseModel):
    patient_id: uuid.UUID


@router.post("/otp/select")
def otp_select(body: ProfileChoiceIn, request: Request, response: Response, db: Session = Depends(get_db)):
    patient_otp.guard()
    claims = decode_session(request.cookies.get("nyt_patient_choice", ""), "patient-choice")
    if str(body.patient_id) not in claims.get("ids", []):
        raise HTTPException(403, "This record is not linked to the verified number.")
    p = db.get(Patient, body.patient_id)
    if p is None or not p.is_synthetic:
        raise HTTPException(403, "Record is unavailable.")
    set_cookie(response, PATIENT_COOKIE, issue_session("patient", str(p.id), str(p.clinic_id)))
    response.delete_cookie("nyt_patient_choice", path="/")
    audit(db, clinic_id=p.clinic_id, action="PATIENT_OTP_LOGIN", actor_type=ActorType.PATIENT,
          actor_id=str(p.id), patient_id=p.id, detail={"mode": "development"})
    db.commit()
    return {"authenticated": True}


class LinkIn(BaseModel):
    token: str = Field(min_length=10, max_length=80)


class VerifyIn(LinkIn):
    birth_year: int | None = Field(default=None, ge=1900, le=2026)


@router.post("/link")
def link_info(body: LinkIn, request: Request, db: Session = Depends(get_db)) -> dict:
    """Before verification only the clinic name is revealed."""
    rate_limit(f"plink:{client_ip(request)}", 30, 60)
    rec, patient = patients.start_patient_session(db, body.token)
    clinic = db.get(Clinic, patient.clinic_id)
    already = False
    if request.cookies.get(PATIENT_COOKIE):  # this browser already verified as this same patient
        try:
            already = decode_session(request.cookies[PATIENT_COOKIE], "patient")["sub"] == str(patient.id)
        except HTTPException:
            already = False
    return {"clinic_name": clinic.name, "clinic_short_name": clinic.short_name,
            "require_verification": clinic.require_patient_verification,
            "language": patient.preferred_language, "already_verified": already}


@router.post("/verify")
def verify(body: VerifyIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    rate_limit(f"pverify:{client_ip(request)}", 10, 60)
    rec, patient = patients.start_patient_session(db, body.token)
    clinic = db.get(Clinic, patient.clinic_id)
    patients.verify_birth_year(db, rec, patient, body.birth_year, clinic)
    set_cookie(response, PATIENT_COOKIE, issue_session("patient", str(patient.id), str(clinic.id)))
    db.commit()
    return home_payload(db, patient, clinic)


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(PATIENT_COOKIE, path="/")
    response.delete_cookie("nyt_patient_choice", path="/")
    return {"ok": True}


@router.get("/home")
def home(me: PatientPrincipal = Depends(current_patient), db: Session = Depends(get_db)) -> dict:
    patient, clinic = _ctx(db, me)
    return home_payload(db, patient, clinic)


class ProfileIn(BaseModel):
    preferred_language: Literal["en", "hi", "te"]


@router.patch("/profile")
def update_profile(body: ProfileIn, me: PatientPrincipal = Depends(current_patient), db: Session = Depends(get_db)) -> dict:
    patient, clinic = _ctx(db, me)
    patient.preferred_language = body.preferred_language
    audit(db, clinic_id=clinic.id, action="PATIENT_LANGUAGE_CHANGED", actor_type=ActorType.PATIENT,
          actor_id=str(patient.id), patient_id=patient.id, detail={"language": body.preferred_language})
    db.commit()
    return home_payload(db, patient, clinic)


class PatientConsentIn(BaseModel):
    purpose: Literal["REMINDERS", "AI_PROCESSING"]
    granted: bool


@router.post("/consents")
def patient_consent(body: PatientConsentIn, me: PatientPrincipal = Depends(current_patient),
                    db: Session = Depends(get_db)) -> dict:
    patient, clinic = _ctx(db, me)
    patients.record_consent(db, patient, ConsentPurpose(body.purpose),
                            ConsentStatus.GRANTED if body.granted else ConsentStatus.WITHDRAWN, method="PATIENT_APP")
    db.commit()
    return {"consents": patients.consent_state(db, patient.id)}


# ------------------------------------------------------------------ Voice Bridge
class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    client_key: str


class ButtonIn(BaseModel):
    choice: str = Field(max_length=40)
    client_key: str


def _ingest_and_view(db: Session, reply: PatientReply) -> dict:
    db.commit()  # processing starts after commit (inline in eager mode, otherwise on the worker)
    db.refresh(reply)
    return reply_view(reply)


@router.post("/replies")
def send_text(body: TextIn, me: PatientPrincipal = Depends(current_patient), db: Session = Depends(get_db)) -> dict:
    rate_limit(f"preply:{me.patient_id}", 20, 60)
    patient, clinic = _ctx(db, me)
    reply, _ = replies.ingest(db, clinic, patient, channel="PATIENT_APP", mode=InputMode.TEXT,
                              idempotency_key=_key(patient.id, body.client_key), text=body.text)
    return _ingest_and_view(db, reply)


@router.post("/replies/button")
def send_button(body: ButtonIn, me: PatientPrincipal = Depends(current_patient), db: Session = Depends(get_db)) -> dict:
    rate_limit(f"preply:{me.patient_id}", 20, 60)
    if body.choice.upper() not in EXPLICIT:
        raise HTTPException(422, "Unknown choice.")
    patient, clinic = _ctx(db, me)
    reply, _ = replies.ingest(db, clinic, patient, channel="PATIENT_APP", mode=InputMode.BUTTON,
                              idempotency_key=_key(patient.id, body.client_key), text=body.choice.upper())
    return _ingest_and_view(db, reply)


@router.post("/replies/voice")
async def send_voice(audio: UploadFile = File(...), client_key: str = Form(...),
                     me: PatientPrincipal = Depends(current_patient), db: Session = Depends(get_db)) -> dict:
    rate_limit(f"preply:{me.patient_id}", 20, 60)
    patient, clinic = _ctx(db, me)
    data = await read_limited(audio, settings.max_audio_mb)
    reply, _ = replies.ingest(db, clinic, patient, channel="PATIENT_APP", mode=InputMode.VOICE,
                              idempotency_key=_key(patient.id, client_key), audio=(data, audio.filename or "voice.webm"))
    return _ingest_and_view(db, reply)


@router.get("/replies/{reply_id}")
def get_reply(reply_id: str, me: PatientPrincipal = Depends(current_patient), db: Session = Depends(get_db)) -> dict:
    return reply_view(guards.own_reply(db, me, reply_id))


class CorrectIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


@router.post("/replies/{reply_id}/correct")
def correct_reply(reply_id: str, body: CorrectIn, me: PatientPrincipal = Depends(current_patient),
                  db: Session = Depends(get_db)) -> dict:
    patient, clinic = _ctx(db, me)
    new = replies.correct(db, clinic, patient, guards.own_reply(db, me, reply_id), body.text)
    return _ingest_and_view(db, new)


class OptOutConfirmIn(BaseModel):
    confirm: bool


@router.post("/replies/{reply_id}/opt-out")
def confirm_opt_out(reply_id: str, body: OptOutConfirmIn, me: PatientPrincipal = Depends(current_patient),
                    db: Session = Depends(get_db)) -> dict:
    patient, clinic = _ctx(db, me)
    reply = guards.own_reply(db, me, reply_id)
    replies.confirm_opt_out(db, clinic, patient, reply, body.confirm)
    db.commit()
    return reply_view(reply)


@router.get("/replies/{reply_id}/audio")
def reply_audio(reply_id: str, i: int = Query(0, ge=0, le=10), me: PatientPrincipal = Depends(current_patient),
                db: Session = Depends(get_db)) -> Response:
    """Read the system's reply aloud (Sarvam text-to-speech). Only server-generated text can be spoken."""
    rate_limit(f"ptts:{me.patient_id}", 15, 60)
    patient, _ = _ctx(db, me)
    reply = guards.own_reply(db, me, reply_id)
    acts = reply.actions or []
    if i >= len(acts):
        raise HTTPException(404, "Nothing to read.")
    text = acts[i].get("patient_text") or acts[i].get("question")
    tts = pipeline.get_tts()
    if not text or tts is None:
        raise HTTPException(503, "Voice playback is not available.")
    try:
        audio = tts.synthesize(text, patient.preferred_language)
    except ProviderError as exc:
        raise HTTPException(503, f"Voice playback failed ({exc.code}).") from None
    return Response(audio, media_type="audio/wav", headers={"Cache-Control": "private, max-age=600"})


# ------------------------------------------------------------------ booking
@router.get("/slots")
def slots(day: str | None = Query(None, alias="date"), window: str | None = None,
          me: PatientPrincipal = Depends(current_patient), db: Session = Depends(get_db)) -> dict:
    _, clinic = _ctx(db, me)
    try:
        d = date.fromisoformat(day) if day else None
    except ValueError:
        raise HTTPException(422, "Invalid date.") from None
    try:
        rows = booking.list_slots(db, clinic, day=d, window=window, limit=24, lead=booking.PATIENT_LEAD)
    except booking.BookingUnavailable:
        raise HTTPException(503, "Booking is not available right now. You can ask for a call back.") from None
    return {"slots": [booking.slot_dict(s, clinic) for s in rows]}


class PatientBookIn(BaseModel):
    slot_id: str
    request_id: str | None = None
    client_key: str


def _booking_response(db: Session, clinic: Clinic, req: AppointmentRequest | None, result: booking.BookingResult) -> dict:
    out: dict = {"booked": result.booked, "reason": result.reason}
    if result.booked and result.appointment:
        slot = db.get(AvailabilitySlot, result.appointment.slot_id)
        sd = booking.slot_dict(slot, clinic)
        out["appointment"] = {"reference": result.appointment.booking_reference, "label": sd["label"],
                              "starts_at": sd["starts_at"], "date": sd["date"], "with": slot.provider_label}
    out["request"] = S.request_dict(req) if req else None
    return out


@router.post("/book")
def book(body: PatientBookIn, me: PatientPrincipal = Depends(current_patient), db: Session = Depends(get_db)) -> dict:
    rate_limit(f"pbook:{me.patient_id}", 10, 60)
    patient, clinic = _ctx(db, me)
    req = guards.own_request(db, patient.id, body.request_id)
    if req is None:
        req = booking.create_request(db, clinic, patient, item=current_item(db, patient.id), reply_id=None,
                                     requested_by="PATIENT", day_text=None, requested=None, window=None, statement=None)
    slot_id = guards._uuid(body.slot_id)
    if slot_id is None:
        raise HTTPException(422, "Unknown slot.")
    result = booking.commit_booking(db, clinic, patient, slot_id=slot_id, request_id=req.id,
                                    idempotency_key=_key(patient.id, body.client_key), created_by="PATIENT")
    replies.booking_outcome(db, req, result)
    db.commit()
    return _booking_response(db, clinic, req, result)


# ------------------------------------------------------------------ passport, documents, caregivers
@router.get("/passport")
def passport(me: PatientPrincipal = Depends(current_patient), db: Session = Depends(get_db)) -> dict:
    patient, clinic = _ctx(db, me)
    return {**views.care_passport(db, clinic, patient), "caregivers": caregivers.grants_for(db, patient.id)}


@router.post("/documents", status_code=201)
async def upload_document(file: UploadFile = File(...),
                          source_type: Literal["PRESCRIPTION", "LAB_REPORT", "OTHER"] = Form("LAB_REPORT"),
                          me: PatientPrincipal = Depends(current_patient), db: Session = Depends(get_db)) -> dict:
    rate_limit(f"pdoc:{me.patient_id}", 10, 3600)
    patient, clinic = _ctx(db, me)
    data = await read_limited(file, settings.max_upload_mb)
    artifact, _ = intake.upload(db, clinic, patient, data, file.filename or "report", source_type, by_patient=True)
    db.commit()
    return {"filename": artifact.filename, "status": "Received — the clinic team will review it.",
            "uploaded_at": S.iso(artifact.created_at)}


@router.get("/documents")
def patient_documents(me: PatientPrincipal = Depends(current_patient), db: Session = Depends(get_db)):
    rows = db.execute(select(SourceArtifact, ExtractionProposal).outerjoin(ExtractionProposal,
        (ExtractionProposal.artifact_id == SourceArtifact.id) & (ExtractionProposal.patient_id == me.patient_id)
        & (ExtractionProposal.clinic_id == me.clinic_id)).where(
        SourceArtifact.patient_id == me.patient_id, SourceArtifact.clinic_id == me.clinic_id,
        SourceArtifact.source_type != "VOICE_NOTE", SourceArtifact.deleted_at.is_(None))
        .order_by(SourceArtifact.created_at.desc()).limit(10)).all()
    return {"documents": [{"id": str(a.id), "filename": a.filename, "uploaded_at": S.iso(a.created_at),
        "status": p.status if p else "RECEIVED", "ocr_provider": p.ocr_provider if p else "",
        "automatic_fields": [{"label": S.FIELD_LABELS.get(f.name, f.name), "value": f.proposed_value,
                              "as_written": f.extracted_value, "review_status": f.status} for f in p.fields] if p else [],
        "automatic_text": "\n".join(str(b.get("text", "")) for b in (p.blocks or []))[:30000] if p else "",
        "clinic_reviewed_fields": [{"label": S.FIELD_LABELS.get(f.name, f.name), "value": f.value,
                                    "reviewed_at": S.iso(f.reviewed_at)} for f in p.fields if f.status == "APPROVED"] if p else [],
        "plan_approved": bool(p and p.status == "APPROVED" and p.plan_id)} for a, p in rows]}


@router.get("/documents/{artifact_id}/file")
def patient_document_file(artifact_id: uuid.UUID, me: PatientPrincipal = Depends(current_patient), db: Session = Depends(get_db)):
    from app import storage
    a = db.scalar(select(SourceArtifact).where(SourceArtifact.id == artifact_id,
        SourceArtifact.patient_id == me.patient_id, SourceArtifact.clinic_id == me.clinic_id,
        SourceArtifact.source_type != "VOICE_NOTE", SourceArtifact.deleted_at.is_(None)))
    if a is None:
        raise HTTPException(404, "Document not found.")
    try:
        data = storage.load(a.storage_key)
    except storage.StorageUnavailable:
        raise HTTPException(503, "Original document is temporarily unavailable.") from None
    return Response(data, media_type=a.mime_type, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": 'inline; filename="document.' + ('pdf' if a.mime_type == 'application/pdf' else 'png' if a.mime_type == 'image/png' else 'jpg') + '"'})


class CaregiverIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(max_length=32)
    scopes: list[str] = Field(min_length=1, max_length=3)


@router.get("/caregivers")
def list_caregivers(me: PatientPrincipal = Depends(current_patient), db: Session = Depends(get_db)) -> dict:
    return {"caregivers": caregivers.grants_for(db, me.patient_id), "scopes": {
        k.value: v for k, v in caregivers.SCOPE_LABELS.items()}}


@router.post("/caregivers", status_code=201)
def invite_caregiver(body: CaregiverIn, me: PatientPrincipal = Depends(current_patient),
                     db: Session = Depends(get_db)) -> dict:
    rate_limit(f"pcare:{me.patient_id}", 5, 3600)
    patient, clinic = _ctx(db, me)
    grant, link = caregivers.invite(db, clinic, patient, body.name, body.phone, body.scopes)
    db.commit()
    return {"id": str(grant.id), "link": link,
            "note": "Share this link with your caregiver yourself. You can remove access at any time."}


@router.delete("/caregivers/{grant_id}")
def revoke_caregiver(grant_id: str, me: PatientPrincipal = Depends(current_patient), db: Session = Depends(get_db)) -> dict:
    patient, _ = _ctx(db, me)
    gid = guards._uuid(grant_id)
    if gid is None:
        raise HTTPException(404, "Access not found.")
    caregivers.revoke(db, patient, gid)
    db.commit()
    return {"caregivers": caregivers.grants_for(db, patient.id)}


# ================================================================== caregiver view
def _grant_ctx(db: Session, me: CaregiverPrincipal) -> tuple[Patient, Clinic]:
    patient = db.get(Patient, me.patient_id)
    return patient, db.get(Clinic, patient.clinic_id)


def _need(me: CaregiverPrincipal, scope: CaregiverScope) -> None:
    if scope.value not in me.scopes:
        raise HTTPException(403, "The patient has not given you this permission.")


@caregiver_router.post("/session")
def caregiver_session(body: LinkIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    rate_limit(f"clink:{client_ip(request)}", 20, 60)
    grant = db.scalar(select(CaregiverGrant).where(CaregiverGrant.token_hash == hash_token(body.token)))
    if grant is None or grant.status != "ACTIVE" or grant.expires_at < utcnow():
        raise HTTPException(401, "This caregiver link is no longer valid. Ask the patient for a new one.")
    set_cookie(response, CAREGIVER_COOKIE, issue_session("caregiver", str(grant.id), str(grant.clinic_id)))
    audit(db, clinic_id=grant.clinic_id, action="CAREGIVER_SESSION_STARTED", actor_type=ActorType.CAREGIVER,
          actor_id=str(grant.id), object_type="caregiver_grant", object_id=grant.id, patient_id=grant.patient_id)
    db.commit()
    me = CaregiverPrincipal(grant.id, grant.patient_id, grant.clinic_id, list(grant.scopes), grant.caregiver_name)
    return caregiver_home(me, db)


@caregiver_router.post("/logout")
def caregiver_logout(response: Response) -> dict:
    response.delete_cookie(CAREGIVER_COOKIE, path="/")
    return {"ok": True}


@caregiver_router.get("/home")
def caregiver_home(me: CaregiverPrincipal = Depends(current_caregiver), db: Session = Depends(get_db)) -> dict:
    patient, clinic = _grant_ctx(db, me)
    today = clinic_today(clinic)
    view = CaregiverScope.VIEW_APPOINTMENTS.value in me.scopes
    audit(db, clinic_id=clinic.id, action="CAREGIVER_VIEW", actor_type=ActorType.CAREGIVER, actor_id=str(me.grant_id),
          object_type="patient", object_id=patient.id, patient_id=patient.id)
    db.commit()
    return {"caregiver_name": me.name, "patient_first_name": first_name(patient),
            "clinic": {"name": clinic.name, "short_name": clinic.short_name, "phone": clinic.phone},
            "scopes": me.scopes, "today": today.isoformat(),
            "scope_labels": [caregivers.SCOPE_LABELS[CaregiverScope(s)] for s in me.scopes],
            "items": [S.item_dict(i, today) for i in active_items(db, patient.id)] if view else None,
            "appointments": _upcoming_appointments(db, clinic, patient.id) if view else None,
            "can_request_reschedule": CaregiverScope.REQUEST_RESCHEDULE.value in me.scopes,
            "language": patient.preferred_language}


class CaregiverRescheduleIn(BaseModel):
    day_text: str = Field(default="", max_length=80)
    window: Literal["MORNING", "AFTERNOON", "EVENING"] | None = None
    note: str = Field(default="", max_length=500)


@caregiver_router.post("/reschedule")
def caregiver_reschedule(body: CaregiverRescheduleIn, me: CaregiverPrincipal = Depends(current_caregiver),
                         db: Session = Depends(get_db)) -> dict:
    _need(me, CaregiverScope.REQUEST_RESCHEDULE)
    rate_limit(f"creq:{me.grant_id}", 10, 3600)
    patient, clinic = _grant_ctx(db, me)
    res = resolve_day_expression(body.day_text, clinic_today(clinic)) if body.day_text.strip() else None
    req = booking.create_request(db, clinic, patient, item=current_item(db, patient.id), reply_id=None,
                                 requested_by="CAREGIVER", day_text=body.day_text.strip() or None,
                                 requested=res.candidate if res else None, window=body.window,
                                 statement=(f"Caregiver {me.name}: " + (body.note or body.day_text or "asked for a new time"))[:500])
    offered = booking.offer_slots(db, clinic, req, day=res.candidate if res else None, days=res.options if res else None)
    db.commit()
    return {"request": S.request_dict(req), "slots": [booking.slot_dict(s, clinic) for s in offered],
            "question": res.question if res and res.question else None}


class CaregiverBookIn(BaseModel):
    slot_id: str
    request_id: str


@caregiver_router.post("/book")
def caregiver_book(body: CaregiverBookIn, me: CaregiverPrincipal = Depends(current_caregiver),
                   db: Session = Depends(get_db)) -> dict:
    _need(me, CaregiverScope.REQUEST_RESCHEDULE)
    patient, clinic = _grant_ctx(db, me)
    req = guards.own_request(db, patient.id, body.request_id)
    slot_id = guards._uuid(body.slot_id)
    if slot_id is None:
        raise HTTPException(422, "Unknown slot.")
    result = booking.commit_booking(db, clinic, patient, slot_id=slot_id, request_id=req.id,
                                    idempotency_key=f"cg:{me.grant_id}:{req.id}:{slot_id}", created_by="CAREGIVER")
    db.commit()
    return _booking_response(db, clinic, req, result)
