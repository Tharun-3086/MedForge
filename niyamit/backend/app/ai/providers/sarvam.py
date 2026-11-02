"""Sarvam AI adapters (REST). Endpoints and parameters follow Sarvam's current docs (Oct 2026):

- Chat:  POST /v1/chat/completions      model sarvam-105b (sarvam-30b / sarvam-m are retired)
- STT:   POST /speech-to-text           model saaras:v3, mode codemix (REST audio must be < 30 s)
- TTS:   POST /text-to-speech           model bulbul:v4-flash with persona speakers
- Vision Extract: POST /doc-ai/v1/job/extract -> GET /doc-ai/v1/job/{id}/status -> GET .../results
Auth header for all: `api-subscription-key`.
"""
from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx

from app.ai.providers.base import ProviderError, Transcript, parse_json_content, request_with_retry
from app.config import settings

LANG_CODES = {"en": "en-IN", "hi": "hi-IN", "te": "te-IN"}


def _client(timeout: float | None = None) -> httpx.Client:
    if not settings.sarvam_ready():
        raise ProviderError("sarvam", "NOT_CONFIGURED")
    return httpx.Client(
        base_url=settings.sarvam_base_url.rstrip("/"),
        timeout=timeout or settings.ai_timeout_seconds,
        headers={"api-subscription-key": settings.sarvam_api_key.strip()},
    )


class SarvamLLM:
    name = "sarvam"

    def __init__(self) -> None:
        self.model = settings.sarvam_chat_model

    def json_completion(self, system: str, user: str, schema: dict[str, Any], schema_name: str,
                        images: list[tuple[bytes, str]] | None = None) -> dict[str, Any]:
        if images:
            raise ProviderError("sarvam", "IMAGES_NOT_SUPPORTED")
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.1,
            "max_tokens": 2000,
            "reasoning_effort": None,  # structured extraction does not need hidden reasoning tokens
        }
        formats = [
            {"type": "json_schema", "json_schema": {"name": schema_name, "schema": schema, "strict": True}},
            {"type": "json_object"},
            None,
        ]
        last_error: ProviderError | None = None
        with _client() as client:
            i = 0
            while i < len(formats):
                fmt = formats[i]
                payload = dict(body)
                if fmt is not None:
                    payload["response_format"] = fmt
                try:
                    resp = request_with_retry(client, "POST", "/v1/chat/completions", "sarvam", json=payload)
                except ProviderError as exc:
                    last_error = exc
                    if exc.code != "HTTP_400":
                        raise
                    if "reasoning" in exc.detail.lower() and "reasoning_effort" in body:
                        body.pop("reasoning_effort")  # parameter not accepted: retry the same format without it
                    else:
                        i += 1  # response format not accepted: fall back to a simpler one
                    continue
                choice = (resp.json().get("choices") or [{}])[0]
                message = choice.get("message") or {}
                content = message.get("content")
                if not content and choice.get("finish_reason") == "length":
                    raise ProviderError("sarvam", "TRUNCATED")
                return parse_json_content(content, "sarvam")
        raise last_error or ProviderError("sarvam", "NO_RESPONSE")


class SarvamASR:
    name = "sarvam"

    def __init__(self) -> None:
        self.model = settings.sarvam_stt_model

    def transcribe(self, audio: bytes, mime: str, filename: str, language_hint: str | None) -> Transcript:
        data: dict[str, str] = {"model": self.model, "language_code": LANG_CODES.get(language_hint or "", "unknown")}
        if self.model.startswith("saaras:v3") and settings.sarvam_stt_mode:
            data["mode"] = settings.sarvam_stt_mode
        with _client() as client:
            resp = request_with_retry(client, "POST", "/speech-to-text", "sarvam",
                                      data=data, files={"file": (filename, audio, mime)})
        body = resp.json()
        text = (body.get("transcript") or "").strip()
        if not text:
            raise ProviderError("sarvam", "EMPTY_TRANSCRIPT")
        return Transcript(text, body.get("language_code"), body.get("language_probability"), "sarvam", self.model)


class SarvamTTS:
    name = "sarvam"

    def synthesize(self, text: str, language: str) -> bytes:
        speaker = {"te": settings.sarvam_tts_speaker_te, "hi": settings.sarvam_tts_speaker_hi}.get(
            language, settings.sarvam_tts_speaker_en)
        payload = {"text": text[:2400], "language_code": LANG_CODES.get(language, "en-IN"),
                   "model": settings.sarvam_tts_model, "speaker": speaker}
        with _client() as client:
            try:
                resp = request_with_retry(client, "POST", "/text-to-speech", "sarvam", json=payload)
            except ProviderError as exc:
                if exc.code != "HTTP_400":
                    raise
                # Voice rosters change; fall back to the default v3 voice rather than failing.
                resp = request_with_retry(client, "POST", "/text-to-speech", "sarvam",
                                          json={"text": payload["text"], "language_code": payload["language_code"],
                                                "model": "bulbul:v3"})
        audios = resp.json().get("audios") or []
        if not audios:
            raise ProviderError("sarvam", "EMPTY_AUDIO")
        return base64.b64decode(audios[0])


class SarvamVisionExtract:
    """Schema-based field extraction with Sarvam Vision (Document AI 'Extract' job)."""
    name = "sarvam-vision"
    model = "sarvam-vision-v1"

    def extract(self, data: bytes, mime: str, filename: str, schema: dict[str, Any]) -> dict[str, Any]:
        if mime not in ("application/pdf", "image/png", "image/jpeg"):
            raise ProviderError(self.name, "UNSUPPORTED_TYPE")
        form = {"schema": json.dumps(schema), "language": "en-IN", "output_format": "json", "model": self.model}
        with _client(timeout=60) as client:
            created = request_with_retry(client, "POST", "/doc-ai/v1/job/extract", self.name,
                                         data=form, files={"file": (filename, data, mime)}).json()
            job_id = created.get("job_id")
            if not job_id:
                raise ProviderError(self.name, "NO_JOB_ID")
            deadline = time.monotonic() + settings.doc_job_timeout_seconds
            status = ""
            while time.monotonic() < deadline:
                st = request_with_retry(client, "GET", f"/doc-ai/v1/job/{job_id}/status", self.name).json()
                status = str(st.get("status", "")).lower()
                if status in {"completed", "partially_completed", "failed", "rejected"}:
                    break
                time.sleep(3)
            if status not in {"completed", "partially_completed"}:
                raise ProviderError(self.name, f"JOB_{(status or 'timeout').upper()}")
            results = request_with_retry(client, "GET", f"/doc-ai/v1/job/{job_id}/results", self.name).json()
        return {"job_id": job_id, "status": status, "result": results.get("result"),
                "annotations": results.get("annotations"), "raw_keys": sorted(results.keys())}
