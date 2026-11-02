"""Structured JSON logs with redaction: ids and correlation ids only, never patient content."""
from __future__ import annotations

import json
import logging
import re

from app.config import settings
from app.context import correlation_id

PHONE = re.compile(r"(?<![\w-])\+?\d(?:[\s-]?\d){9,13}(?![\w-])")  # phone-like digit runs, not ids


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = PHONE.sub("[redacted-number]", record.getMessage())
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "msg": message,
            "correlation_id": correlation_id.get(),
        }
        for key in ("event", "object_id", "provider", "status", "duration_ms", "error_code", "path", "method"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else ""
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.log_level.upper())
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
