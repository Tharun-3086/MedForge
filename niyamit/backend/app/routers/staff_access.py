"""Administrators approve new staff via privately shared, expiring invitations."""
import hashlib
import secrets
import uuid
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import settings
from app.db import get_db, utcnow
from app.enums import Role
from app.models import Clinic, Membership, StaffInvitation, User
from app.security import Staff, client_ip, hash_password, rate_limit, require_roles

router = APIRouter(prefix="/v1", tags=["staff access"])
admin_only = require_roles(Role.ADMIN)


class InviteIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    name: str = Field(min_length=1, max_length=120)
    role: Literal["DOCTOR", "NURSE", "RECEPTION"]

    @field_validator("email")
    @classmethod
    def email_valid(cls, value):
        value = value.strip().lower()
        if value.count("@") != 1 or any(c.isspace() for c in value) or not all(value.split("@")):
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("name")
    @classmethod
    def name_valid(cls, value):
        if not value.strip():
            raise ValueError("Name is required")
        return value.strip()


class AcceptIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=12, max_length=200)


@router.get("/clinic/staff-access")
def list_staff(staff: Staff = Depends(admin_only), db: Session = Depends(get_db)):
    rows = db.execute(select(User, Membership).join(Membership, Membership.user_id == User.id)
                      .where(Membership.clinic_id == staff.clinic_id)).all()
    invites = db.scalars(select(StaffInvitation).where(StaffInvitation.clinic_id == staff.clinic_id,
        StaffInvitation.used_at.is_(None), StaffInvitation.revoked_at.is_(None),
        StaffInvitation.expires_at > utcnow()).order_by(StaffInvitation.created_at.desc())).all()
    return {"staff": [{"id": str(m.id), "name": u.name, "email": u.email, "role": m.role,
                        "can_revoke": m.role not in (Role.ADMIN, Role.OPERATOR)} for u, m in rows],
            "invitations": [{"id": str(i.id), "name": i.name, "email": i.email, "role": i.role,
                             "expires_at": i.expires_at.isoformat()} for i in invites]}


@router.post("/clinic/staff/invitations", status_code=201)
def invite(body: InviteIn, staff: Staff = Depends(admin_only), db: Session = Depends(get_db)):
    rate_limit(f"staff-invite:{staff.user_id}", 20, 3600)
    # Serialize invitations within a clinic; do not overwrite an existing account or password.
    db.scalar(select(Clinic).where(Clinic.id == staff.clinic_id).with_for_update())
    if db.scalar(select(User.id).where(User.email == body.email)):
        raise HTTPException(409, "This email already has an account. Existing-account transfers require administrator support.")
    pending = db.scalars(select(StaffInvitation).where(StaffInvitation.clinic_id == staff.clinic_id,
        StaffInvitation.email == body.email, StaffInvitation.used_at.is_(None),
        StaffInvitation.revoked_at.is_(None))).all()
    for old in pending:
        old.revoked_at = utcnow()
    token = secrets.token_urlsafe(32)
    row = StaffInvitation(clinic_id=staff.clinic_id, email=body.email, name=body.name, role=body.role,
                          token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=utcnow()+timedelta(hours=24))
    db.add(row)
    db.flush()
    audit(db, clinic_id=staff.clinic_id, action="STAFF_INVITED", actor=staff,
          object_type="staff_invitation", object_id=str(row.id), detail={"role": body.role})
    db.commit()
    # Fragment prevents the secret from entering server request URLs or referrer headers.
    return {"invitation_url": settings.public_app_url.rstrip('/') + "/staff/accept#" + token,
            "expires_at": row.expires_at.isoformat()}


@router.post("/auth/staff-invitations/accept")
def accept(body: AcceptIn, request: Request, db: Session = Depends(get_db)):
    rate_limit(f"staff-accept:{client_ip(request)}", 10, 300)
    row = db.scalar(select(StaffInvitation).where(
        StaffInvitation.token_hash == hashlib.sha256(body.token.encode()).hexdigest()).with_for_update())
    if row is None or row.used_at or row.revoked_at or row.expires_at <= utcnow():
        raise HTTPException(400, "Invitation is invalid, expired or already used. Ask your clinic administrator for a new link.")
    if db.scalar(select(User.id).where(User.email == row.email)):
        raise HTTPException(409, "This email already has an account. Sign in or contact your administrator.")
    user = User(email=row.email, name=row.name, password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.flush()
        db.add(Membership(user_id=user.id, clinic_id=row.clinic_id, role=row.role))
        row.used_at = utcnow()
        audit(db, clinic_id=row.clinic_id, action="STAFF_INVITATION_ACCEPTED", actor_type="USER",
              actor_id=str(user.id), object_type="staff_invitation", object_id=str(row.id))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "This account was already created. Sign in or contact your administrator.") from None
    return {"email": user.email, "message": "Account created. Sign in with your email and new password."}


@router.delete("/clinic/staff/invitations/{invitation_id}")
def revoke_invite(invitation_id: uuid.UUID, staff: Staff = Depends(admin_only), db: Session = Depends(get_db)):
    row = db.scalar(select(StaffInvitation).where(StaffInvitation.id == invitation_id,
                     StaffInvitation.clinic_id == staff.clinic_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Invitation not found.")
    row.revoked_at = utcnow()
    audit(db, clinic_id=staff.clinic_id, action="STAFF_INVITATION_REVOKED", actor=staff,
          object_type="staff_invitation", object_id=str(row.id))
    db.commit()
    return {"ok": True}


@router.delete("/clinic/staff/{membership_id}")
def revoke_staff(membership_id: uuid.UUID, staff: Staff = Depends(admin_only), db: Session = Depends(get_db)):
    row = db.scalar(select(Membership).where(Membership.id == membership_id,
                     Membership.clinic_id == staff.clinic_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Staff membership not found.")
    if row.role in (Role.ADMIN, Role.OPERATOR):
        raise HTTPException(403, "Administrator and operator access cannot be removed here.")
    audit(db, clinic_id=staff.clinic_id, action="STAFF_ACCESS_REVOKED", actor=staff,
          object_type="membership", object_id=str(row.id))
    db.delete(row)
    db.commit()
    return {"ok": True}
