"""Private, encrypted file storage with strict upload validation and short-lived signed access."""
from __future__ import annotations

import hashlib
import hmac
import io
import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from app.config import settings

_fernet = Fernet(settings.fernet_key)

DOC_TYPES = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/csv": ".csv",
}
AUDIO_TYPES = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
}


@dataclass
class ValidatedFile:
    data: bytes
    mime: str
    filename: str
    page_count: int
    sha256: str


def sniff_mime(data: bytes) -> str | None:
    """Identify the file by its magic bytes, never by the client-supplied content type."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav"
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return "audio/webm"
    if data.startswith(b"OggS"):
        return "audio/ogg"
    if data[4:8] == b"ftyp":
        return "audio/mp4"
    if data.startswith(b"ID3") or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = zf.namelist()
                total = sum(i.file_size for i in zf.infolist())
            if total > 50 * 1024 * 1024:
                return None  # decompression bomb guard
            if "[Content_Types].xml" in names and any(n.startswith("xl/") for n in names):
                return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        except zipfile.BadZipFile:
            return None
        return None
    try:
        sample = data[:4096].decode("utf-8")
        if "," in sample and "\x00" not in sample:
            return "text/csv"
    except UnicodeDecodeError:
        return None
    return None


def validate_document(data: bytes, filename: str) -> ValidatedFile:
    limit = settings.max_upload_mb * 1024 * 1024
    if len(data) == 0:
        raise HTTPException(400, "The file is empty.")
    if len(data) > limit:
        raise HTTPException(413, f"File is larger than {settings.max_upload_mb} MB.")
    mime = sniff_mime(data)
    if mime not in DOC_TYPES:
        raise HTTPException(415, "Only PDF, PNG, JPG, WEBP, XLSX or CSV files are accepted.")
    ext = Path(filename).suffix.lower()
    allowed_ext = {DOC_TYPES[mime]} | ({".jpeg"} if mime == "image/jpeg" else set())
    if ext not in allowed_ext:
        raise HTTPException(415, f"File extension {ext or '(none)'} does not match its content ({mime}).")
    pages = 1
    if mime == "application/pdf":
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise HTTPException(415, "Password-protected PDFs are not accepted.")
            pages = len(reader.pages)
        except HTTPException:
            raise
        except Exception:  # noqa: BLE001
            raise HTTPException(415, "The PDF could not be read.") from None
        if pages > settings.max_pdf_pages:
            raise HTTPException(413, f"PDF has {pages} pages; the limit is {settings.max_pdf_pages}.")
    elif mime.startswith("image/"):
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = settings.max_image_pixels
        try:
            with Image.open(io.BytesIO(data)) as im:
                im.verify()
        except Exception:  # noqa: BLE001 - includes DecompressionBombError
            raise HTTPException(415, "The image could not be read or is too large.") from None
    safe_name = Path(filename).name[:120] or f"upload{DOC_TYPES[mime]}"
    return ValidatedFile(data, mime, safe_name, pages, hashlib.sha256(data).hexdigest())


def validate_audio(data: bytes, filename: str) -> ValidatedFile:
    if len(data) == 0:
        raise HTTPException(400, "The recording is empty.")
    if len(data) > settings.max_audio_mb * 1024 * 1024:
        raise HTTPException(413, f"Recording is larger than {settings.max_audio_mb} MB. Keep it under 30 seconds.")
    mime = sniff_mime(data)
    if mime not in AUDIO_TYPES:
        raise HTTPException(415, "Unsupported audio format.")
    name = Path(filename).name[:80] or f"voice{AUDIO_TYPES[mime]}"
    return ValidatedFile(data, mime, name, 1, hashlib.sha256(data).hexdigest())


def store(clinic_id: uuid.UUID, object_id: uuid.UUID, data: bytes) -> str:
    rel = f"{clinic_id}/{object_id}.bin"
    path = Path(settings.storage_dir) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_fernet.encrypt(data))
    return rel


class StorageUnavailable(Exception):
    """The stored file is missing or cannot be decrypted (for example after SECRET_KEY was changed)."""


def load(storage_key: str) -> bytes:
    path = Path(settings.storage_dir) / storage_key
    try:
        return _fernet.decrypt(path.read_bytes())
    except (InvalidToken, FileNotFoundError) as exc:
        raise StorageUnavailable(type(exc).__name__) from None


def delete(storage_key: str) -> None:
    path = Path(settings.storage_dir) / storage_key
    if path.exists():
        path.unlink()


def sign(object_id: str, ttl_seconds: int = 300) -> str:
    exp = int(time.time()) + ttl_seconds
    mac = hmac.new(settings.secret_key.encode(), f"{object_id}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"exp={exp}&sig={mac}"


def verify_signature(object_id: str, exp: int, sig: str) -> bool:
    if exp < time.time():
        return False
    mac = hmac.new(settings.secret_key.encode(), f"{object_id}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(mac, sig)
