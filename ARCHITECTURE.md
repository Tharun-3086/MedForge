# Architecture

Status: incremental diabetes-focused extension of the existing app, not a replacement. See PROJECT_AUDIT.md for the baseline.

## Implemented flow

Next.js patient/clinic UI and Android web wrapper → same-origin API proxy → FastAPI session/clinic authorization → bounded upload → patient-scoped duplicate check → encrypted SourceArtifact → ExtractionProposal → Celery worker (or synthetic Render inline mode).

Text-only printed PDF with supported, explicit labels/date: embedded-text rules fast path. Other supported documents: PaddleOCR/TrOCR when configured, Tesseract fallback → Sarvam Vision or configured LLM/OpenAI → administrative fields plus structured measurements → evidence/unit/date validation → rule/AI reconciliation → clinic review → shared health history and source-linked monitoring summary.

AI measurements always require clinician review. Local regex fallback retains its existing unverified display policy. Disagreements remain separate candidates. Unrelated/uncertain documents are labelled in the summary without silently deleting their original or existing follow-up workflow.

## Incremental data model decision

Reuse SourceArtifact, ExtractionProposal, ExtractedField, AuditEvent and existing JSON evidence. Additive evidence keys are versioned by `diabetes-measurements-v1`. No migration is needed for this increment; old records continue to load without new metadata.

Next schema revision should introduce immutable Observation/ObservationRevision, MedicationStatement/MedicationRevision, ScreeningFinding, ClinicalTargetProfile and document identity verification. Do not store CGM series in ad hoc field strings. Migration/backfill/dual-read tests are required before changing the current health API.

## Boundaries

Source storage is private and encrypted; database access is server-side. No external AI when processing consent is absent. OpenAI is optional and is selected explicitly by DOC_PROVIDER; no credentials are embedded. Medical calculations use Decimal/versioned rules, not model arithmetic. Render Free remains a synthetic demo profile; a persistent worker, measured capacity and operational gates are needed for production.
