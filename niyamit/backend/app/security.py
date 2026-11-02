"""Authentication, sessions, role checks, tenant scoping helpers and rate limiting."""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import timedelta

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.context import correlation_id
from app.db import get_db, utcnow
from app.enums import CLINICAL_ROLES, Role
from app.models import AuditEvent, CaregiverGrant, Membership, Patient, User

log = logging.getLogger("niyamit.security")

STAFF_COOKIE = "nyt_staff"
PATIENT_COOKIE = "nyt_patient"
CAREGIVER_COOKIE = "nyt_caregiver"
ALGORITHM = "HS256"


# ------------------------------------------------------------------ passwords (stdlib scrypt)
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except (ValueError, TypeError):
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(24)


# ------------------------------------------------------------------ JWT sessions
_JWT_KEY = hashlib.sha256(("session-jwt:" + settings.secret_key).encode()).digest()  # 32-byte HS256 key


def issue_session(kind: str, subject: str, clinic_id: str, **claims: object) -> str:
    now = utcnow()
    payload = {
        "typ": kind,
        "sub": subject,
        "cid": clinic_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.session_hours)).timestamp()),
        "jti": uuid.uuid4().hex,
        **claims,
    }
    return jwt.encode(payload, _JWT_KEY, algorithm=ALGORITHM)


def decode_session(token: str, kind: str) -> dict:
    try:
        data = jwt.decode(token, _JWT_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.") from None
    if data.get("typ") != kind:
        raise HTTPException(status_code=401, detail="Wrong session type.")
    return data


def set_cookie(response, name: str, token: str) -> None:
    response.set_cookie(
        name,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_hours * 3600,
        path="/",
    )


# ------------------------------------------------------------------ principals
@dataclass
class Staff:
    user_id: uuid.UUID
    clinic_id: uuid.UUID
    role: str
    name: str
    email: str

    @property
    def is_clinical(self) -> bool:
        return self.role in CLINICAL_ROLES

    @property
    def label(self) -> str:
        return f"{self.name} ({self.role.title()})"


@dataclass
class PatientPrincipal:
    patient_id: uuid.UUID
    clinic_id: uuid.UUID


@dataclass
class CaregiverPrincipal:
    grant_id: uuid.UUID
    patient_id: uuid.UUID
    clinic_id: uuid.UUID
    scopes: list[str] = field(default_factory=list)
    name: str = ""


def current_staff(request: Request, db: Session = Depends(get_db)) -> Staff:
    token = request.cookies.get(STAFF_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Please sign in.")
    data = decode_session(token, "staff")
    user = db.get(User, uuid.UUID(data["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Account is not active.")
    membership = db.scalar(
        select(Membership).where(Membership.user_id == user.id, Membership.clinic_id == uuid.UUID(data["cid"]))
    )
    if membership is None:
        raise HTTPException(status_code=401, detail="No access to this clinic.")
    return Staff(user.id, membership.clinic_id, membership.role, user.name, user.email)


def require_roles(*roles: Role):
    allowed = {r.value for r in roles}

    def dep(staff: Staff = Depends(current_staff), db: Session = Depends(get_db)) -> Staff:
        if staff.role not in allowed:
            record_security_event(db, staff, "ROLE_DENIED", detail={"needed": sorted(allowed)})
            raise HTTPException(status_code=403, detail="Your role cannot do this.")
        return staff

    return dep


def require_staff(staff: Staff = Depends(current_staff), db: Session = Depends(get_db)) -> Staff:
    """Any clinic staff role except the platform operator (who never sees patient content)."""
    if staff.role == Role.OPERATOR:
        record_security_event(db, staff, "ROLE_DENIED", detail={"needed": "clinic staff"})
        raise HTTPException(status_code=403, detail="Operators cannot open patient records.")
    return staff


def current_patient(request: Request, db: Session = Depends(get_db)) -> PatientPrincipal:
    token = request.cookies.get(PATIENT_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Please open the link from your message again.")
    data = decode_session(token, "patient")
    patient = db.get(Patient, uuid.UUID(data["sub"]))
    if patient is None or str(patient.clinic_id) != data["cid"]:
        raise HTTPException(status_code=401, detail="Session is not valid.")
    return PatientPrincipal(patient.id, patient.clinic_id)


def current_caregiver(request: Request, db: Session = Depends(get_db)) -> CaregiverPrincipal:
    token = request.cookies.get(CAREGIVER_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Please open the caregiver link again.")
    data = decode_session(token, "caregiver")
    grant = db.get(CaregiverGrant, uuid.UUID(data["sub"]))
    # Revocation takes effect immediately: the grant is re-checked on every request.
    if grant is None or grant.status != "ACTIVE" or grant.expires_at < utcnow():
        if grant is not None:
            db.add(AuditEvent(clinic_id=grant.clinic_id, actor_type="CAREGIVER", actor_id=str(grant.id),
                              action="ACCESS_DENIED", object_type="caregiver_grant", object_id=str(grant.id),
                              patient_id=grant.patient_id, outcome="DENIED", correlation_id=correlation_id.get(),
                              detail={"reason": "grant revoked or expired"}))
            db.commit()
        raise HTTPException(status_code=403, detail="This caregiver access has been revoked or has expired.")
    return CaregiverPrincipal(grant.id, grant.patient_id, grant.clinic_id, list(grant.scopes), grant.caregiver_name)


def record_security_event(db: Session, staff: Staff | None, action: str, *, object_type: str = "",
                          object_id: str = "", detail: dict | None = None) -> None:
    db.add(
        AuditEvent(
            clinic_id=staff.clinic_id if staff else None,
            actor_type="USER" if staff else "ANONYMOUS",
            actor_id=str(staff.user_id) if staff else "",
            actor_role=staff.role if staff else "",
            action=action,
            object_type=object_type,
            object_id=object_id,
            outcome="DENIED",
            correlation_id=correlation_id.get(),
            detail=detail or {},
        )
    )
    db.commit()


def not_found_or_denied(db: Session, staff: Staff, object_type: str, object_id: object) -> HTTPException:
    """Cross-clinic or unknown ids look identical to the caller (no data leakage); the attempt is audited."""
    record_security_event(db, staff, "ACCESS_DENIED", object_type=object_type, object_id=str(object_id),
                          detail={"reason": "not found in caller's clinic"})
    return HTTPException(status_code=404, detail=f"{object_type.replace('_', ' ').capitalize()} not found.")


# ------------------------------------------------------------------ rate limiting
_local_counters: dict[str, tuple[int, float]] = {}


def rate_limit(bucket: str, limit: int, window_seconds: int) -> None:
    """Fixed-window limiter in Redis; falls back to process memory if Redis is unavailable."""
    from app.redis_client import get_redis

    if not settings.rate_limits_enabled:
        return
    window = int(time.time() // window_seconds)
    key = f"rl:{bucket}:{window}"
    try:
        r = get_redis()
        count = r.incr(key)
        if count == 1:
            r.expire(key, window_seconds + 5)
    except Exception:  # noqa: BLE001 - availability over strictness for the demo
        count, _ = _local_counters.get(key, (0, 0.0))
        count += 1
        _local_counters[key] = (count, time.time())
    if count > limit:
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute and try again.")


def client_ip(request: Request) -> str:
    """The caller's address for rate limits. Behind the Next.js proxy the right-most X-Forwarded-For entry is the
    one the proxy added; entries further left come from the client and can be forged, so they are ignored."""
    hops = settings.trusted_proxy_hops
    fwd = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if hops > 0 and fwd:
        return fwd[-hops] if len(fwd) >= hops else fwd[0]
    return request.client.host if request.client else "unknown"
