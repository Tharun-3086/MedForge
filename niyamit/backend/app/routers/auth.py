"""Staff sign-in. Sessions are httpOnly cookies; passwords are scrypt hashes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import settings
from app.db import get_db
from app.enums import Role
from app.models import Clinic, Membership, User
from app.security import (
    STAFF_COOKIE,
    Staff,
    client_ip,
    current_staff,
    issue_session,
    rate_limit,
    set_cookie,
    verify_password,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])

PERMISSIONS = {
    Role.ADMIN: ["patients", "plans.approve", "tasks", "tasks.clinical.view", "intake", "messages", "settings",
                 "audit", "metrics", "demo", "evals"],
    Role.DOCTOR: ["patients", "plans.approve", "tasks", "tasks.clinical", "intake", "messages", "metrics", "demo",
                  "evals"],
    Role.NURSE: ["patients", "plans.approve", "tasks", "tasks.clinical", "intake", "messages", "metrics", "demo",
                 "evals"],
    Role.RECEPTION: ["patients", "tasks", "intake", "messages"],
    Role.OPERATOR: ["ops", "audit", "metrics", "evals"],
}


class LoginIn(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


def staff_payload(db: Session, staff: Staff) -> dict:
    clinic = db.get(Clinic, staff.clinic_id)
    perms = list(PERMISSIONS.get(Role(staff.role), []))
    if staff.role in clinic.plan_approver_roles and "plans.approve" not in perms:
        perms.append("plans.approve")
    if staff.role not in clinic.plan_approver_roles and "plans.approve" in perms:
        perms.remove("plans.approve")
    return {"user": {"id": str(staff.user_id), "name": staff.name, "email": staff.email, "role": staff.role,
                     "label": staff.label},
            "clinic": {"id": str(clinic.id), "name": clinic.name, "short_name": clinic.short_name,
                       "phone": clinic.phone, "timezone": clinic.timezone, "is_synthetic": clinic.is_synthetic},
            "permissions": perms, "demo_mode": settings.demo_mode}


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    email = body.email.strip().lower()
    rate_limit(f"login:{client_ip(request)}", 20, 60)
    rate_limit(f"login-user:{email}", 10, 300)
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        audit(db, clinic_id=None, action="LOGIN_FAILED", actor_type="ANONYMOUS", outcome="DENIED",
              detail={"email_domain": email.split("@")[-1][:60]})
        db.commit()
        raise HTTPException(401, "Email or password is not correct.")
    membership = db.scalar(select(Membership).where(Membership.user_id == user.id).order_by(Membership.id))
    if membership is None:
        raise HTTPException(403, "This account is not linked to a clinic.")
    staff = Staff(user.id, membership.clinic_id, membership.role, user.name, user.email)
    set_cookie(response, STAFF_COOKIE, issue_session("staff", str(user.id), str(membership.clinic_id),
                                                     role=membership.role))
    audit(db, clinic_id=membership.clinic_id, action="LOGIN", actor=staff)
    db.commit()
    return staff_payload(db, staff)


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(STAFF_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(staff: Staff = Depends(current_staff), db: Session = Depends(get_db)) -> dict:
    return staff_payload(db, staff)


@router.get("/demo-users")
def demo_users(db: Session = Depends(get_db)) -> dict:
    """Demo mode only: one-click sign-in buttons for the synthetic accounts."""
    if not settings.demo_mode:
        raise HTTPException(404, "Not found.")
    from app.seed import DEMO_PASSWORD, STAFF_A, STAFF_B
    from app.services.demo import SANDBOX_PREFIX

    rows = db.execute(select(User, Membership, Clinic).join(Membership, Membership.user_id == User.id)
                      .join(Clinic, Clinic.id == Membership.clinic_id)
                      .where(Clinic.is_synthetic.is_(True), Clinic.name.not_like(f"{SANDBOX_PREFIX}%"),
                             User.email.in_([row[0] for row in STAFF_A + STAFF_B]))
                      .order_by(Clinic.name.desc(), Membership.role)).all()
    return {"password": DEMO_PASSWORD,
            "users": [{"email": u.email, "name": u.name, "role": m.role, "clinic": c.short_name} for u, m, c in rows]}
