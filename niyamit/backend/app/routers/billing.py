"""Illustrative subscriptions only: no gateway, auto-renewal or access cutoff."""
import uuid
from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db,utcnow
from app.audit import audit
from app.enums import Role
from app.models import Clinic,ClinicSubscription,FollowUpItem,FollowUpPlan
from app.security import Staff,require_roles

router=APIRouter(prefix="/v1/billing",tags=["demo billing"])
admin=require_roles(Role.ADMIN)
PLANS=[{"key":"starter","name":"Starter","patient_limit":100,"monthly_paise":99900},
       {"key":"growth","name":"Growth","patient_limit":500,"monthly_paise":249900},
       {"key":"scale","name":"Scale","patient_limit":2000,"monthly_paise":499900}]

def active_count(db,cid):
    return db.scalar(select(func.count(func.distinct(FollowUpItem.patient_id)))
        .join(FollowUpPlan,FollowUpPlan.id==FollowUpItem.plan_id)
        .where(FollowUpItem.clinic_id==cid,FollowUpPlan.clinic_id==cid,FollowUpPlan.status=="ACTIVE",
               FollowUpItem.status.in_(["PENDING","CONFIRMED_BY_PATIENT","BOOKED"]))) or 0

@router.get("")
def summary(staff:Staff=Depends(admin),db:Session=Depends(get_db)):
    sub=db.get(ClinicSubscription,staff.clinic_id)
    return {"simulation":True,"selection_enabled":settings.demo_mode,"currency":"INR","plans":PLANS,
            "active_patients":active_count(db,staff.clinic_id),
            "active_definition":"Patients with at least one pending, confirmed or booked follow-up in an active plan. Each patient counts once. This is a current snapshot, not metered monthly billing.",
            "subscription":None if not sub else {"plan_key":sub.plan_key,"period_start":str(sub.period_start),
                "period_end":str(sub.period_end),"status":"DEMO_ACTIVE" if utcnow().date()<sub.period_end else "DEMO_EXPIRED"},
            "invoices":[] if not sub else sub.invoices}

class PlanIn(BaseModel):
    plan_key:Literal["starter","growth","scale"]

@router.post("/simulate")
def simulate(body:PlanIn,staff:Staff=Depends(admin),db:Session=Depends(get_db)):
    if not settings.demo_mode:
        raise HTTPException(403,"Demo subscription activation is disabled outside demo mode. No payment provider is configured.")
    db.scalar(select(Clinic).where(Clinic.id==staff.clinic_id).with_for_update())
    plan=next(p for p in PLANS if p['key']==body.plan_key)
    if active_count(db,staff.clinic_id)>plan['patient_limit']:
        raise HTTPException(409,"Choose a plan that covers your current active patients.")
    today=utcnow().date();start=today.replace(day=1)
    end=date(start.year+1,1,1) if start.month==12 else date(start.year,start.month+1,1)
    sub=db.get(ClinicSubscription,staff.clinic_id)
    if sub is None:
        sub=ClinicSubscription(clinic_id=staff.clinic_id,plan_key=body.plan_key,period_start=start,period_end=end,invoices=[]);db.add(sub)
    elif sub.plan_key==body.plan_key and sub.period_end==end:
        return {"ok":True,"message":"This demo plan is already selected for this month. No payment collected."}
    sub.plan_key=body.plan_key;sub.period_start=start;sub.period_end=end
    sub.invoices=[{"reference":"DEMO-"+uuid.uuid4().hex[:12].upper(),"plan":plan['name'],"amount_paise":plan['monthly_paise'],
                   "currency":"INR","status":"SIMULATED_NO_PAYMENT","created_at":utcnow().isoformat(),
                   "period_start":str(start),"period_end":str(end)}]+list(sub.invoices or [])[:19]
    audit(db,clinic_id=staff.clinic_id,action="DEMO_SUBSCRIPTION_SELECTED",actor=staff,detail={"plan":body.plan_key,"payment_collected":False})
    db.commit()
    return {"ok":True,"message":"Demo plan selected. No payment collected; no automatic renewal."}
