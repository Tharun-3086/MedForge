"""Messaging channel adapters. Workflow code only sees `send()` and `ChannelError`."""
from __future__ import annotations

from dataclasses import dataclass

from app.models import OutboundMessage, Patient


class ChannelError(Exception):
    def __init__(self, code: str, retriable: bool, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.retriable = retriable
        self.detail = detail[:300]


@dataclass
class SendResult:
    provider_message_id: str
    delivery_confirmation_supported: bool


def get_channel(name: str):
    if name == "SIMULATED":
        from app.channels.simulated import SimulatedChannel

        return SimulatedChannel()
    if name == "WHATSAPP":
        from app.channels.whatsapp import WhatsAppChannel

        return WhatsAppChannel()
    raise ChannelError("UNKNOWN_CHANNEL", retriable=False)


class Channel:
    name: str

    def send(self, message: OutboundMessage, patient: Patient) -> SendResult:  # pragma: no cover - interface
        raise NotImplementedError
