"""Authenticated, patient-scoped monitoring summary and user-requested JSON export."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Patient
from app.security import current_patient, PatientPrincipal, Staff, require_roles
from app.enums import Role
from app.audit import audit
from app.services.diabetes_analysis import summary

router=APIRouter(prefix='/v1',tags=['diabetes summary'])


def output(db,patient,download,staff=None):
    result=summary(db,patient)
    audit(db,clinic_id=patient.clinic_id,action='DIABETES_SUMMARY_EXPORTED' if download else 'DIABETES_SUMMARY_VIEWED',
          actor=staff,actor_type=None if staff else 'PATIENT',actor_id='' if staff else str(patient.id),
          object_type='patient',object_id=patient.id,patient_id=patient.id,
          detail={'schema_version':result['schema_version']})
    db.commit()
    return JSONResponse(result,headers={'Content-Disposition':'attachment; filename="niyamit-diabetes-summary.json"'} if download else {})


@router.get('/p/diabetes-summary')
def patient_summary(download:bool=Query(False),me:PatientPrincipal=Depends(current_patient),db:Session=Depends(get_db)):
    patient=db.scalar(select(Patient).where(Patient.id==me.patient_id,Patient.clinic_id==me.clinic_id))
    if patient is None:raise HTTPException(404,'Patient not found.')
    return output(db,patient,download)


@router.get('/patients/{patient_id}/diabetes-summary')
def clinician_summary(patient_id:uuid.UUID,download:bool=Query(False),
                      staff:Staff=Depends(require_roles(Role.ADMIN,Role.DOCTOR,Role.NURSE)),db:Session=Depends(get_db)):
    patient=db.scalar(select(Patient).where(Patient.id==patient_id,Patient.clinic_id==staff.clinic_id))
    if patient is None:raise HTTPException(404,'Patient not found.')
    return output(db,patient,download,staff)
