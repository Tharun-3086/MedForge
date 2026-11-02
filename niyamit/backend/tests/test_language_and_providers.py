"""Language understanding (offline rules, date words) and the provider adapters, tested without network:
provider HTTP calls go to a mock transport, so no API key is ever used."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from app.ai import pipeline, rules
from app.ai.dates import parse_explicit_date, parse_interval, resolve_day_expression
from app.ai.providers import sarvam
from app.ai.providers.base import ProviderError, parse_json_content
from app.config import settings
from app.enums import Intent

TODAY = date(2026, 10, 29)  # a Thursday
SAMPLES = Path(__file__).resolve().parents[1] / "samples"


# ------------------------------------------------------------------ day words (deterministic, never guessed)
@pytest.mark.parametrize("text,kind,expected", [
    ("Doctor, Monday nahi aa sakta. Saturday slot unda?", "WEEKDAY", date(2026, 10, 31)),
    ("not Monday, Saturday", "WEEKDAY", date(2026, 10, 31)),
    ("Monday kaadu, Saturday", "WEEKDAY", date(2026, 10, 31)),
    ("శనివారం స్లాట్ ఉందా? సోమవారం రాలేను", "WEEKDAY", date(2026, 10, 31)),  # Telugu script, negated Monday
    ("शनिवार को आऊँगा, सोमवार नहीं", "WEEKDAY", date(2026, 10, 31)),
    ("repu vastanu", "RELATIVE", date(2026, 10, 30)),
    ("ellundi", "RELATIVE", date(2026, 10, 31)),
    ("Haan, main 12 tareekh ko aa jaunga", "EXPLICIT", date(2026, 11, 12)),
    ("on 05/11/2026 please", "EXPLICIT", date(2026, 11, 5)),
    ("kal aaunga", "AMBIGUOUS", None),  # Hindi 'kal' is both yesterday and tomorrow
    ("next week", "VAGUE", None),
    ("Monday raalenu", "VAGUE", None),  # only a negated day: ask which day
    ("Please call me back after 6pm", "NONE", None),
])
def test_day_resolution(text, kind, expected):
    res = resolve_day_expression(text, TODAY)
    assert res.kind == kind and res.candidate == expected
    if kind in ("VAGUE", "AMBIGUOUS"):
        assert res.question


@pytest.mark.parametrize("text,kind,expected,options", [
    # Thursday 29 Oct: the coming Saturday is in this week, so "next Saturday" could mean 31 Oct or 7 Nov -> ask.
    ("Next Saturday possible?", "AMBIGUOUS", None, [date(2026, 10, 31), date(2026, 11, 7)]),
    ("agle shanivar aaunga", "AMBIGUOUS", None, [date(2026, 10, 31), date(2026, 11, 7)]),
    ("వచ్చే శనివారం వస్తాను", "AMBIGUOUS", None, [date(2026, 10, 31), date(2026, 11, 7)]),
    # The coming Monday is already next week: "next Monday" is unambiguous.
    ("next monday", "WEEKDAY", date(2026, 11, 2), []),
    ("not next saturday, sunday is fine", "WEEKDAY", date(2026, 11, 1), []),
])
def test_next_weekday_is_asked_when_it_could_mean_two_dates(text, kind, expected, options):
    res = resolve_day_expression(text, TODAY)
    assert (res.kind, res.candidate, res.options) == (kind, expected, options)
    if options:
        assert "31 Oct" in res.question and "7 Nov" in res.question


def test_document_dates_and_intervals():
    assert parse_explicit_date("Review on 14/01/2027", TODAY) == date(2027, 1, 14)
    assert parse_explicit_date("next visit 3 months", TODAY, allow_missing_year=False) is None
    assert parse_interval("Review after 3 months") is not None
    assert parse_interval("after 2 weeks") is not None


# ------------------------------------------------------------------ offline rules (fallback when no AI key)
@pytest.mark.parametrize("text,intents", [
    ("Avunu doctor, vastanu", ["CONFIRM_FOLLOWUP"]),
    ("Monday nahi aa sakta. Saturday slot unda? HbA1c report kuda upload chestha",
     ["RESCHEDULE_REQUEST", "REPORT_UPLOAD_INTENT"]),
    ("Paise nahi hain abhi", ["BARRIER_REPORTED"]),
    ("Should I double my insulin dose?", ["CLINICAL_QUESTION"]),
    ("Chest lo noppi ga undi", ["URGENT_CONCERN"]),
    ("Inka messages pampakandi", ["OPT_OUT"]),
    ("Please call me back", ["CALLBACK_REQUEST"]),
    ("Who is this?", ["OTHER_OR_UNCLEAR"]),
    ("hmm ok maybe later", ["OTHER_OR_UNCLEAR"]),  # a hedged 'ok' is not a confirmation
])
def test_rules_classifier(text, intents):
    u = pipeline.understand_reply(text, today=TODAY, provider="rules").understanding
    assert sorted(i.value for i in u.intents) == sorted(intents)


def test_unclear_and_hedged_messages_ask_instead_of_acting():
    for text in ("Who is this?", "hmm ok maybe"):
        u = pipeline.understand_reply(text, today=TODAY, provider="rules").understanding
        assert u.needs_clarification and u.confidence < settings.clarify_confidence_threshold


def test_safety_intents_survive_low_confidence():
    u = pipeline.understand_reply("sugar chala takkuva ga undi, chemata", today=TODAY, provider="rules").understanding
    assert Intent.URGENT_CONCERN in u.intents and u.urgent_concern_present


# ------------------------------------------------------------------ AI output is validated server-side
class FakeLLM:
    name, model = "fake", "fake-1"

    def __init__(self, out):
        self.out = out

    def json_completion(self, *args, **kwargs):
        if isinstance(self.out, Exception):
            raise self.out
        return self.out


def _llm_reply(**overrides):
    base = {"intents": ["RESCHEDULE_REQUEST"], "requested_date": None, "requested_day_text": "Saturday",
            "requested_time_window": None, "barrier_category": None, "clinical_question_present": False,
            "urgent_concern_present": False, "opt_out_present": False, "source_text": "Saturday slot unda",
            "english_gloss": "Is there a Saturday slot?", "confidence": 0.9, "needs_clarification": False,
            "clarification_reason": None}
    return base | overrides


def test_llm_output_is_policy_checked(monkeypatch):
    text = "Monday nahi aa sakta. Saturday slot unda?"
    monkeypatch.setattr(pipeline, "get_llm", lambda name=None: FakeLLM(_llm_reply(requested_date="2026-11-02")))
    res = pipeline.understand_reply(text, today=TODAY)
    assert res.source == "LLM:fake:fake-1"
    assert res.understanding.requested_date is None  # a date the patient never wrote is dropped
    assert any("calendar date" in n for n in res.notes)

    monkeypatch.setattr(pipeline, "get_llm", lambda name=None: FakeLLM(_llm_reply(source_text="I want a refund")))
    res = pipeline.understand_reply(text, today=TODAY)
    assert res.understanding.confidence <= 0.5 and res.understanding.needs_clarification  # invented quote


def test_llm_schema_violation_and_outage_fall_back_to_rules(monkeypatch):
    text = "Monday nahi aa sakta. Saturday slot unda?"
    monkeypatch.setattr(pipeline, "get_llm", lambda name=None: FakeLLM(_llm_reply(intents=["BOOK_ANYTHING"])))
    res = pipeline.understand_reply(text, today=TODAY)
    assert res.source == "RULES" and any("outside the allowed schema" in n for n in res.notes)
    monkeypatch.setattr(pipeline, "get_llm", lambda name=None: FakeLLM(ProviderError("fake", "TIMEOUT")))
    res = pipeline.understand_reply(text, today=TODAY)
    assert res.source == "RULES" and Intent.RESCHEDULE_REQUEST in res.understanding.intents


def test_clinical_flag_from_the_model_always_routes_to_a_human(monkeypatch):
    out = _llm_reply(intents=["CONFIRM_FOLLOWUP"], clinical_question_present=True, requested_day_text=None,
                     source_text="")
    monkeypatch.setattr(pipeline, "get_llm", lambda name=None: FakeLLM(out))
    u = pipeline.understand_reply("vastanu, kaani tablet maarchala?", today=TODAY).understanding
    assert Intent.CLINICAL_QUESTION in u.intents


def test_parse_json_content_tolerates_fences_and_think_tags():
    assert parse_json_content('<think>hmm</think>```json\n{"a": 1}\n```', "x") == {"a": 1}
    with pytest.raises(ProviderError):
        parse_json_content("no json here", "x")


# ------------------------------------------------------------------ documents (local OCR + rules)
def test_prompt_injection_document_is_treated_as_data():
    data = (SAMPLES / "prompt_injection.png").read_bytes()
    res = pipeline.extract_document(data, "image/png", "x.png", today=TODAY)
    assert any("instruction-like" in n for n in res.notes)
    assert all(f.status in ("UNVERIFIED", "NEEDS_REVIEW") for f in res.fields)


def test_lab_report_pdf_text_layer_has_evidence():
    data = (SAMPLES / "lab_report_hba1c.pdf").read_bytes()
    res = pipeline.extract_document(data, "application/pdf", "lab.pdf", today=TODAY)
    fields = {f.name: f for f in res.fields}
    assert fields["document_type"].value == "LAB_REPORT"
    assert fields["hba1c_due_date"].value == "2027-01-10"
    assert fields["hba1c_due_date"].evidence["bboxes"]


# ------------------------------------------------------------------ Sarvam adapter (mock HTTP, no key used)
@pytest.fixture()
def sarvam_mock(monkeypatch):
    calls: list[httpx.Request] = []
    responses: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        status, body = responses.pop(0)
        return httpx.Response(status, json=body)

    monkeypatch.setattr(settings, "sarvam_api_key", "test-key-not-real")
    monkeypatch.setattr(sarvam, "_client", lambda timeout=None: httpx.Client(
        base_url="https://api.sarvam.ai", transport=httpx.MockTransport(handler),
        headers={"api-subscription-key": settings.sarvam_api_key}))
    return calls, responses


def test_sarvam_chat_falls_back_from_json_schema(sarvam_mock):
    calls, responses = sarvam_mock
    responses += [(400, {"error": {"message": "response_format json_schema not supported"}}),
                  (200, {"choices": [{"message": {"content": json.dumps(_llm_reply())}, "finish_reason": "stop"}]})]
    out = sarvam.SarvamLLM().json_completion("sys", "user", {"type": "object"}, "reply")
    assert out["intents"] == ["RESCHEDULE_REQUEST"]
    first, second = (json.loads(c.content) for c in calls)
    assert first["response_format"]["type"] == "json_schema" and second["response_format"]["type"] == "json_object"
    assert calls[0].url.path == "/v1/chat/completions" and calls[0].headers["api-subscription-key"]


def test_sarvam_chat_retries_without_reasoning_parameter(sarvam_mock):
    calls, responses = sarvam_mock
    responses += [(400, {"error": {"message": "Unknown parameter: reasoning_effort"}}),
                  (200, {"choices": [{"message": {"content": '{"ok": true}'}}]})]
    assert sarvam.SarvamLLM().json_completion("s", "u", {}, "x") == {"ok": True}
    first, second = (json.loads(c.content) for c in calls)
    assert "reasoning_effort" in first and "reasoning_effort" not in second
    assert second["response_format"]["type"] == "json_schema"


def test_sarvam_speech_to_text_request(sarvam_mock):
    calls, responses = sarvam_mock
    responses += [(200, {"transcript": "Monday raalenu", "language_code": "te-IN", "language_probability": 0.91})]
    tr = sarvam.SarvamASR().transcribe(b"RIFF....WAVE", "audio/wav", "v.wav", "te")
    assert tr.text == "Monday raalenu" and tr.language_code == "te-IN"
    body = calls[0].content.decode(errors="ignore")
    assert calls[0].url.path == "/speech-to-text" and "saaras:v3" in body and "te-IN" in body and "codemix" in body


def test_sarvam_errors_are_not_retried_forever(sarvam_mock):
    calls, responses = sarvam_mock
    responses += [(401, {"error": {"message": "invalid key"}})]
    with pytest.raises(ProviderError) as exc:
        sarvam.SarvamASR().transcribe(b"x", "audio/wav", "v.wav", "hi")
    assert exc.value.code == "HTTP_401" and len(calls) == 1


def test_sarvam_vision_extract_job_flow(sarvam_mock, monkeypatch):
    calls, responses = sarvam_mock
    monkeypatch.setattr(sarvam.time, "sleep", lambda s: None)
    responses += [(200, {"job_id": "job-1"}), (200, {"status": "Running"}), (200, {"status": "Completed"}),
                  (200, {"result": {"next_review_date": "14/01/2027"}, "annotations": []})]
    out = sarvam.SarvamVisionExtract().extract(b"%PDF-1.4", "application/pdf", "rx.pdf", {"type": "object"})
    assert out["job_id"] == "job-1" and out["result"]["next_review_date"] == "14/01/2027"
    assert [c.url.path for c in calls] == ["/doc-ai/v1/job/extract", "/doc-ai/v1/job/job-1/status",
                                           "/doc-ai/v1/job/job-1/status", "/doc-ai/v1/job/job-1/results"]


def test_missing_key_means_offline_not_a_crash(monkeypatch):
    monkeypatch.setattr(settings, "sarvam_api_key", "")
    monkeypatch.setattr(settings, "llm_provider", "sarvam")
    assert pipeline.get_llm() is None and pipeline.get_asr() is None
    res = pipeline.understand_reply("Avunu vastanu", today=TODAY)
    assert res.source == "RULES"
    assert pipeline.provider_status()["llm"]["active"] == "rules (offline)"
