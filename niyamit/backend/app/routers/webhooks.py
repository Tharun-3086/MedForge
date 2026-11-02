"""Inbound provider webhooks. Signatures are verified before anything is stored; events are deduplicated by
provider event id; processing happens after the event is safely recorded (PRD 7.3, 15)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.channels import whatsapp
from app.config import settings
from app.db import get_db
from app.security import client_ip, rate_limit
from app.services import inbound

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])
MAX_BODY = 256 * 1024


async def _body(request: Request) -> bytes:
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(413, "Payload too large.")
    return raw


@router.post("/simulated")
async def simulated(request: Request, db: Session = Depends(get_db)) -> dict:
    rate_limit(f"wh-sim:{client_ip(request)}", 300, 60)
    raw = await _body(request)
    result = inbound.handle_simulated(db, raw, request.headers.get("x-niyamit-signature"))
    db.commit()
    return result


@router.get("/whatsapp", response_class=PlainTextResponse)
def whatsapp_verify(mode: str = Query("", alias="hub.mode"), token: str = Query("", alias="hub.verify_token"),
                    challenge: str = Query("", alias="hub.challenge")) -> str:
    if not settings.whatsapp_verify_token or mode != "subscribe" or token != settings.whatsapp_verify_token:
        raise HTTPException(403, "Verification failed.")
    return challenge


@router.post("/whatsapp")
async def whatsapp_events(request: Request, db: Session = Depends(get_db)) -> dict:
    raw = await _body(request)
    if not whatsapp.verify_signature(raw, request.headers.get("x-hub-signature-256")):
        raise HTTPException(401, "Invalid signature.")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON.") from None
    events = [e for e in whatsapp.parse_webhook(payload) if e.get("event_id")]
    results = inbound.handle_whatsapp(db, events, payload)
    db.commit()
    return {"received": len(events), "results": results}
