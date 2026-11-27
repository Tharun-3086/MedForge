# API documentation

Actual route schemas: FastAPI `/v1/openapi.json`; interactive docs `/v1/docs` outside production. Authentication uses HttpOnly cookies. Mutating `/v1` requests require `X-Niyamit-Client: web`. Do not share session cookies or signed original links.

## Existing stable workflows

- Staff: POST `/v1/auth/login`; patient OTP: POST `/v1/p/otp/request` and `/verify`.
- Patient uploads: POST `/v1/p/documents`; clinic uploads: POST `/v1/intake-artifacts` with patient_id. Multipart file/source_type/document_style/document_language remain supported. Matching patient/clinic/hash/config returns the existing extraction instead of scheduling it again.
- Clinic inbox GET `/v1/intake-proposals` and `/{id}`; review PATCH `/{id}/fields/{field_id}` with APPROVE/CORRECT/REJECT and reason. Doctor/nurse is required for measurements; uncertain AI proposals require an explicit verification note.
- Health history GET `/v1/p/health-readings` or `/v1/priorities/{patient_id}/health-readings`.
- Originals GET `/v1/p/documents/{artifact_id}/file` for the current patient; clinic original retrieval remains authenticated/scoped.

## Added monitoring summary

- GET `/v1/p/diabetes-summary`: current authenticated patient only.
- GET `/v1/patients/{patient_id}/diabetes-summary`: same-clinic ADMIN/DOCTOR/NURSE.
- Add `?download=true` for an audited JSON attachment. No caller-specified patient ID is accepted on the patient endpoint.
- Response: schema_version, patient, findings with source IDs/page metadata and explanations, historical_comparisons, document relevance, missing_from_verified_records, unstructured medication/screening notices, processing/pending flags and limitations.
- Clinical ranges/targets: comparison is only with a source-copied range when its unit matches; it is not an individualized target or separately verified range.
- 401: wrong/missing session; 403: role/client-header denial; 404: inaccessible patient; 422: invalid review/value/unit; 409: invalid workflow transition. Existing storage failures use 503.

JSON export is a summary export, not comprehensive portability of all medical data/originals. No new endpoint changes clinical priority or medication.


## Demo test-patient removal

DELETE `/v1/patients/{patient_id}` with JSON `{ "confirm_name": "Exact patient name" }`. Only same-clinic Doctor/Admin, DEMO_MODE=true, non-production, synthetic clinic/patient. Fixed showcase Ramesh (SDC-1001) is protected. Detail response exposes `can_remove_test_patient` for button visibility.

Removes the test profile, clinical/workflow data and access links; invalidates pending phone OTP without resetting send limits; frees the phone for a fresh profile. Audit records remain. Originals are deleted after the DB change; failures stay queued in the existing retention cleanup path and are reported by `file_cleanup_pending`. This is not a production right-to-erasure endpoint.


OTP registration precheck: POST `/v1/p/otp/request` normalizes the phone and checks for a clinic patient record before creating a challenge or contacting Twilio. Missing records return 404 with registration instructions and no SMS. Verification still rechecks records to handle removal after a code was requested. The phone challenge cooldown/send limits remain; a separate IP lookup throttle limits registration probing.
