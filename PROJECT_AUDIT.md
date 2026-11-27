# Project audit — MedForge / Niyamit

Audit date: 27 November 2026. Baseline: feature/health-history-hybrid-ocr, including existing uncommitted work. This is a source audit and local engineering assessment, not clinical validation, penetration testing or a production certification.

## 1. Existing architecture

- `niyamit/frontend`: Next.js 15 / React, shared responsive patient and staff interface; same-origin `/api` reverse proxy, cookie authentication, multilingual copy and installable web manifest.
- `niyamit/android`: Java Android WebView wrapper and PowerShell build tooling. It depends on the hosted web application; it is not an offline clinical application.
- `niyamit/backend`: FastAPI, SQLAlchemy, PostgreSQL, Alembic migrations, Celery/Redis. Local Docker Compose separates API and worker. Optional `Dockerfile.ocr` worker installs PaddleOCR/TrOCR. Render Free uses inline processing and explicitly supports synthetic demos only (`app/render_start.py`).
- Document intake: bounded upload → encrypted original → SourceArtifact → ExtractionProposal → OCR/text blocks → document AI/rules → ExtractedField → clinician review → optional FollowUpPlan. Original documents are retained separately from field corrections.
- `services/health_readings.py` builds shared patient/clinic snapshots and history. Priority is assigned by staff; no validated automatic clinical triage exists.
- Provider adapters: Sarvam document extraction, text LLM, ASR/TTS; optional OpenAI chat/vision/ASR; local OCR. Baidu Unlimited-OCR is an optional experimental adapter. Provider configuration is not evidence of provider accuracy.

## 2. Verified implemented features

| Capability | Actual source evidence | Limit |
|---|---|---|
| Clinic membership and roles | security.py, routers/auth.py, staff_access.py | Clinic-level scope; no assigned-doctor restriction |
| Patient SMS OTP and synthetic demo login | routers/patient_app.py; services/patient_otp.py | SMS provider/trial limits still apply; demo prohibited in production |
| Protected original documents | storage.py, routers/intake.py, patient_app.py | Fernet-encrypted objects; storage signing keys require separate backup |
| Field verification and corrections | services/intake.py | Health values require doctor/nurse; audit records old/current decisions |
| Source-linked readings and history | health_readings.py; frontend health-readings.tsx and reading-trends.ts | Supported parameters only; unverified readings can appear explicitly labelled; charts require verified dates/values |
| Follow-up plans, tasks, bookings, messages | services/plans.py, tasks.py, booking.py, messaging.py | Due dates are not booked appointments; no autonomous diagnosis |
| Consent, caregiver revocation | services/patients.py, security.py, patient_app.py | Provider/retention governance needs deployment review |
| Rate limits, bounded uploads, startup checks | security.py, storage.py, config.py | No malware scanner or fully isolated PDF sandbox |
| Local/remote encrypted storage | storage.py; tests/test_remote_storage.py | PostgreSQL metadata is not application-field encrypted |
| Automated checks | backend/tests; frontend/tests; .github/workflows/ci.yml | Tests are mostly deterministic/offline, not a representative OCR benchmark |

## 3. Partially implemented

- Printed/scanned/photo/mixed OCR: PaddleOCR and optional English TrOCR with Tesseract fallback; handwriting alternatives and uncertainty flags retained. Hindi/Telugu interface support is not handwriting validation.
- Medical measurement extraction: existing regex covers glucose, HbA1c, BP, kidney markers, lipids and weight; schema and LLM prompt originally excluded all medical measurements. Local audit reproduced a returned glucose value being discarded by `_from_sarvam_extract`.
- Native PDF fast path improves latency but intentionally bypasses document AI for recognised text-only reports. It must be measured separately from AI extraction.
- Evidence stores quotes, page boxes, engine/confidence and reviews. Separate unit/reference range/sample date metadata is not consistently captured for each field.
- Corrections preserve original proposed values and audit events; there is no explicit immutable observation/version table.
- Retention scheduler exists; patient-initiated comprehensive export/deletion and legal-hold workflows are not complete.
- Hashes are stored for files but intake does not deduplicate processing. Upload currently hardcodes `is_synthetic=True`.

## 4. Missing functionality at audit baseline

- Structured medical extraction from Sarvam/OpenAI, with reconciliation against OCR rather than blind trust in either.
- Reliable diabetes relevance classification and explanation for unrelated documents.
- Comprehensive diabetes summary, source-linked explanations/reference-range comparisons, medication history, clinician-configurable individualized targets.
- CGM time-series/device ingestion; glucometer ingestion; BMI inputs/calculation; urine albumin, retinal and foot findings; structured medication/dose/frequency records.
- Patient-document identity reconciliation before accepting an upload for a patient.
- Representative consented/de-identified printed/handwritten/mixed multilingual evaluation dataset, measured field accuracy and false acceptance.
- Clinically approved thresholds and external qualified-professional validation.

## 5. Security vulnerabilities and concerns

1. **Release blocker:** public shared demo accounts and synthetic-only Render profile cannot be used for real patient care. Synthetic flags on uploaded originals do not de-identify them.
2. **High:** source identity is not cross-checked with the chosen patient; erroneous clinical attribution is possible even within correct tenant scope.
3. **High:** encryption key lifecycle/backups must be proven; rotating SECRET_KEY without preserving the storage encryption key can make documents unreadable. DB metadata requires managed storage encryption/access controls.
4. **High:** PDF/image byte/page/pixel checks are present, but there is no complete malware scanner, isolated parser sandbox or documented adversarial-input penetration assessment.
5. **High:** signed original URLs are short-lived bearer access links; avoid logging tokens/signatures or distributing them publicly. Request logs currently include document route identifiers.
6. **High:** formal deletion, subprocessor/cross-border processing review, consent notices and incident response ownership need operational/legal review. No compliance claim follows from this audit.
7. **Medium:** no full multi-device session revocation or security penetration test established; API OpenAPI remains exposed even when interactive docs are disabled.
8. **Medium:** provider responses and AI quotes require strict evidence validation, output bounds, prompt-injection handling and safe fallback. Model confidence is not medical correctness.
9. **Operational:** local development credentials are for isolated Docker only; never reuse them online. No secret values were read into this audit or included here.

## 6. Technical debt

- Large routers/services, dense code in health_readings.py, overlapping rules and provider-specific conversion.
- Medical parameter names/units need a versioned catalogue rather than repeated ad hoc regex changes.
- Document classification, lab dates and current measurement extraction are not one coherent structured contract.
- Experimental OCR dependencies are heavy; Render Free and local OCR capabilities differ substantially.
- Legacy `intake-v2` version does not identify each rule/model revision independently.
- Audit tests cover workflow correctness; they must not be presented as OCR/clinical acceptance scores.

## 7. Production-readiness gaps

Not ready for real-patient production. Required gates: independent tenant/security review; verified backups and restore; retention/export/deletion procedures; identity checks; approved clinical rules and targets; representative field-level validation; capacity/latency monitoring; medication-specific clinical review; privacy/legal assessment; dedicated persistent worker and database/storage capacity. Free tiers can sleep and inline OCR can exceed request limits.

## 8. Implementation sequence

1. Preserve dirty work; publish this audit before application changes. Baseline last completed: 217 backend tests, frontend production build passed (earlier wrapped-label repair).
2. Add a versioned, provider-neutral medical extraction contract and evidence validator. Sarvam and OpenAI must receive measurement instructions. Preserve administrative APIs and fast printed-PDF route.
3. Reconcile model/rule candidates: keep exact source quote, value/unit/range/date/engine; flag missing evidence, unit mismatch and disagreement. Never silently replace or autoapprove.
4. Add diabetes relevance status and conservative source-linked summaries; separate verified observations from unverified machine proposals. Avoid diagnosis or treatment recommendations.
5. Extend normalized model for medications, screening findings, CGM/device data and clinician targets in independently reviewed increments; do not imply these are already available.
6. Add isolation/security/format/unit/date regression tests and a benchmark harness. Human benchmark labels and clinical sign-off remain external requirements.
7. Complete operational/privacy documentation, deployment checks and production acceptance review. User retains control of GitHub/Render/APK publication.

## Scope of inspection

Reviewed repository inventory, dirty status, backend main/config/security/auth and provider contracts/prompts/pipeline, storage, intake and review services/models, patient and priority APIs, migrations inventory, clinical history frontend, Docker/Render startup and CI/test inventory. This audit does not claim line-by-line verification of every file, real-provider accuracy, deployed configuration, a new APK build or a penetration test. Subsequent phase documents must distinguish implemented code from planned capabilities.


## First implementation increment outcome

See TEST_REPORT.md for actual runs. Added provider-neutral medical schema, Sarvam/OpenAI measurement wiring, explicit local-provider isolation, source/unit/date validation, model/rule reconciliation, unknown-parameter manual review, source-linked monitoring summaries and audited JSON export. Added patient-scoped hash reuse and derived synthetic flags from clinic/patient context. Existing originals and reviewed records remain intact. New metadata uses existing JSON fields, so no destructive schema migration was introduced. The release blockers above remain; no production readiness or clinical validation claim is made.
