"""Staff-confirmed priority with a separate OCR-verification queue. No medical thresholds."""
import hashlib,json,uuid
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy import select,func,case
from sqlalchemy.orm import Session
from app.db import get_db,utcnow
from app.models import Patient,PatientPriority
from app.security import Staff,require_roles
from app.enums import Role
from app.audit import audit
from app.services.health_readings import latest

router=APIRouter(prefix="/v1/priorities",tags=["clinical priority"])
read=require_roles(Role.ADMIN,Role.DOCTOR,Role.NURSE)
write=require_roles(Role.DOCTOR,Role.NURSE)

def fingerprint(readings,revision=""):
    return hashlib.sha256(json.dumps(sorted([(v['key'],v['value'],v['artifact_id'],v['clinic_reviewed'],v['report_date']) for v in readings]),sort_keys=True).encode()+revision.encode()).hexdigest()

def state(readings,assessment,revision=""):
    verification=any(not r['clinic_reviewed'] for r in readings)
    changed=bool(assessment and assessment.readings_hash!=fingerprint(readings,revision))
    if assessment and assessment.priority in ('URGENT','HIGH'):bucket=assessment.priority
    elif verification or changed:bucket='VERIFY'
    elif assessment and assessment.priority=='ROUTINE':bucket='ROUTINE'
    else:bucket='NOT_ASSESSED'
    return bucket,verification,changed

@router.get("")
def queue(offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),staff:Staff=Depends(read),db:Session=Depends(get_db)):
    # Confirmed urgent/high flags are ordered first before pagination.
    order=case((PatientPriority.priority=='URGENT',0),(PatientPriority.priority=='HIGH',1),else_=2)
    patients=db.scalars(select(Patient).outerjoin(PatientPriority,PatientPriority.patient_id==Patient.id)
        .where(Patient.clinic_id==staff.clinic_id).order_by(order,Patient.display_name,Patient.id).offset(offset).limit(limit)).all()
    total=db.scalar(select(func.count()).select_from(Patient).where(Patient.clinic_id==staff.clinic_id))
    rows=[]
    for patient in patients:
        snapshot=latest(db,patient.id,staff.clinic_id);readings=snapshot['readings'];a=db.get(PatientPriority,patient.id)
        bucket,verification,changed=state(readings,a,snapshot['source_revision'])
        if snapshot['processing']:
            verification=True
            if bucket not in ('URGENT','HIGH'):bucket='VERIFY'
        rows.append({'patient_id':str(patient.id),'name':patient.display_name,'bucket':bucket,'needs_verification':verification,
            'readings_changed':changed,'readings':readings,'assessment':None if not a else {'priority':a.priority,'reason':a.reason,'by':a.assessed_by,'at':a.assessed_at.isoformat()}})
    return {'rows':rows,'offset':offset,'limit':limit,'total':total,'can_assess':staff.role in (Role.DOCTOR,Role.NURSE)}

class AssessmentIn(BaseModel):
    priority:Literal['URGENT','HIGH','ROUTINE']
    reason:str=Field(min_length=3,max_length=500)

@router.put("/{patient_id}")
def assess(patient_id:uuid.UUID,body:AssessmentIn,staff:Staff=Depends(write),db:Session=Depends(get_db)):
    if len(body.reason.strip())<3:raise HTTPException(422,'Give a reason for this priority.')
    patient=db.scalar(select(Patient).where(Patient.id==patient_id,Patient.clinic_id==staff.clinic_id).with_for_update())
    if patient is None:raise HTTPException(404,'Patient not found.')
    snapshot=latest(db,patient.id,staff.clinic_id);readings=snapshot['readings']
    if body.priority=='ROUTINE' and (snapshot['processing'] or any(not v['clinic_reviewed'] for v in readings)):
        raise HTTPException(409,'Verify the extracted readings in Report inbox before marking routine.')
    a=db.get(PatientPriority,patient.id);previous=a.priority if a else None
    if a is None:a=PatientPriority(patient_id=patient.id,clinic_id=staff.clinic_id);db.add(a)
    a.priority=body.priority;a.reason=body.reason.strip();a.assessed_by=staff.label;a.assessed_at=utcnow();a.readings_hash=fingerprint(readings,snapshot['source_revision'])
    audit(db,clinic_id=staff.clinic_id,action='PATIENT_PRIORITY_ASSESSED',actor=staff,patient_id=patient.id,
          detail={'previous':previous,'priority':body.priority,'reason':a.reason,'basis':'STAFF_ASSESSMENT'})
    db.commit();return {'ok':True}
