"""Per-request context (correlation id) shared by logs, audit rows and provider calls."""
from __future__ import annotations

import contextvars
import uuid

correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")


def new_correlation_id() -> str:
    return uuid.uuid4().hex[:16]
