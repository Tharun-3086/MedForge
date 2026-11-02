"""Simulated channel: the in-app 'demo phone'. Always labelled SIMULATED in the UI.

It behaves like a real provider: it returns a provider message id, and a moment later posts a *signed*
delivery-status webhook that goes through the same validation and dedupe path as WhatsApp would.
"""
from __future__ import annotations

from app.channels.base import ChannelError, SendResult
from app.models import OutboundMessage, Patient


class SimulatedChannel:
    name = "SIMULATED"

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def send(self, message: OutboundMessage, patient: Patient) -> SendResult:
        if self.fail:
            raise ChannelError("SIMULATED_PERMANENT_FAILURE", retriable=False,
                               detail="Demo fault injection: channel rejected the message")
        return SendResult(provider_message_id=f"sim-{message.id}", delivery_confirmation_supported=True)
