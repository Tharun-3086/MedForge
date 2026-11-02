"""Provider-neutral interfaces. Domain code never imports a vendor SDK directly."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx


class ProviderError(Exception):
    """A provider call failed. `code` is safe to show staff and store; never contains patient content."""

    def __init__(self, provider: str, code: str, detail: str = "", retriable: bool = False):
        super().__init__(f"{provider}: {code}")
        self.provider = provider
        self.code = code
        self.detail = detail[:300]
        self.retriable = retriable


@dataclass
class Transcript:
    text: str
    language_code: str | None
    language_probability: float | None
    provider: str
    model: str


class LLM(Protocol):
    name: str
    model: str

    def json_completion(self, system: str, user: str, schema: dict[str, Any], schema_name: str,
                        images: list[tuple[bytes, str]] | None = None) -> dict[str, Any]: ...


class ASR(Protocol):
    name: str
    model: str

    def transcribe(self, audio: bytes, mime: str, filename: str, language_hint: str | None) -> Transcript: ...


class TTS(Protocol):
    name: str

    def synthesize(self, text: str, language: str) -> bytes: ...


def parse_json_content(content: str | None, provider: str) -> dict[str, Any]:
    """Models sometimes wrap JSON in fences or reasoning tags; take the first JSON object."""
    if not content:
        raise ProviderError(provider, "EMPTY_RESPONSE")
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(content[start: end + 1])
            except json.JSONDecodeError:
                pass
    raise ProviderError(provider, "INVALID_JSON")


def request_with_retry(client: httpx.Client, method: str, url: str, provider: str, *, attempts: int = 2,
                       **kwargs: Any) -> httpx.Response:
    """Bounded retry with backoff for transient errors (429/5xx/timeouts)."""
    last: ProviderError | None = None
    for attempt in range(attempts):
        try:
            resp = client.request(method, url, **kwargs)
        except httpx.TimeoutException:
            last = ProviderError(provider, "TIMEOUT", retriable=True)
        except httpx.HTTPError as exc:
            last = ProviderError(provider, "NETWORK_ERROR", type(exc).__name__, retriable=True)
        else:
            if resp.status_code < 400:
                return resp
            code = f"HTTP_{resp.status_code}"
            retriable = resp.status_code in (429, 500, 502, 503, 504)
            last = ProviderError(provider, code, _error_text(resp), retriable=retriable)
            if not retriable:
                raise last
        if attempt + 1 < attempts:
            time.sleep(1.5 * (attempt + 1))
    assert last is not None
    raise last


def _error_text(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        err = body.get("error", body)
        if isinstance(err, dict):
            return str(err.get("message") or err.get("code") or err)[:300]
        return str(err)[:300]
    except Exception:  # noqa: BLE001
        return resp.text[:300]
