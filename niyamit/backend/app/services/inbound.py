"""Inbound provider events (PRD 7.3): verify signature, store the event, dedupe by provider event id,
then process. Used by the WhatsApp webhook and the simulated channel (demo phone) alike."""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.context import correlation_id
from app.db import utcnow
from app.enums import Channel, InputMode
from app.models import Clinic, OutboundMessage, Patient, ProviderEvent
from app.services import messaging, replies


def sign_simulated(body: bytes) -> str:
    return "sha256=" + hmac.new(settings.simulated_webhook_secret, body, hashlib.sha256).hexdigest()


def verify_simulated(body: bytes, header: str | None) -> bool:
    return bool(header) and hmac.compare_digest(sign_simulated(body), header)


def store_event(db: Session, *, provider: str, event_id: str, event_type: str, payload: dict[str, Any],
                signature_valid: bool, clinic_id: uuid.UUID | None) -> tuple[ProviderEvent, bool]:
    """Returns (event, is_new). A repeated provider event id only bumps duplicate_count."""
    existing = db.scalar(select(ProviderEvent).where(ProviderEvent.provider == provider,
                                                     ProviderEvent.provider_event_id == event_id))
    if existing:
        existing.duplicate_count += 1
        return existing, False
    ev = ProviderEvent(provider=provider, provider_event_id=event_id, event_type=event_type, payload=payload,
                       signature_valid=signature_valid, clinic_id=clinic_id, correlation_id=correlation_id.get())
    try:
        with db.begin_nested():
            db.add(ev)
            db.flush()
    except IntegrityError:
        existing = db.scalar(select(ProviderEvent).where(ProviderEvent.provider == provider,
                                                         ProviderEvent.provider_event_id == event_id))
        existing.duplicate_count += 1
        return existing, False
    return ev, True


def handle_simulated(db: Session, raw: bytes, signature: str | None) -> dict[str, Any]:
    if not verify_simulated(raw, signature):
        raise HTTPException(401, "Invalid signature.")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON.") from None
    if not isinstance(payload, dict) or not payload.get("event_id") or len(raw) > 20_000:
        raise HTTPException(422, "Malformed event.")
    clinic_id = uuid.UUID(payload["clinic_id"]) if payload.get("clinic_id") else None
    ev, new = store_event(db, provider="SIMULATED", event_id=str(payload["event_id"])[:160],
                          event_type=payload.get("type", "INBOUND_MESSAGE"), payload=payload, signature_valid=True,
                          clinic_id=clinic_id)
    if not new:
        return {"status": "duplicate", "event": str(ev.id), "result_ref": ev.result_ref}
    return _process(db, ev, "SIMULATED")


def handle_whatsapp(db: Session, events: list[dict[str, Any]], raw_payload: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for e in events:
        ev, new = store_event(db, provider="WHATSAPP", event_id=e["event_id"][:160], event_type=e["type"],
                              payload=e, signature_valid=True, clinic_id=None)
        out.append({"status": "duplicate"} if not new else _process(db, ev, "WHATSAPP"))
    return out


def _process(db: Session, ev: ProviderEvent, provider: str) -> dict[str, Any]:
    p = ev.payload
    if ev.event_type == "DELIVERY_STATUS":
        result = messaging.apply_delivery_status(db, p.get("message_id", ""), p.get("status", ""), p.get("error_code"))
        ev.processing_status, ev.result_ref, ev.processed_at = "PROCESSED", result, utcnow()
        return {"status": "processed", "result": result}
    patient = _resolve_sender(db, p, ev.clinic_id)
    if patient is None:
        ev.processing_status, ev.processed_at = "UNRESOLVED_SENDER", utcnow()
        return {"status": "unresolved_sender"}
    clinic = db.get(Clinic, patient.clinic_id)
    ev.clinic_id = clinic.id
    audio = None
    mode = InputMode.BUTTON if p.get("button") else InputMode.TEXT
    if p.get("media_id") and provider == "WHATSAPP":
        from app.channels.whatsapp import download_media

        try:
            data, mime = download_media(p["media_id"])
            audio, mode = (data, f"voice{'.ogg' if 'ogg' in mime else '.m4a'}"), InputMode.VOICE
        except Exception:  # noqa: BLE001
            ev.processing_status = "MEDIA_DOWNLOAD_FAILED"
            return {"status": "media_failed"}
    reply, _ = replies.ingest(db, clinic, patient, channel=Channel(provider), mode=mode,
                              idempotency_key=f"{provider}:{ev.provider_event_id}", text=p.get("text"),
                              audio=audio, provider_event_id=ev.id)
    ev.processing_status, ev.result_ref, ev.processed_at = "STORED", str(reply.id), utcnow()
    return {"status": "accepted", "reply_id": str(reply.id)}


def _resolve_sender(db: Session, p: dict[str, Any], clinic_id: uuid.UUID | None) -> Patient | None:
    phone = "+" + "".join(ch for ch in str(p.get("from", "")) if ch.isdigit())
    q = select(Patient).where(Patient.phone_e164 == phone)
    if clinic_id:
        q = q.where(Patient.clinic_id == clinic_id)
    matches = db.scalars(q).all()
    return matches[0] if len(matches) == 1 else None  # ambiguous senders are never guessed


def simulate_delivery_callback(db: Session, message_id: uuid.UUID) -> None:
    """The simulated provider confirms delivery through the same signed webhook path."""
    m = db.get(OutboundMessage, message_id)
    if m is None or not m.provider_message_id:
        return
    body = json.dumps({"event_id": f"{m.provider_message_id}:delivered", "type": "DELIVERY_STATUS",
                       "message_id": m.provider_message_id, "status": "delivered",
                       "clinic_id": str(m.clinic_id)}).encode()
    handle_simulated(db, body, sign_simulated(body))


def demo_phone_reply(db: Session, patient: Patient, text: str, *, button: bool, event_id: str | None = None
                     ) -> tuple[dict[str, Any], str]:
    """Builds a provider-style signed event for the demo phone and sends it through the real webhook path."""
    event_id = event_id or f"sim-in-{uuid.uuid4().hex[:16]}"
    body = json.dumps({"event_id": event_id, "type": "INBOUND_MESSAGE", "from": patient.phone_e164,
                       "clinic_id": str(patient.clinic_id), "text": text[:1000], "button": button}).encode()
    return handle_simulated(db, body, sign_simulated(body)), event_id
