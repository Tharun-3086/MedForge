"""Celery worker and beat schedule.

    celery -A app.worker worker -B --loglevel=INFO      # worker with the embedded scheduler (demo setup)

Jobs are enqueued by `app.jobs.dispatch` only after the database commit. Every job is idempotent: it re-reads
state from PostgreSQL and does nothing if the work was already done, so retries and duplicates are safe.
"""
from __future__ import annotations

from pathlib import Path

from celery import Celery
from celery.signals import setup_logging

from app.config import settings
from app.jobs import JOBS, periodic, run_job

celery_app = Celery("niyamit", broker=settings.redis_url, backend=None)
celery_app.conf.update(
    task_acks_late=True,  # a crashed worker's job is redelivered
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    beat_schedule={"niyamit-periodic": {"task": "niyamit.periodic", "schedule": 15.0}},
    # keep beat's bookkeeping file next to the stored artifacts, not in the source tree
    beat_schedule_filename=str(Path(settings.storage_dir).resolve().parent / "celerybeat-schedule"),
)
Path(settings.storage_dir).resolve().parent.mkdir(parents=True, exist_ok=True)


@setup_logging.connect
def _logging(**_: object) -> None:
    from app.logging_setup import setup_logging as configure

    configure()


def _cid(request) -> str:
    return getattr(request, "cid", None) or (getattr(request, "headers", None) or {}).get("cid") or ""


def _register(name: str) -> None:
    @celery_app.task(name=f"niyamit.{name}", bind=True, max_retries=3)
    def _task(self, *args: str) -> None:
        try:
            run_job(name, list(args), _cid(self.request))
        except Exception as exc:  # noqa: BLE001 - transient DB/network errors: retry with backoff
            raise self.retry(exc=exc, countdown=5 * (self.request.retries + 1)) from exc


for _name in JOBS:
    _register(_name)


@celery_app.task(name="niyamit.periodic")
def periodic_task() -> dict[str, int]:
    return periodic()
