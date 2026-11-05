
"""Regression tests for multilingual simulated-phone staff responses."""
from __future__ import annotations

import uuid

from app.db import SessionLocal
from app.models import PatientReply
from tests.conftest import new_patient


def _send_simulated_message(client, *, name: str, phone: str, language: str, text: str):
    """Create a fresh patient and send one simulated incoming message."""
    pid = new_patient(
        client,
        name,
        phone,
        language=language,
        plan_days=None,
    )

    response = client.post(
        f"/v1/demo/phone/{pid}/reply",
        json={"text": text},
    )
    assert response.status_code == 200, response.text

    incoming = [
        message
        for message in response.json()["messages"]
        if message["direction"] == "in" and message["body"] == text
    ]
    assert len(incoming) == 1

    return pid, incoming[0]["id"]


def _get_thread_message(client, pid: str, reply_id: str) -> dict:
    response = client.get(f"/v1/demo/phone/{pid}")
    assert response.status_code == 200, response.text

    messages = response.json()["messages"]
    return next(message for message in messages if message["id"] == reply_id)


def test_simulated_phone_returns_original_message_and_english_gloss(nurse, seeded):
    original_text = "నేను ఈరోజు మందులు మర్చిపోయాను"
    english_gloss = "I forgot to take my medicines today."

    pid, reply_id = _send_simulated_message(
        nurse,
        name="English Gloss Regression",
        phone="+919000500101",
        language="te",
        text=original_text,
    )

    # Set the already-processed understanding to a deterministic test value.
    with SessionLocal() as db:
        reply = db.get(PatientReply, uuid.UUID(reply_id))
        assert reply is not None

        reply.understanding = {"english_gloss": english_gloss}
        reply.detected_language = "te-IN"
        reply.understanding_source = "LLM:sarvam"
        db.commit()

    message = _get_thread_message(nurse, pid, reply_id)

    assert message["direction"] == "in"
    assert message["body"] == original_text
    assert message["english_gloss"] == english_gloss
    assert message["patient_preferred_language"] == "te"
    assert message["detected_language"] == "te-IN"
    assert message["understanding_source"] == "LLM:sarvam"


def test_simulated_phone_returns_null_when_english_gloss_is_unavailable(nurse, seeded):
    original_text = "hmm ok maybe"

    pid, reply_id = _send_simulated_message(
        nurse,
        name="Missing Gloss Regression",
        phone="+919000500102",
        language="hi",
        text=original_text,
    )

    # Simulate a valid reply with no available English gloss.
    with SessionLocal() as db:
        reply = db.get(PatientReply, uuid.UUID(reply_id))
        assert reply is not None

        reply.understanding = {}
        reply.detected_language = None
        reply.understanding_source = "RULES"
        db.commit()

    message = _get_thread_message(nurse, pid, reply_id)

    assert message["body"] == original_text
    assert message["english_gloss"] is None
    assert message["patient_preferred_language"] == "hi"
    assert message["detected_language"] is None
    assert message["understanding_source"] == "RULES"
