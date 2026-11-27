# Database schema

Actual models: niyamit/backend/app/models.py. Alembic revisions: niyamit/backend/alembic/versions. PostgreSQL is required; duplicate serialization uses transaction advisory locks.

- Clinic → Membership → User: tenant membership and staff role.
- Patient → ConsentEvent / PatientAccessToken / OTP challenge: consent and patient access.
- Patient + Clinic → SourceArtifact: filename, MIME, content hash, storage key, upload timestamp, declared style/language, retention and deletion markers. The synthetic flag reflects account context and does not de-identify file contents.
- SourceArtifact → ExtractionProposal → ExtractedField: OCR blocks/page geometry, extraction provider/model/version, processing state; field original proposed value, current value, status and review identity/time.
- Evidence JSON: quote, page, boxes, engines, source block IDs, alternatives. New medical metadata: raw value/unit, normalized unit, copied range, source test-date text/validated date, extraction schema/provider/method, and model confidence. None of these metadata additions imply separate clinical review of the reference range.
- FollowUpPlan / PlanItem, CareTask / TaskEvent, appointments and messages retain existing operational behavior.
- AuditEvent and TimelineEvent retain access/review/workflow evidence. Audit records are not a separately tamper-proof external ledger.

No destructive migration or new observation table is introduced in this increment. Proposed future normalized records: Observation and immutable revision; MedicationStatement and revision; ScreeningFinding; ClinicalTargetProfile; DocumentIdentityReview; Export/DeleteRequest. These are design decisions, not implemented tables.
