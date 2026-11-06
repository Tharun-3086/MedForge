"""Test setup. Tests run against a separate database (never the demo one), with jobs inline, offline AI only
(no API keys are ever used) and a temporary file store.

    pytest -q                                  # locally, uses <DATABASE_URL database>_test
    docker compose exec backend pytest -q      # inside Docker
"""
from __future__ import annotations

import os
import tempfile
import uuid
from datetime import date, timedelta
from urllib.parse import urlsplit, urlunsplit

DEFAULT_URL = "postgresql+psycopg://niyamit:niyamit@localhost:5432/niyamit"


def _test_url() -> str:
    if os.environ.get("TEST_DATABASE_URL"):
        return os.environ["TEST_DATABASE_URL"]
    parts = urlsplit(os.environ.get("DATABASE_URL", DEFAULT_URL))
    name = parts.path.lstrip("/") or "niyamit"
    return urlunsplit(parts._replace(path="/" + (name if name.endswith("_test") else name + "_test")))


TEST_URL = _test_url()
os.environ.update({
    "DATABASE_URL": TEST_URL, "TASKS_EAGER": "true", "RATE_LIMITS_ENABLED": "false", "INLINE_SCHEDULER": "false", "DEMO_MODE": "true",
    "PATIENT_OTP_PROVIDER": "development", "TWILIO_ACCOUNT_SID": "", "TWILIO_AUTH_TOKEN": "", "TWILIO_VERIFY_SERVICE_SID": "",
    "APP_ENV": "test", "LLM_PROVIDER": "rules", "ASR_PROVIDER": "none", "TTS_PROVIDER": "none",
    "DOC_PROVIDER": "local", "OCR_PROVIDER": "local", "UNLIMITED_OCR_RUNTIME": "vllm",
    "SARVAM_API_KEY": "", "OPENAI_API_KEY": "", "WHATSAPP_ENABLED": "false",
    "SECRET_KEY": "test-secret-key-for-automated-tests-only-0123456789",
    "STORAGE_DIR": tempfile.mkdtemp(prefix="niyamit-test-files-"),
    "STORAGE_PROVIDER": "local", "SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": "",
})

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402


def _ensure_database() -> None:
    parts = urlsplit(TEST_URL)
    admin = create_engine(urlunsplit(parts._replace(path="/postgres")), isolation_level="AUTOCOMMIT")
    name = parts.path.lstrip("/")
    with admin.connect() as conn:
        if not conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}):
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()


_ensure_database()

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

HEADERS = {"X-Niyamit-Client": "web"}
PASSWORD = "niyamit-demo"


@pytest.fixture(scope="session", autouse=True)
def schema():
    """Build the schema with the real Alembic migration, so migrations are tested too."""
    from alembic import command
    from alembic.config import Config

    assert urlsplit(TEST_URL).path.endswith("_test"), "Refusing to reset a database whose name does not end in _test"
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    command.upgrade(cfg, "head")
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="session")
def seeded(schema) -> dict:
    """Synthetic demo data, created once per test session by running the real workflows."""
    from app.seed import seed

    return seed()


@pytest.fixture()
def client(seeded):
    with TestClient(app, headers=HEADERS) as c:
        yield c


@pytest.fixture()
def no_quiet_hours(seeded):
    """Make reminder dispatch independent of the time of day the tests run."""
    from app.db import SessionLocal
    from app.models import Clinic

    with SessionLocal() as db:
        clinic = db.get(Clinic, uuid.UUID(seeded["clinic_a"]))
        saved = (clinic.quiet_hours_start, clinic.quiet_hours_end)
        clinic.quiet_hours_start = clinic.quiet_hours_end = 0
        db.commit()
    yield
    with SessionLocal() as db:
        clinic = db.get(Clinic, uuid.UUID(seeded["clinic_a"]))
        clinic.quiet_hours_start, clinic.quiet_hours_end = saved
        db.commit()


def login(c: TestClient, email: str) -> dict:
    c.cookies.clear()
    r = c.post("/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture()
def nurse(client):
    login(client, "nurse@sunrise.demo")
    return client


def patient_id(c: TestClient, name: str) -> str:
    rows = c.get("/v1/patients", params={"q": name}).json()["patients"]
    exact = [r for r in rows if r["name"] == name or r["name"].split()[0] == name]
    assert exact, f"patient {name} not found"
    return exact[0]["id"]


def new_patient(c: TestClient, name: str, phone: str, *, language: str = "te", plan_days: int | None = 5) -> str:
    """A fresh patient (with consent and an approved plan) so a test never depends on another test's changes."""
    r = c.post("/v1/patients", json={"display_name": name, "phone": phone, "birth_year": 1970,
                                     "preferred_language": language, "consent_reminders": True, "consent_ai": True})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    if plan_days is not None:
        due = (clinic_today(c) + timedelta(days=plan_days)).isoformat()
        r = c.post("/v1/follow-up-plans", json={"patient_id": pid, "items": [{"kind": "REVIEW_VISIT", "due_date": due}]})
        assert r.status_code == 201 and r.json()["status"] == "ACTIVE", r.text
    return pid


def clinic_today(c: TestClient) -> date:
    return date.fromisoformat(c.get("/v1/dashboard").json()["today"])


def patient_session(c: TestClient, staff_email: str, pid: str, birth_year: int = 1970) -> None:
    """Sign the client in as the patient through a magic link (as a patient would)."""
    login(c, staff_email)
    link = c.post(f"/v1/patients/{pid}/access-link").json()["link"]
    c.cookies.clear()
    r = c.post("/v1/p/verify", json={"token": link.rsplit("/p/", 1)[1], "birth_year": birth_year})
    assert r.status_code == 200, r.text
