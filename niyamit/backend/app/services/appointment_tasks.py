"""Patient-visible appointment task replies and atomic booking changes."""
import uuid
from fastapi import HTTPException
from sqlalchemy import select, text
from app.audit import audit, timeline
from app.db import utcnow
from app.enums import ActorType, Provenance, OPEN_TASK_STATES, TaskStatus, ItemStatus
from app.models import Appointment, AppointmentRequest, AvailabilitySlot, AuditEvent, CareTask, Patient, TimelineEvent
from app.services import booking, tasks
from app.services.common import clinic_tz, same_visit_items

APPOINTMENT_TASKS = {"RESCHEDULE", "BARRIER", "CALLBACK", "BOOKING_FAILED"}


def appointment_options(db, clinic_id, task):
    if task.category not in APPOINTMENT_TASKS:return []
    query=select(Appointment,AvailabilitySlot).join(AvailabilitySlot,AvailabilitySlot.id==Appointment.slot_id).where(
        Appointment.clinic_id==clinic_id,Appointment.patient_id==task.patient_id,
        Appointment.status=="CONFIRMED",AvailabilitySlot.starts_at>utcnow())
    if task.source_type=="appointment":
        try:query=query.where(Appointment.id==uuid.UUID(task.source_id))
        except ValueError:return []
    return db.execute(query.order_by(AvailabilitySlot.starts_at)).all()


def patient_requests(db, patient):
    result=[]
    for task in db.scalars(select(CareTask).where(CareTask.patient_id==patient.id,
        CareTask.clinic_id==patient.clinic_id,CareTask.category.in_(APPOINTMENT_TASKS))
        .order_by(CareTask.created_at.desc()).limit(10)):
        reply=db.scalar(select(TimelineEvent).where(TimelineEvent.clinic_id==patient.clinic_id,
            TimelineEvent.patient_id==patient.id,TimelineEvent.event_type=="CLINICIAN_REPLY",
            TimelineEvent.source_type=="care_task",TimelineEvent.source_id==str(task.id))
            .order_by(TimelineEvent.occurred_at.desc()).limit(1))
        result.append({"id":str(task.id),"question":task.patient_statement or task.title,
            "status":task.status,"outcome":task.outcome,
            "reply":{"text":reply.summary,"from":reply.actor_label,"at":reply.occurred_at.isoformat()} if reply else None})
    return result


def change_appointment(db, staff, clinic, task, *, action, appointment_id, slot_id, message):
    if db.bind.dialect.name=="postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                   {"key":f"appointment-task:{clinic.id}:{appointment_id}"})
    db.refresh(task,with_for_update=True)
    if task.category not in APPOINTMENT_TASKS:
        raise HTTPException(422,"Use an appointment or attendance task.")
    message=message.strip()
    if len(message)<3:raise HTTPException(422,"Enter a message the patient will see.")
    key=f"{action}:{appointment_id}:{slot_id or ''}"
    if task.status not in OPEN_TASK_STATES:
        previous=db.scalars(select(AuditEvent).where(AuditEvent.clinic_id==staff.clinic_id,
            AuditEvent.action=="APPOINTMENT_TASK_CHANGED",AuditEvent.object_id==str(task.id))).all()
        match=next((e for e in previous if (e.detail or {}).get('request_key')==key),None)
        if match:return db.get(Appointment,uuid.UUID(match.detail.get('replacement') or match.detail['old_appointment']))
        raise HTTPException(409,"This task is closed. Refresh to see the latest appointment status.")
    old=db.scalar(select(Appointment).where(Appointment.id==appointment_id,
        Appointment.clinic_id==staff.clinic_id,Appointment.patient_id==task.patient_id).with_for_update())
    if old is None:raise HTTPException(404,"Appointment not found for this patient.")
    if task.source_type=="appointment" and task.source_id!=str(old.id):
        raise HTTPException(422,"This task refers to a different appointment.")
    old_slot=db.get(AvailabilitySlot,old.slot_id)
    if old.status!="CONFIRMED" or old_slot is None or old_slot.starts_at<=utcnow():
        raise HTTPException(409,"This appointment has already changed or is no longer upcoming.")
    patient=db.get(Patient,task.patient_id)
    replacement=None
    if action!="CANCEL":
        if slot_id is None:raise HTTPException(422,"Choose a replacement slot first.")
        slot=db.get(AvailabilitySlot,slot_id)
        if slot is None or slot.clinic_id!=staff.clinic_id:
            raise HTTPException(404,"Replacement slot not found.")
        clock=slot.starts_at.astimezone(clinic_tz(clinic))
        if not 11*60<=clock.hour*60+clock.minute<=19*60:
            raise HTTPException(422,"Choose a replacement start from 11 AM to 7 PM.")
        if action=="POSTPONE" and slot.starts_at<=old_slot.starts_at:
            raise HTTPException(422,"Postpone requires a later slot than the current appointment.")
        if action=="PREPONE" and slot.starts_at>=old_slot.starts_at:
            raise HTTPException(422,"Prepone requires an earlier slot than the current appointment.")
        req=AppointmentRequest(clinic_id=clinic.id,patient_id=patient.id,item_id=old.item_id,
            requested_by="STAFF",requested_date=clock.date(),status="REQUESTED",patient_statement=message)
        db.add(req);db.flush()
        booked=booking.commit_booking(db,clinic,patient,slot_id=slot.id,request_id=req.id,
            idempotency_key=f"taskmove:{task.id}:{slot.id}",created_by="STAFF",staff_label=staff.label)
        if not booked.booked:
            # Caller rolls back the entire transaction, including outbox and request changes.
            raise HTTPException(409,"The replacement could not be booked. The original appointment is unchanged.")
        replacement=booked.appointment
    booking.cancel_appointment(db,clinic,old,reason=message,actor_label=staff.label)
    if old.request_id:
        old_request=db.get(AppointmentRequest,old.request_id)
        if old_request and old_request.appointment_id==old.id:old_request.status="CANCELLED"
    if task.source_type=="appointment_request":
        try:source_request=db.get(AppointmentRequest,uuid.UUID(task.source_id))
        except ValueError:source_request=None
        if source_request and source_request.clinic_id==clinic.id and source_request.patient_id==patient.id:
            source_request.status="BOOKED" if replacement else "CANCELLED"
            source_request.appointment_id=replacement.id if replacement else old.id
    if replacement and old.item_id:
        from app.models import FollowUpItem
        item=db.get(FollowUpItem,old.item_id)
        if item:
            for sibling in same_visit_items(db,item):sibling.status=ItemStatus.BOOKED
    outcome={"CANCEL":"APPOINTMENT_CANCELLED","POSTPONE":"APPOINTMENT_POSTPONED","PREPONE":"APPOINTMENT_PREPONED"}[action]
    summary=(f"Appointment {old.booking_reference} cancelled. {message}" if not replacement else
        f"Appointment {old.booking_reference} {'postponed' if action=='POSTPONE' else 'preponed'} to "
        f"{booking.slot_dict(db.get(AvailabilitySlot,replacement.slot_id),clinic)['label']} "
        f"— ref {replacement.booking_reference}. {message}")
    timeline(db,clinic_id=clinic.id,patient_id=patient.id,event_type="APPOINTMENT_CHANGED",
        summary=summary,provenance=Provenance.STAFF_CONFIRMED,actor_type=ActorType.USER,
        actor_label=staff.label,source_type="appointment",source_id=old.id)
    timeline(db,clinic_id=clinic.id,patient_id=patient.id,event_type="CLINICIAN_REPLY",summary=message,
        patient_words=task.patient_statement,provenance=Provenance.STAFF_CONFIRMED,
        actor_type=ActorType.USER,actor_label=staff.label,source_type="care_task",source_id=task.id)
    related=list(db.scalars(select(CareTask).where(CareTask.clinic_id==clinic.id,
        CareTask.patient_id==patient.id,CareTask.source_type=="appointment",CareTask.source_id==str(old.id),
        CareTask.category.in_(APPOINTMENT_TASKS),CareTask.status.in_(OPEN_TASK_STATES)).with_for_update()).all())
    if task not in related:related.append(task)
    for row in related:
        if row.status in OPEN_TASK_STATES:
            tasks.transition(db,staff,row,TaskStatus.RESOLVED,outcome=outcome,note=summary)
    audit(db,clinic_id=clinic.id,action="APPOINTMENT_TASK_CHANGED",actor=staff,
        object_type="care_task",object_id=task.id,patient_id=patient.id,
        detail={"request_key":key,"old_appointment":str(old.id),
                "replacement":str(replacement.id) if replacement else None,"action":action})
    return replacement or old
