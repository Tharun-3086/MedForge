"""Niyamit Care Bridge API.

    uvicorn app.main:app --reload
"""
from __future__ import annotations

import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.context import correlation_id, new_correlation_id
from app.db import engine
from app.enums import InvalidTransition
from app.logging_setup import setup_logging
from app.routers import priorities, billing, auth, demo, evals, intake, patient_app, staff, staff_access, webhooks
from app.storage import StorageUnavailable

log = logging.getLogger("niyamit.api")
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
_stop = threading.Event()


def _scheduler_loop() -> None:
    """In-process scheduler for setups without Celery beat (INLINE_SCHEDULER=true)."""
    from app.jobs import periodic

    while not _stop.wait(15):
        try:
            periodic()
        except Exception:  # noqa: BLE001 - keep ticking; the error is logged
            log.exception("scheduler tick failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    settings.validate_for_startup()
    if settings.inline_scheduler:
        threading.Thread(target=_scheduler_loop, name="niyamit-scheduler", daemon=True).start()
    log.info("api started", extra={"event": "startup"})
    yield
    _stop.set()


app = FastAPI(title="Niyamit Care Bridge API", version="1.0.0", lifespan=lifespan,
              docs_url="/v1/docs" if not settings.is_production else None, openapi_url="/v1/openapi.json")


@app.middleware("http")
async def request_context(request: Request, call_next):
    cid = (request.headers.get("x-correlation-id") or "")[:40] or new_correlation_id()
    token = correlation_id.set(cid)
    started = time.monotonic()
    try:
        path = request.url.path
        # CSRF guard: browsers cannot add this header cross-site without a CORS preflight, which we never allow.
        if (request.method in MUTATING and path.startswith("/v1/") and not path.startswith("/v1/webhooks/")
                and request.headers.get("x-niyamit-client") != "web"):
            return JSONResponse({"detail": "Missing client header."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Correlation-Id"] = cid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers.setdefault("Cache-Control", "no-store")
        log.info("request", extra={"method": request.method, "path": path, "status": response.status_code,
                                   "duration_ms": int((time.monotonic() - started) * 1000)})
        return response
    finally:
        correlation_id.reset(token)


@app.exception_handler(InvalidTransition)
async def invalid_transition(_: Request, exc: InvalidTransition) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=409)


@app.exception_handler(StorageUnavailable)
async def storage_unavailable(_: Request, exc: StorageUnavailable) -> JSONResponse:
    return JSONResponse({"detail": "The stored file cannot be read (it is missing, or the encryption key changed)."},
                        status_code=410)


@app.get("/healthz")
def healthz() -> dict:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"ok": True, "demo_mode": settings.demo_mode}


for r in (auth.router, staff.router, intake.router, patient_app.router, patient_app.caregiver_router,
            demo.router, evals.router, webhooks.router, staff_access.router, billing.router, priorities.router):
    app.include_router(r)
