"""Database models (PRD section 13). PostgreSQL is the source of truth for workflow state.

Every tenant-owned row carries `clinic_id`; services always filter by it.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow

JSONType = JSON().with_variant(JSONB(), "postgresql")


def pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


def clinic_fk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, ForeignKey("clinics.id"), nullable=False, index=True)


# ---------------------------------------------------------------------------------- tenancy
class Clinic(Base):
    __tablename__ = "clinics"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(200))
    short_name: Mapped[str] = mapped_column(String(60))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    phone: Mapped[str] = mapped_column(String(32), default="")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    # Clinic configuration (PRD 6.4 / FR-30)
    languages: Mapped[list[str]] = mapped_column(JSONType, default=lambda: ["en", "hi", "te"])
    quiet_hours_start: Mapped[int] = mapped_column(Integer, default=21)  # local hour
    quiet_hours_end: Mapped[int] = mapped_column(Integer, default=8)
    reminder_send_hour: Mapped[int] = mapped_column(Integer, default=10)
    reminder_offsets_days: Mapped[list[int]] = mapped_column(JSONType, default=lambda: [-3, -1, 0])
    overdue_nudge_days: Mapped[list[int]] = mapped_column(JSONType, default=lambda: [3, 7])
    overdue_task_after_days: Mapped[int] = mapped_column(Integer, default=7)
    plan_approver_roles: Mapped[list[str]] = mapped_column(JSONType, default=lambda: ["DOCTOR", "NURSE"])
    clinical_queue: Mapped[str] = mapped_column(String(20), default="NURSE")
    urgent_queue: Mapped[str] = mapped_column(String(20), default="DOCTOR")
    task_due_hours: Mapped[int] = mapped_column(Integer, default=24)
    require_patient_verification: Mapped[bool] = mapped_column(Boolean, default=True)
    audio_retention_days: Mapped[int] = mapped_column(Integer, default=30)
    document_retention_days: Mapped[int] = mapped_column(Integer, default=365)
    message_unit_cost_inr: Mapped[float] = mapped_column(Float, default=0.115)  # configurable estimate
    created_at: Mapped[datetime] = created()


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = pk()
    email: Mapped[str] = mapped_column(String(200), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(300))
    phone: Mapped[str] = mapped_column(String(32), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = created()
    memberships: Mapped[list[Membership]] = relationship(back_populates="user", lazy="selectin")


class ClinicSubscription(Base):
    __tablename__ = "clinic_subscriptions"
    clinic_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("clinics.id"), primary_key=True)
    plan_key: Mapped[str] = mapped_column(String(30))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    invoices: Mapped[list[dict]] = mapped_column(JSONType, default=list)


class StaffInvitation(Base):
    __tablename__ = "staff_invitations"
    id: Mapped[uuid.UUID] = pk()
    clinic_id: Mapped[uuid.UUID] = clinic_fk()
    email: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created()


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "clinic_id"),)
    id: Mapped[uuid.UUID] = pk()
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    clinic_id: Mapped[uuid.UUID] = clinic_fk()
    role: Mapped[str] = mapped_column(String(20))
    user: Mapped[User] = relationship(back_populates="memberships")


# ---------------------------------------------------------------------------------- patients
class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (UniqueConstraint("clinic_id", "phone_e164"),)
    id: Mapped[uuid.UUID] = pk()
    clinic_id: Mapped[uuid.UUID] = clinic_fk()
    display_name: Mapped[str] = mapped_column(String(120))
    phone_e164: Mapped[str] = mapped_column(String(20))
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preferred_language: Mapped[str] = mapped_column(String(5), default="en")
    preferred_channel: Mapped[str] = mapped_column(String(20), default="SIMULATED")
    external_ref: Mapped[str] = mapped_column(String(60), default="")
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False)
    opted_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    last_visit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created()


class PatientPriority(Base):
    __tablename__ = "patient_priorities"
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("patients.id"), primary_key=True)
    clinic_id: Mapped[uuid.UUID] = clinic_fk()
    priority: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(500))
    readings_hash: Mapped[str] = mapped_column(String(64))
    assessed_by: Mapped[str] = mapped_column(String(160))
    assessed_at: Mapped[datetime] = created()


class ConsentRecord(Base):
    __tablename__ = "consent_records"
    id: Mapped[uuid.UUID] = pk()
    clinic_id: Mapped[uuid.UUID] = clinic_fk()
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("patients.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(30))
    channel: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    method: Mapped[str] = mapped_column(String(30))  # DEMO_SEED | PATIENT_APP | STAFF_RECORDED | MESSAGE
    notice_version: Mapped[str] = mapped_column(String(20), default="demo-v1")
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = created()


class PatientAccessToken(Base):
    """Magic-link token for the patient web app (stored hashed)."""
    __tablename__ = "patient_access_tokens"
    id: Mapped[uuid.UUID] = pk()
    clinic_id: Mapped[uuid.UUID] = clinic_fk()
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("patients.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created()


class PatientOtpChallenge(Base):
    """One short-lived, single-use development challenge per hashed phone."""
    __tablename__ = "patient_otp_challenges"
    phone_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CaregiverGrant(Base):
    __tablename__ = "caregiver_grants"
    id: Mapped[uuid.UUID] = pk()
    clinic_id: Mapped[uuid.UUID] = clinic_fk()
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("patients.id"), index=True)
    caregiver_name: Mapped[str] = mapped_column(String(120))
    caregiver_phone: Mapped[str] = mapped_column(String(20))
    scopes: Mapped[list[str]] = mapped_column(JSONType, default=list)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")  # ACTIVE | REVOKED
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[str] = mapped_column(String(20), default="PATIENT")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created()


# ---------------------------------------------------------------------------------- intake
class SourceArtifact(Base):
    __tablename__ = "source_artifacts"
    id: Mapped[uuid.UUID] = pk()
    clinic_id: Mapped[uuid.UUID] = clinic_fk()
    patient_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("patients.id"), nullable=True, index=True)
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    uploaded_by_patient: Mapped[bool] = mapped_column(Boolean, default=False)
    source_type: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str] = mapped_column(String(200))
    mime_type: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(Integer)
    page_count: Mapped[int] = mapped_column(Integer, default=1)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(300))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created()


class ExtractionProposal(Base):
    __tablename__ = "extraction_proposals"
    id: Mapped[uuid.UUID] = pk()
    clinic_id: Mapped[uuid.UUID] = clinic_fk()
    patient_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("patients.id"), nullable=True, index=True)
    artifact_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("source_artifacts.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="EXTRACTION_PENDING")
    pipeline_version: Mapped[str] = mapped_column(String(20), default="intake-v1")
    ocr_provider: Mapped[str] = mapped_column(String(40), default="")
    llm_provider: Mapped[str] = mapped_column(String(40), default="")
    model_version: Mapped[str] = mapped_column(String(80), default="")
    error_code: Mapped[str] = mapped_column(String(60), default="")
    provider_notes: Mapped[list[str]] = mapped_column(JSONType, default=list)
    blocks: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)  # OCR blocks + bboxes
    page_sizes: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created()
    fields: Mapped[list[ExtractedField]] = relationship(
        back_populates="proposal", lazy="selectin", order_by="ExtractedField.position"
    )


class ExtractedField(Base):
    __tablename__ = "extracted_fields"
    id: Mapped[uuid.UUID] = pk()
    clinic_id: Mapped[uuid.UUID] = clinic_fk()
    proposal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("extraction_proposals.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(40))
    value: Mapped[str | None] = mapped_column(String(200), nullable=True)  # current value (ISO date etc.)
    proposed_value: Mapped[str | None] = mapped_column(String(200), nullable=True)  # normalised AI proposal, never edited
    extracted_value: Mapped[str | None] = mapped_column(String(300), nullable=True)  # text as written in the source
    status: Mapped[str] = mapped_column(String(20), default="UNVERIFIED")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)  # page, quote, bboxes, block ids
    review_reasons: Mapped[list[str]] = mapped_column(JSONType, default=list)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    proposal: Mapped[ExtractionProposal] = relationship(back_populates="fields")


# ---------------------------------------------------------------------------------- plans
class FollowUpPlan(Base):
    __tablename__ = "follow_up_plans"
    id: Mapped[uuid.UUID] = pk()
    clinic_id: Mapped[uuid.UUID] = clinic_fk()
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("patients.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    version: Mapped[int] = mapped_column(Integer, default=1)
    previous_plan_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="MANUAL")  # MANUAL | ARTIFACT
    source_artifact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = created()
    items: Mapped[list[FollowUpItem]] = relationship(
        back_populates="plan", lazy="selectin", order_by="FollowUpItem.due_date"
    )


class FollowUpItem(Base):
    __tablename__ = "follow_up_items"
    id: Mapped[uuid.UUID] = pk()
    clinic_id: Mapped[uuid.UUID] = clinic_fk()
    plan_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("follow_up_plans.id"), index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("patients.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    label: Mapped[str] = mapped_column(String(120))
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    source_field_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    patient_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = created()
    plan: Mapped[FollowUpPlan] = relationship(back_populates="items")


# ---------------------------------------------------------------------------------- messaging
class OutboundMessage(Base):
    """Transactional outbox for every patient-facing message (reminders, acks, escalations)."""
    __tablename__ = "outbound_messages"
    __table_args__ = (Index("ix_outbound_due", "status", "scheduled_for"),)
    id: Mapped[uuid.UUID] = pk()
    clinic_id: Mapped[uuid.UUID] = clinic_fk()
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("patients.id"), index=True)
    caregiver_grant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    kind: Mapped[str] = mapped_column(String(30))
    template_key: Mapped[str] = mapped_column(String(40))
    template_version: Mapped[int] = mapped_column(Integer, default=1)
    language: Mapped[str] = mapped_column(String(5))
    channel: Mapped[str] = mapped_column(String(20))
    body: Mapped[str] = mapped_column(Text)
    essential: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="SCHEDULED")
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    last_error_code: Mapped[str] = mapped_column(String(80), default="")
    provider_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reply_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    suppressed_reason: Mapped[str] = mapped_column(String(80), default="")
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sending_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created()


class ProviderEvent(Base):
    """Every inbound webhook event, stored before processing. Unique per provider event id."""
    __tablename__ = "provider_events"
    __table_args__ = (UniqueConstraint("provider", "provider_event_id"),)
    id: Mapped[uuid.UUID] = pk()
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(20))
    provider_event_id: Mapped[str] = mapped_column(String(160))
    event_type: Mapped[str] = mapped_column(String(30))  # INBOUND_MESSAGE | DELIVERY_STATUS
    signature_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    processing_status: Mapped[str] = mapped_column(String(20), default="RECEIVED")
    result_ref: Mapped[str] = mapped_column(String(80), default="")
    correlation_id: Mapped[str] = mapped_column(String(40), default="")
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    received_at: Mapped[datetime] = created()
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MessageTemplate(Base):
    __tablename__ = "message_templates"
    __table_args__ = (UniqueConstraint("clinic_id", "key", "language", "version"),)
    id: Mapped[uuid.UUID] = pk()
    clinic_id: Mapped[uuid.UUID] = clinic_fk()
    key: Mapped[str] = mapped_column(String(40))
    language: Mapped[str] = mapped_column(String(5))
    version: Mapped[int] = mapped_column(Integer, default=1)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="APPROVED")  # DRAFT | APPROVED | RETIRED
    approved_by_label: Mapped[str] = mapped_column(String(120), default="")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created()


# ---------------------------------------------------------------------------------- replies
class PatientReply(Base):
    __tablename__ = "patient_replies"
    id: Mapped[uuid.UUID] = pk()
    clinic_id: Mapped[uuid.UUID] = clinic_fk()
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("patients.id"), index=True)
    caregiver_grant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    channel: Mapped[str] = mapped_column(String(20))
    input_mode: Mapped[str] = mapped_column(String(10))
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True)
    provider_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="RECEIVED")
    text: Mapped[str | None] = mapped_column(Text, nullable=True)  # typed text or button value
    audio_artifact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    language_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    asr_provider: Mapped[str] = mapped_column(String(40), default="")
    understanding: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    understanding_source: Mapped[str] = mapped_column(String(30), default="")  # LLM:<provider> | RULES | BUTTON
    provider_notes: Mapped[list[str]] = mapped_column(JSONType, default=list)
    clarification: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    actions: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    correlation_id: Mapped[str] = mapped_column(String(40), default="")
    error_code: Mapped[str] = mapped_column(String(60), default="")
    created_at: Mapped[datetime] = created()
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------------- booking
class AvailabilitySlot(Base):
    __tablename__ = "availability_slots"
    __table_args__ = (Index("ix_slot_clinic_start", "clinic_id", "starts_at"),)
    id: Mapped[uuid.UUID] = pk()
    clinic_id: Mapped[uuid.UUID] = clinic_fk()
    provider_label: Mapped[str] = mapped_column(String(120))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    source: Mapped[str] = mapped_column(String(30), default="SEEDED_DEMO")
    created_at: Mapped[datetime] = created()


class AppointmentRequest(Base):
    __tablename__ = "appointment_requests"
    id: Mapped[uuid.UUID] = pk()
    clinic_id: Mapped[uuid.UUID] = clinic_fk()
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("patients.id"), index=True)
    item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reply_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    requested_by: Mapped[str] = mapped_column(String(20), default="PATIENT")  # PATIENT | CAREGIVER | STAFF
    requested_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    requested_day_text: Mapped[str | None] = mapped_column(String(80), nullable=True)
    requested_time_window: Mapped[str | None] = mapped_column(String(20), nullable=True)
    patient_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="REQUESTED")
    offered_slot_ids: Mapped[list[str]] = mapped_column(JSONType, default=list)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    failure_reason: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        # A slot can hold only one confirmed appointment (database-level guard against double booking).
        Index("uq_confirmed_slot", "slot_id", unique=True, postgresql_where=text("status = 'CONFIRMED'")),
    )
    id: Mapped[uuid.UUID] = pk()
    clinic_id: Mapped[uuid.UUID] = clinic_fk()
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("patients.id"), index=True)
    slot_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("availability_slots.id"), index=True)
    item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="CONFIRMED")
    booking_reference: Mapped[str] = mapped_column(String(20), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True)
    created_by: Mapped[str] = mapped_column(String(20), default="PATIENT")
    committed_at: Mapped[datetime] = created()
    created_at: Mapped[datetime] = created()


# ---------------------------------------------------------------------------------- tasks
class CareTask(Base):
    __tablename__ = "care_tasks"
    __table_args__ = (
        # One open task per dedupe key: retries and duplicate events cannot create duplicates.
        Index(
            "uq_open_task_dedupe",
            "clinic_id",
            "dedupe_key",
            unique=True,
            postgresql_where=text("status IN ('OPEN','ASSIGNED','IN_PROGRESS')"),
        ),
    )
    id: Mapped[uuid.UUID] = pk()
    clinic_id: Mapped[uuid.UUID] = clinic_fk()
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("patients.id"), index=True)
    category: Mapped[str] = mapped_column(String(30))
    barrier_category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    queue: Mapped[str] = mapped_column(String(20))
    priority: Mapped[str] = mapped_column(String(10), default="NORMAL")  # NORMAL | HIGH | URGENT
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    title: Mapped[str] = mapped_column(String(200))
    patient_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(20), default="SYSTEM")
    source_id: Mapped[str] = mapped_column(String(80), default="")
    dedupe_key: Mapped[str] = mapped_column(String(160))
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str] = mapped_column(String(60), default="")
    outcome_note: Mapped[str] = mapped_column(Text, default="")
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    events: Mapped[list[TaskEvent]] = relationship(lazy="selectin", order_by="TaskEvent.created_at")


class TaskEvent(Base):
    __tablename__ = "task_events"
    id: Mapped[uuid.UUID] = pk()
    clinic_id: Mapped[uuid.UUID] = clinic_fk()
    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("care_tasks.id"), index=True)
    actor_type: Mapped[str] = mapped_column(String(20))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    actor_label: Mapped[str] = mapped_column(String(120), default="")
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = created()


# ---------------------------------------------------------------------------------- timeline & audit
class TimelineEvent(Base):
    __tablename__ = "timeline_events"
    __table_args__ = (Index("ix_timeline_patient_time", "patient_id", "occurred_at"),)
    id: Mapped[uuid.UUID] = pk()
    clinic_id: Mapped[uuid.UUID] = clinic_fk()
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("patients.id"))
    event_type: Mapped[str] = mapped_column(String(40))
    actor_type: Mapped[str] = mapped_column(String(20))
    actor_label: Mapped[str] = mapped_column(String(120), default="")
    provenance: Mapped[str] = mapped_column(String(30))
    summary: Mapped[str] = mapped_column(Text)
    patient_words: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(30), default="")
    source_id: Mapped[str] = mapped_column(String(80), default="")
    visibility: Mapped[str] = mapped_column(String(20), default="PATIENT_AND_STAFF")  # STAFF | CLINICAL | PATIENT_AND_STAFF
    occurred_at: Mapped[datetime] = created()


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[uuid.UUID] = pk()
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    actor_type: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[str] = mapped_column(String(60), default="")
    actor_role: Mapped[str] = mapped_column(String(20), default="")
    action: Mapped[str] = mapped_column(String(40))
    object_type: Mapped[str] = mapped_column(String(40), default="")
    object_id: Mapped[str] = mapped_column(String(60), default="")
    patient_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    outcome: Mapped[str] = mapped_column(String(20), default="SUCCESS")
    correlation_id: Mapped[str] = mapped_column(String(40), default="")
    detail: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = created()


# ---------------------------------------------------------------------------------- evaluation & demo
class EvalRun(Base):
    __tablename__ = "eval_runs"
    id: Mapped[uuid.UUID] = pk()
    corpus_version: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    exact_match_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = created()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(120), default="")


class EvalResult(Base):
    __tablename__ = "eval_results"
    id: Mapped[uuid.UUID] = pk()
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("eval_runs.id"), index=True)
    item_id: Mapped[str] = mapped_column(String(20))
    language_pair: Mapped[str] = mapped_column(String(10))
    text: Mapped[str] = mapped_column(Text)
    expected_intents: Mapped[list[str]] = mapped_column(JSONType, default=list)
    predicted_intents: Mapped[list[str]] = mapped_column(JSONType, default=list)
    exact_match: Mapped[bool] = mapped_column(Boolean, default=False)
    expected_fields: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    predicted_fields: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    fields_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(String(200), default="")
    tags: Mapped[list[str]] = mapped_column(JSONType, default=list)


class SystemFlag(Base):
    """Demo fault-injection switches (only honoured when DEMO_MODE is on)."""
    __tablename__ = "system_flags"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
