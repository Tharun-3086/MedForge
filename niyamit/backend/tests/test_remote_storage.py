"""Remote storage tests never call Supabase or use a real service key."""
import uuid

import httpx
import pytest

from app import storage
from app.config import Settings, settings


@pytest.fixture
def remote(monkeypatch):
    monkeypatch.setattr(settings, "storage_provider", "supabase")
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_storage_bucket", "niyamit-artifacts")
    monkeypatch.setattr(settings, "supabase_service_role_key", "test-server-only-key")
    original_client = httpx.Client

    def install(handler):
        monkeypatch.setattr(storage.httpx, "Client", lambda **kwargs: original_client(
            transport=httpx.MockTransport(handler), **kwargs))
    return install


def test_remote_roundtrip_encrypted_and_private(remote, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path))
    objects = {}
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["authorization"] == "Bearer test-server-only-key"
        assert request.headers["apikey"] == "test-server-only-key"
        key = request.url.path.replace("/authenticated/", "/")
        if request.method == "POST":
            assert request.headers["content-type"] == "application/octet-stream"
            assert request.headers["x-upsert"] == "false"
            assert b"private report" not in request.content
            objects[key] = request.content
        elif request.method == "GET":
            assert "/object/authenticated/" in request.url.path
            return httpx.Response(200, content=objects[key])
        else:
            objects.pop(key)
        return httpx.Response(200, json={})

    remote(handler)
    key = storage.store(uuid.uuid4(), uuid.uuid4(), b"private report")
    assert storage.load(key) == b"private report"
    storage.delete(key)
    assert objects == {}
    assert [r.method for r in requests] == ["POST", "GET", "DELETE"]
    assert not list(tmp_path.iterdir())  # no ephemeral-file fallback


@pytest.mark.parametrize("status", [302, 401, 403, 404, 429, 500])
def test_remote_failures_sanitized_and_no_local_fallback(remote, status, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path))
    remote(lambda _: httpx.Response(status, text="sensitive provider details", headers={"location": "https://other.example"}))
    with pytest.raises(storage.StorageUnavailable) as error:
        storage.store(uuid.uuid4(), uuid.uuid4(), b"private")
    assert "sensitive" not in str(error.value)
    assert "test-server-only-key" not in str(error.value)
    assert not list(tmp_path.iterdir())


def test_remote_timeout(remote):
    key = f"{uuid.uuid4()}/{uuid.uuid4()}.bin"

    def timeout(request):
        raise httpx.ReadTimeout("sensitive URL and credentials", request=request)

    remote(timeout)
    with pytest.raises(storage.StorageUnavailable, match="connection failed"):
        storage.load(key)


def test_remote_corrupted_file_and_missing_delete(remote):
    remote(lambda _: httpx.Response(200, content=b"not encrypted"))
    key = f"{uuid.uuid4()}/{uuid.uuid4()}.bin"
    with pytest.raises(storage.StorageUnavailable, match="encryption key"):
        storage.load(key)
    remote(lambda _: httpx.Response(404))
    storage.delete(key)


@pytest.mark.parametrize("key", ["../secret", "/secret", "x/y.bin", "https://example.org", "a" * 36 + "/" + "b" * 36 + ".bin?x=1"])
def test_reject_invalid_object_keys(remote, key):
    remote(lambda _: pytest.fail("Invalid keys must not make requests"))
    for operation in (storage.load, storage.delete):
        with pytest.raises(storage.StorageUnavailable):
            operation(key)


def test_remote_config_validation():
    config = Settings(_env_file=None, storage_provider="supabase", supabase_url="https://example.supabase.co",
                      supabase_service_role_key="test-key", secret_key="x" * 48)
    config.validate_for_startup()
    for field, value in [("supabase_url", "http://example.org"), ("supabase_url", "https://example.org/path"),
                         ("supabase_service_role_key", ""), ("supabase_storage_bucket", "../bucket"),
                         ("secret_key", "dev-only-change-me")]:
        bad = config.model_copy(update={field: value})
        with pytest.raises(RuntimeError):
            bad.validate_for_startup()


def test_hosted_image_pixel_limit(monkeypatch):
    import io
    from PIL import Image
    from fastapi import HTTPException

    image = io.BytesIO()
    Image.new("RGB", (100, 100)).save(image, format="PNG")
    monkeypatch.setattr(settings, "max_image_pixels", 8000)
    with pytest.raises(HTTPException) as error:
        storage.validate_document(image.getvalue(), "large.png")
    assert error.value.status_code == 415


def test_hosted_tables_protected(schema):
    from sqlalchemy import text
    from app.db import Base, engine
    from app.render_start import protect_app_tables

    protect_app_tables()
    with engine.connect() as conn:
        tables = dict(conn.execute(text("SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname='public'")).all())
    for name in [*Base.metadata.tables, "alembic_version"]:
        assert tables[name] is True


def test_patient_ocr_clinic_review_with_remote_storage(nurse, remote):
    from pathlib import Path
    from tests.conftest import login, new_patient, patient_session

    objects = {}

    def handler(request):
        key = request.url.path.replace("/authenticated/", "/")
        if request.method == "POST":
            objects[key] = request.content
            return httpx.Response(200, json={})
        return httpx.Response(200, content=objects[key])

    remote(handler)
    pid = new_patient(nurse, "Remote Storage QA", "+919000490001")
    patient_session(nurse, "nurse@sunrise.demo", pid)
    original = (Path(__file__).parents[1] / "samples" / "prescription_review.png").read_bytes()
    result = nurse.post("/v1/p/documents", files={"file": ("remote-report.png", original, "image/png")},
                        data={"source_type": "PRESCRIPTION"})
    assert result.status_code == 201, result.text
    doc = nurse.get("/v1/p/documents").json()["documents"][0]
    assert doc["ocr_provider"] == "tesseract"
    assert doc["status"] == "NEEDS_REVIEW" and doc["automatic_fields"]
    assert nurse.get(f"/v1/p/documents/{doc['id']}/file").content == original
    assert original not in objects.values()

    login(nurse, "nurse@sunrise.demo")
    proposal = next(p for p in nurse.get("/v1/intake-proposals").json()["proposals"]
                    if p["artifact"]["id"] == doc["id"])
    detail = nurse.get(f"/v1/intake-proposals/{proposal['id']}").json()
    assert nurse.get(detail["artifact"]["content_url"]).content == original
    field = next(f for f in detail["fields"] if f["value"])
    reviewed = nurse.patch(f"/v1/intake-proposals/{proposal['id']}/fields/{field['id']}",
                          json={"action": "APPROVE"})
    assert reviewed.status_code == 200, reviewed.text
    patient_session(nurse, "nurse@sunrise.demo", pid)
    assert nurse.get("/v1/p/documents").json()["documents"][0]["clinic_reviewed_fields"]

    login(nurse, "doctor@lakeview.demo")
    assert nurse.get(detail["artifact"]["content_url"]).status_code == 404
    assert nurse.get(f"/v1/intake-proposals/{proposal['id']}").status_code == 404


def test_remote_upload_outage_returns_503_without_report(nurse, remote):
    from sqlalchemy import func, select
    from app.db import SessionLocal
    from app.models import SourceArtifact
    from tests.conftest import new_patient, patient_session

    pid = new_patient(nurse, "Storage Outage QA", "+919000490002")
    patient_session(nurse, "nurse@sunrise.demo", pid)
    remote(lambda _: httpx.Response(503, text="private provider error"))
    result = nurse.post("/v1/p/documents", files={"file": ("report.csv", b"Test,Value\nHbA1c,6.2 %")})
    assert result.status_code == 503 and "private provider error" not in result.text
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(SourceArtifact).where(SourceArtifact.patient_id == uuid.UUID(pid))) == 0


def test_render_prepare_is_idempotent(seeded, remote):
    from app.render_start import prepare
    from app.db import SessionLocal
    from app.models import Clinic
    from sqlalchemy import func, select

    remote(lambda _: pytest.fail("Existing demo must not be reseeded"))
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(Clinic))
    prepare()
    prepare()
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Clinic)) == before
