"""Local operator command: provision a clinic and its first administrator. Never a public signup API."""
import argparse
import getpass
from sqlalchemy import select
from app.config import settings
from app.db import SessionLocal
from app.enums import Role
from app.models import Clinic, Membership, MessageTemplate, User
from app.security import hash_password
from app.services.templates import TEMPLATES
from app.audit import audit


def create_clinic(db, *, name, short_name, email, admin_name, password):
    name, short_name, email, admin_name = name.strip(), short_name.strip(), email.strip().lower(), admin_name.strip()
    if not name or len(name)>200 or not short_name or len(short_name)>60 or not admin_name or len(admin_name)>120:
        raise ValueError("Enter valid clinic and administrator names.")
    if email.count("@")!=1 or not all(email.split("@")) or len(email)>200 or any(c.isspace() for c in email):
        raise ValueError("Enter a valid administrator email.")
    if not 12<=len(password)<=200:
        raise ValueError("Use a password between 12 and 200 characters.")
    if db.scalar(select(User.id).where(User.email==email)):
        raise ValueError("Email already exists; existing accounts will not be overwritten.")
    if db.scalar(select(Clinic.id).where(Clinic.name==name)):
        raise ValueError("Clinic name already exists; existing clinics will not be overwritten.")
    clinic=Clinic(name=name,short_name=short_name,is_synthetic=False)
    user=User(email=email,name=admin_name,password_hash=hash_password(password))
    db.add_all([clinic,user]);db.flush()
    db.add(Membership(clinic_id=clinic.id,user_id=user.id,role=Role.ADMIN))
    for key,langs in TEMPLATES.items():
        for language,body in langs.items():
            db.add(MessageTemplate(clinic_id=clinic.id,key=key,language=language,version=1,body=body,
                                   status="DRAFT",approved_by_label="",approved_at=None))
    audit(db,clinic_id=clinic.id,action="CLINIC_BOOTSTRAPPED",object_type="clinic",object_id=str(clinic.id))
    db.flush()
    return clinic


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name",required=True);parser.add_argument("--short-name",required=True)
    parser.add_argument("--admin-email",required=True);parser.add_argument("--admin-name",required=True)
    args=parser.parse_args()
    if settings.demo_mode or settings.patient_otp_provider=="development":
        parser.error("Use an isolated non-demo deployment with development OTP disabled before provisioning a real clinic.")
    settings.validate_for_startup()
    password=getpass.getpass("Administrator password (12+ characters): ")
    if password!=getpass.getpass("Confirm password: "):
        parser.error("Passwords do not match.")
    try:
        with SessionLocal() as db:
            clinic=create_clinic(db,name=args.name,short_name=args.short_name,email=args.admin_email,
                                 admin_name=args.admin_name,password=password)
            clinic_id=str(clinic.id);db.commit()
        print("Clinic created:",clinic_id,". Review draft templates before enabling messages.")
    except ValueError as exc:
        parser.error(str(exc))

if __name__=="__main__":
    main()
