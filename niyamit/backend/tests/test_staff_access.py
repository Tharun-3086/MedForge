from datetime import timedelta
import hashlib
import uuid
from sqlalchemy import select
from app.db import SessionLocal, utcnow
from app.models import StaffInvitation

PASSWORD = "Synthetic-test-password-2026"

def login(c, email="admin@sunrise.demo", password="niyamit-demo"):
    return c.post("/v1/auth/login", json={"email":email,"password":password})

def invite(c, role="NURSE", email=None):
    return c.post("/v1/clinic/staff/invitations",json={"name":"Synthetic Invited Staff",
        "email":email or f"qa-{uuid.uuid4().hex}@example.test","role":role})

def accept(c, token, password=PASSWORD):
    return c.post("/v1/auth/staff-invitations/accept",json={"token":token,"password":password})

def test_invite_accept_login_and_immediate_revoke(client):
    login(client)
    email=f"qa-{uuid.uuid4().hex}@example.test"
    result=invite(client,email=email);assert result.status_code==201
    token=result.json()["invitation_url"].split("#")[1]
    listing=client.get("/v1/clinic/staff-access");assert token not in listing.text
    with SessionLocal() as db:
        row=db.scalar(select(StaffInvitation).where(StaffInvitation.email==email))
        assert row.token_hash==hashlib.sha256(token.encode()).hexdigest()
    client.cookies.clear()
    assert login(client,email,PASSWORD).status_code==401
    assert accept(client,token).status_code==200
    assert accept(client,token).status_code==400
    assert login(client,email,PASSWORD).status_code==200
    assert email not in [u["email"] for u in client.get("/v1/auth/demo-users").json()["users"]]
    saved=dict(client.cookies)
    assert client.get("/v1/patients").status_code==200
    assert client.get("/v1/clinic/staff-access").status_code==403
    login(client)
    member=next(x for x in client.get("/v1/clinic/staff-access").json()["staff"] if x["email"]==email)
    assert client.delete("/v1/clinic/staff/"+member["id"]).status_code==200
    client.cookies.clear();client.cookies.update(saved)
    assert client.get("/v1/patients").status_code==401

def test_only_admin_and_no_privilege_escalation(client):
    login(client,"nurse@sunrise.demo")
    assert invite(client).status_code==403
    login(client)
    assert invite(client,role="ADMIN").status_code==422
    assert invite(client,role="OPERATOR").status_code==422
    assert invite(client,email="doctor@lakeview.demo").status_code==409
    admin=next(x for x in client.get("/v1/clinic/staff-access").json()["staff"] if x["role"]=="ADMIN")
    assert client.delete("/v1/clinic/staff/"+admin["id"]).status_code==403

def test_cancel_expire_replace_and_cross_clinic(client):
    login(client);email=f"qa-{uuid.uuid4().hex}@example.test"
    token=invite(client,email=email).json()["invitation_url"].split("#")[1]
    row=next(x for x in client.get("/v1/clinic/staff-access").json()["invitations"] if x["email"]==email)
    login(client,"admin@lakeview.demo")
    assert all(x["email"]!=email for x in client.get("/v1/clinic/staff-access").json()["invitations"])
    assert client.delete("/v1/clinic/staff/invitations/"+row["id"]).status_code==404
    login(client)
    new=invite(client,email=email).json()["invitation_url"].split("#")[1]
    assert accept(client,token).status_code==400
    assert accept(client,new,password="short").status_code==422
    with SessionLocal() as db:
        r=db.scalar(select(StaffInvitation).where(StaffInvitation.token_hash==hashlib.sha256(new.encode()).hexdigest()))
        r.expires_at=utcnow()-timedelta(seconds=1);db.commit()
    assert accept(client,new).status_code==400
    latest=invite(client,email=email).json()["invitation_url"].split("#")[1]
    row=next(x for x in client.get("/v1/clinic/staff-access").json()["invitations"] if x["email"]==email)
    assert client.delete("/v1/clinic/staff/invitations/"+row["id"]).status_code==200
    assert accept(client,latest).status_code==400


def test_real_clinic_bootstrap_drafts_and_patient_identity(client):
    from app.bootstrap_clinic import create_clinic
    from app.models import Clinic, MessageTemplate, Patient
    tag=uuid.uuid4().hex
    email=f"owner-{tag}@example.test"
    with SessionLocal() as db:
        clinic=create_clinic(db,name="Synthetic test of real-mode "+tag,short_name="QA real-mode",
                            email=email,admin_name="QA Administrator",password=PASSWORD)
        cid=clinic.id
        assert clinic.is_synthetic is False
        assert set(db.scalars(select(MessageTemplate.status).where(MessageTemplate.clinic_id==cid)))=={"DRAFT"}
        db.commit()
    assert login(client,email,PASSWORD).status_code==200
    result=client.post("/v1/patients",json={"display_name":"Fictional real-mode test","phone":"+919000499999"})
    assert result.status_code==201
    with SessionLocal() as db:
        patient=db.get(Patient,uuid.UUID(result.json()["id"]))
        assert patient.is_synthetic is False
    ch=client.post("/v1/p/otp/request",json={"phone":"+919000499999"}).json()
    response=client.post("/v1/p/otp/verify",json={"phone":"+919000499999","challenge_id":ch["challenge_id"],"code":ch["development_code"]})
    assert not response.json().get("authenticated",False)
