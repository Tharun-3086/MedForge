"""WhatsApp Cloud API adapter (optional real channel; switched on with WHATSAPP_* settings).

Business-initiated reminders must use a Meta-approved template (WHATSAPP_REMINDER_TEMPLATE). Replies inside
the 24-hour customer window can be plain text. Inbound webhooks are verified with X-Hub-Signature-256.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any

import httpx

from app.channels.base import ChannelError, SendResult
from app.config import settings
from app.enums import MessageKind
from app.models import OutboundMessage, Patient

TEMPLATE_KINDS = {MessageKind.REMINDER_PRE_DUE, MessageKind.REMINDER_DUE, MessageKind.REMINDER_OVERDUE,
                  MessageKind.REMINDER_MANUAL}


class WhatsAppChannel:
    name = "WHATSAPP"

    def send(self, message: OutboundMessage, patient: Patient) -> SendResult:
        if not (settings.whatsapp_enabled and settings.whatsapp_access_token and settings.whatsapp_phone_number_id):
            raise ChannelError("WHATSAPP_NOT_CONFIGURED", retriable=False)
        to = re.sub(r"\D", "", patient.phone_e164)
        if message.kind in TEMPLATE_KINDS and settings.whatsapp_reminder_template:
            body: dict[str, Any] = {
                "messaging_product": "whatsapp", "to": to, "type": "template",
                "template": {"name": settings.whatsapp_reminder_template,
                             "language": {"code": {"hi": "hi", "te": "te"}.get(message.language, "en")},
                             "components": [{"type": "body", "parameters": [
                                 {"type": "text", "text": (patient.display_name or "").split()[0] or "there"}]}]},
            }
        else:
            body = {"messaging_product": "whatsapp", "to": to, "type": "text",
                    "text": {"preview_url": False, "body": message.body[:4000]}}
        url = f"https://graph.facebook.com/{settings.whatsapp_graph_version}/{settings.whatsapp_phone_number_id}/messages"
        try:
            resp = httpx.post(url, json=body, timeout=15,
                              headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"})
        except httpx.TimeoutException:
            raise ChannelError("WHATSAPP_TIMEOUT", retriable=True) from None
        except httpx.HTTPError as exc:
            raise ChannelError("WHATSAPP_NETWORK", retriable=True, detail=type(exc).__name__) from None
        if resp.status_code >= 400:
            retriable = resp.status_code == 429 or resp.status_code >= 500
            code = "WHATSAPP_HTTP_" + str(resp.status_code)
            try:
                code = f"WHATSAPP_{resp.json()['error'].get('code', resp.status_code)}"
            except Exception:  # noqa: BLE001
                pass
            raise ChannelError(code, retriable=retriable)
        msgs = resp.json().get("messages") or [{}]
        return SendResult(provider_message_id=msgs[0].get("id", ""), delivery_confirmation_supported=True)


def verify_signature(raw_body: bytes, header: str | None) -> bool:
    if not settings.whatsapp_app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(settings.whatsapp_app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])


def parse_webhook(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a Meta webhook into inbound-message and status events with stable ids for dedupe."""
    events: list[dict[str, Any]] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for m in value.get("messages", []) or []:
                ev = {"type": "INBOUND_MESSAGE", "event_id": m.get("id", ""), "from": m.get("from", ""),
                      "kind": m.get("type")}
                if m.get("type") == "text":
                    ev["text"] = m.get("text", {}).get("body", "")
                elif m.get("type") == "button":
                    ev["text"] = m.get("button", {}).get("payload") or m.get("button", {}).get("text", "")
                    ev["button"] = True
                elif m.get("type") == "interactive":
                    inter = m.get("interactive", {})
                    reply = inter.get("button_reply") or inter.get("list_reply") or {}
                    ev["text"], ev["button"] = reply.get("id") or reply.get("title", ""), True
                elif m.get("type") == "audio":
                    ev["media_id"] = m.get("audio", {}).get("id")
                events.append(ev)
            for s in value.get("statuses", []) or []:
                events.append({"type": "DELIVERY_STATUS", "event_id": f"{s.get('id')}:{s.get('status')}",
                               "message_id": s.get("id"), "status": s.get("status"),
                               "error_code": (s.get("errors") or [{}])[0].get("code")})
    return events


def download_media(media_id: str) -> tuple[bytes, str]:
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    meta = httpx.get(f"https://graph.facebook.com/{settings.whatsapp_graph_version}/{media_id}", headers=headers, timeout=15)
    meta.raise_for_status()
    info = meta.json()
    media = httpx.get(info["url"], headers=headers, timeout=30)
    media.raise_for_status()
    return media.content, info.get("mime_type", "audio/ogg").split(";")[0]
