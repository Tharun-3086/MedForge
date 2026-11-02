"""Workflow states and categories (PRD sections 7, 8 and 10).

States are stored as plain strings; transitions are enforced in code via `TRANSITIONS`
so every state change is explicit and testable.
"""
from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "ADMIN"
    DOCTOR = "DOCTOR"
    NURSE = "NURSE"
    RECEPTION = "RECEPTION"
    OPERATOR = "OPERATOR"  # platform support: operational data only, patient content masked


CLINICAL_ROLES = {Role.DOCTOR, Role.NURSE}
STAFF_ROLES = {Role.ADMIN, Role.DOCTOR, Role.NURSE, Role.RECEPTION}


class Language(StrEnum):
    EN = "en"
    HI = "hi"
    TE = "te"


class Channel(StrEnum):
    SIMULATED = "SIMULATED"  # in-app demo phone, always labelled as simulated
    WHATSAPP = "WHATSAPP"
    PATIENT_APP = "PATIENT_APP"


class ConsentPurpose(StrEnum):
    REMINDERS = "REMINDERS"
    AI_PROCESSING = "AI_PROCESSING"
    REPORT_SHARING = "REPORT_SHARING"
    CAREGIVER_ACCESS = "CAREGIVER_ACCESS"


class ConsentStatus(StrEnum):
    GRANTED = "GRANTED"
    WITHDRAWN = "WITHDRAWN"


# --- 10.1 Follow-up plan --------------------------------------------------------
class PlanStatus(StrEnum):
    DRAFT = "DRAFT"
    EXTRACTION_PENDING = "EXTRACTION_PENDING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class ItemKind(StrEnum):
    REVIEW_VISIT = "REVIEW_VISIT"
    HBA1C_TEST = "HBA1C_TEST"
    EYE_EXAM = "EYE_EXAM"
    FOOT_EXAM = "FOOT_EXAM"
    KIDNEY_TEST = "KIDNEY_TEST"
    MEDICINE_REFILL = "MEDICINE_REFILL"
    OTHER = "OTHER"


ITEM_LABELS = {
    ItemKind.REVIEW_VISIT: "Review visit",
    ItemKind.HBA1C_TEST: "HbA1c test",
    ItemKind.EYE_EXAM: "Eye (retina) check",
    ItemKind.FOOT_EXAM: "Foot check",
    ItemKind.KIDNEY_TEST: "Kidney test",
    ItemKind.MEDICINE_REFILL: "Medicine refill",
    ItemKind.OTHER: "Follow-up",
}


class ItemStatus(StrEnum):
    PENDING = "PENDING"
    CONFIRMED_BY_PATIENT = "CONFIRMED_BY_PATIENT"  # patient response event, not a clinical change
    BOOKED = "BOOKED"
    COMPLETED = "COMPLETED"  # verified by staff
    CANCELLED = "CANCELLED"


# --- 7.8 Report inbox -----------------------------------------------------------
class ProposalStatus(StrEnum):
    EXTRACTION_PENDING = "EXTRACTION_PENDING"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class FieldStatus(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class SourceType(StrEnum):
    PRESCRIPTION = "PRESCRIPTION"
    LAB_REPORT = "LAB_REPORT"
    REGISTER = "REGISTER"
    SPREADSHEET = "SPREADSHEET"
    VOICE_NOTE = "VOICE_NOTE"
    OTHER = "OTHER"


# --- 10.2 Outbound message / reminder ------------------------------------------
class MessageStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    QUEUED = "QUEUED"
    SENDING = "SENDING"
    SENT_TO_PROVIDER = "SENT_TO_PROVIDER"
    DELIVERED = "DELIVERED"  # only when the provider confirms
    FAILED = "FAILED"
    SUPPRESSED = "SUPPRESSED"
    UNKNOWN = "UNKNOWN"


FINAL_MESSAGE_STATES = {MessageStatus.DELIVERED, MessageStatus.FAILED, MessageStatus.SUPPRESSED}


class MessageKind(StrEnum):
    REMINDER_PRE_DUE = "REMINDER_PRE_DUE"
    REMINDER_DUE = "REMINDER_DUE"
    REMINDER_OVERDUE = "REMINDER_OVERDUE"
    REMINDER_MANUAL = "REMINDER_MANUAL"
    ACKNOWLEDGEMENT = "ACKNOWLEDGEMENT"
    URGENT_ESCALATION = "URGENT_ESCALATION"
    BOOKING_UPDATE = "BOOKING_UPDATE"
    CLARIFICATION = "CLARIFICATION"
    OPT_OUT_CONFIRMATION = "OPT_OUT_CONFIRMATION"
    CAREGIVER_COPY = "CAREGIVER_COPY"


# Essential messages are still sent after an opt-out (e.g. the opt-out confirmation itself
# and the urgent-concern safety script). Reminders are never essential.
ESSENTIAL_KINDS = {MessageKind.OPT_OUT_CONFIRMATION, MessageKind.URGENT_ESCALATION}


# --- 10.3 Patient reply ------------------------------------------------------------
class ReplyStatus(StrEnum):
    RECEIVED = "RECEIVED"
    VALIDATED = "VALIDATED"
    TRANSCRIPTION_FAILED = "TRANSCRIPTION_FAILED"
    CLASSIFIED = "CLASSIFIED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    ROUTED = "ROUTED"
    ACTION_PENDING = "ACTION_PENDING"
    ACTION_SUCCEEDED = "ACTION_SUCCEEDED"
    ACTION_FAILED = "ACTION_FAILED"
    HUMAN_HANDOFF = "HUMAN_HANDOFF"


class InputMode(StrEnum):
    TEXT = "TEXT"
    VOICE = "VOICE"
    BUTTON = "BUTTON"


class Intent(StrEnum):
    CONFIRM_FOLLOWUP = "CONFIRM_FOLLOWUP"
    RESCHEDULE_REQUEST = "RESCHEDULE_REQUEST"
    REPORT_UPLOAD_INTENT = "REPORT_UPLOAD_INTENT"
    CALLBACK_REQUEST = "CALLBACK_REQUEST"
    BARRIER_REPORTED = "BARRIER_REPORTED"
    CLINICAL_QUESTION = "CLINICAL_QUESTION"
    URGENT_CONCERN = "URGENT_CONCERN"
    OPT_OUT = "OPT_OUT"
    OTHER_OR_UNCLEAR = "OTHER_OR_UNCLEAR"


class BarrierCategory(StrEnum):
    TIMING = "TIMING"
    TRANSPORT = "TRANSPORT"
    COST = "COST"
    CONFUSION = "CONFUSION"
    FEELING_WELL = "FEELING_WELL"
    CAREGIVER_LOGISTICS = "CAREGIVER_LOGISTICS"
    OTHER = "OTHER"
    PREFER_NOT_TO_SAY = "PREFER_NOT_TO_SAY"


class TimeWindow(StrEnum):
    MORNING = "MORNING"
    AFTERNOON = "AFTERNOON"
    EVENING = "EVENING"


# --- 7.5 Booking ---------------------------------------------------------------------
class RequestStatus(StrEnum):
    REQUESTED = "REQUESTED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    SLOTS_OFFERED = "SLOTS_OFFERED"
    BOOKED = "BOOKED"
    NOT_BOOKED = "NOT_BOOKED"
    HANDED_TO_STAFF = "HANDED_TO_STAFF"
    CANCELLED = "CANCELLED"


class SlotStatus(StrEnum):
    OPEN = "OPEN"
    BOOKED = "BOOKED"
    BLOCKED = "BLOCKED"


class AppointmentStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


# --- 10.4 Care task --------------------------------------------------------------------
class TaskStatus(StrEnum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    UNABLE_TO_RESOLVE = "UNABLE_TO_RESOLVE"
    CANCELLED = "CANCELLED"


OPEN_TASK_STATES = {TaskStatus.OPEN, TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS}


class TaskCategory(StrEnum):
    RESCHEDULE = "RESCHEDULE"
    CALLBACK = "CALLBACK"
    BARRIER = "BARRIER"
    CLINICAL_QUESTION = "CLINICAL_QUESTION"
    URGENT_CONCERN = "URGENT_CONCERN"
    UNCLEAR_INPUT = "UNCLEAR_INPUT"
    MESSAGE_FAILURE = "MESSAGE_FAILURE"
    OVERDUE_FOLLOWUP = "OVERDUE_FOLLOWUP"
    DOCUMENT_REVIEW = "DOCUMENT_REVIEW"
    BOOKING_FAILED = "BOOKING_FAILED"


CLINICAL_TASK_CATEGORIES = {TaskCategory.CLINICAL_QUESTION, TaskCategory.URGENT_CONCERN}


class TaskQueue(StrEnum):
    NURSE = "NURSE"
    DOCTOR = "DOCTOR"
    RECEPTION = "RECEPTION"


class Provenance(StrEnum):
    PATIENT_REPORTED = "PATIENT_REPORTED"
    AI_PROPOSED = "AI_PROPOSED"
    STAFF_CONFIRMED = "STAFF_CONFIRMED"
    CLINICIAN_APPROVED = "CLINICIAN_APPROVED"
    SYSTEM_EVENT = "SYSTEM_EVENT"


class ActorType(StrEnum):
    USER = "USER"
    PATIENT = "PATIENT"
    CAREGIVER = "CAREGIVER"
    SYSTEM = "SYSTEM"
    AI = "AI"


class CaregiverScope(StrEnum):
    VIEW_APPOINTMENTS = "VIEW_APPOINTMENTS"
    REQUEST_RESCHEDULE = "REQUEST_RESCHEDULE"
    RECEIVE_REMINDER_COPY = "RECEIVE_REMINDER_COPY"


# Allowed transitions. Anything not listed raises InvalidTransition.
TRANSITIONS: dict[type[StrEnum], dict[str, set[str]]] = {
    PlanStatus: {
        PlanStatus.DRAFT: {PlanStatus.EXTRACTION_PENDING, PlanStatus.NEEDS_REVIEW, PlanStatus.CANCELLED},
        PlanStatus.EXTRACTION_PENDING: {PlanStatus.NEEDS_REVIEW, PlanStatus.CANCELLED},
        PlanStatus.NEEDS_REVIEW: {PlanStatus.APPROVED, PlanStatus.REJECTED, PlanStatus.CANCELLED},
        PlanStatus.APPROVED: {PlanStatus.ACTIVE, PlanStatus.CANCELLED, PlanStatus.SUPERSEDED},
        PlanStatus.ACTIVE: {PlanStatus.COMPLETED, PlanStatus.CANCELLED, PlanStatus.SUPERSEDED},
    },
    MessageStatus: {
        MessageStatus.SCHEDULED: {MessageStatus.QUEUED, MessageStatus.SUPPRESSED},
        MessageStatus.QUEUED: {MessageStatus.SENDING, MessageStatus.SUPPRESSED, MessageStatus.QUEUED},
        MessageStatus.SENDING: {
            MessageStatus.SENT_TO_PROVIDER,
            MessageStatus.FAILED,
            MessageStatus.QUEUED,  # transient failure -> bounded retry
            MessageStatus.UNKNOWN,
            MessageStatus.SUPPRESSED,
        },
        MessageStatus.SENT_TO_PROVIDER: {MessageStatus.DELIVERED, MessageStatus.FAILED},
        MessageStatus.UNKNOWN: {MessageStatus.DELIVERED, MessageStatus.FAILED, MessageStatus.SENT_TO_PROVIDER},
        MessageStatus.FAILED: {MessageStatus.QUEUED},  # explicit staff retry only
    },
    TaskStatus: {
        TaskStatus.OPEN: {TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS, TaskStatus.RESOLVED,
                          TaskStatus.UNABLE_TO_RESOLVE, TaskStatus.CANCELLED},
        TaskStatus.ASSIGNED: {TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS, TaskStatus.RESOLVED,
                              TaskStatus.UNABLE_TO_RESOLVE, TaskStatus.CANCELLED, TaskStatus.OPEN},
        TaskStatus.IN_PROGRESS: {TaskStatus.ASSIGNED, TaskStatus.RESOLVED, TaskStatus.UNABLE_TO_RESOLVE,
                                 TaskStatus.CANCELLED},
        TaskStatus.RESOLVED: {TaskStatus.OPEN},  # reopen keeps history
        TaskStatus.UNABLE_TO_RESOLVE: {TaskStatus.OPEN},
        TaskStatus.CANCELLED: {TaskStatus.OPEN},
    },
}


class InvalidTransition(ValueError):
    pass


def check_transition(enum_cls: type[StrEnum], current: str, new: str) -> None:
    allowed = TRANSITIONS[enum_cls].get(current, set())
    if new not in allowed:
        raise InvalidTransition(f"{enum_cls.__name__}: {current} -> {new} is not allowed")
