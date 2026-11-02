"""Optional OpenAI adapters. Needs a pay-as-you-go API key from platform.openai.com
(a ChatGPT Plus subscription does not include API access)."""
from __future__ import annotations

import base64
from typing import Any

import httpx

from app.ai.providers.base import ProviderError, Transcript, parse_json_content, request_with_retry
from app.config import settings


def _client() -> httpx.Client:
    if not settings.openai_ready():
        raise ProviderError("openai", "NOT_CONFIGURED")
    return httpx.Client(
        base_url=settings.openai_base_url.rstrip("/"),
        timeout=settings.ai_timeout_seconds,
        headers={"Authorization": f"Bearer {settings.openai_api_key.strip()}"},
    )


class OpenAILLM:
    name = "openai"

    def __init__(self) -> None:
        self.model = settings.openai_model

    def json_completion(self, system: str, user: str, schema: dict[str, Any], schema_name: str,
                        images: list[tuple[bytes, str]] | None = None) -> dict[str, Any]:
        content: Any = user
        if images:
            content = [{"type": "text", "text": user}] + [
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime};base64,{base64.b64encode(img).decode()}"}}
                for img, mime in images
            ]
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": schema_name, "schema": schema, "strict": True}},
            "max_completion_tokens": 4000,
        }
        with _client() as client:
            resp = request_with_retry(client, "POST", "/chat/completions", "openai", json=payload)
        choice = (resp.json().get("choices") or [{}])[0]
        if choice.get("message", {}).get("refusal"):
            raise ProviderError("openai", "REFUSED")
        return parse_json_content(choice.get("message", {}).get("content"), "openai")


class OpenAIASR:
    name = "openai"

    def __init__(self) -> None:
        self.model = settings.openai_transcribe_model

    def transcribe(self, audio: bytes, mime: str, filename: str, language_hint: str | None) -> Transcript:
        data = {"model": self.model}
        if language_hint in ("hi", "te", "en"):
            data["language"] = language_hint
        with _client() as client:
            resp = request_with_retry(client, "POST", "/audio/transcriptions", "openai",
                                      data=data, files={"file": (filename, audio, mime)})
        text = (resp.json().get("text") or "").strip()
        if not text:
            raise ProviderError("openai", "EMPTY_TRANSCRIPT")
        return Transcript(text, language_hint, None, "openai", self.model)
