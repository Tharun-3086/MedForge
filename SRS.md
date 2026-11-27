# Software requirements and status

Version: diabetes increment 1, 27 November 2026. “Implemented” means source/test support, not clinical acceptance.

| Requirement | Status | Evidence / remaining work |
|---|---|---|
| Original storage and retrieval | Implemented | storage.py, patient/intake APIs; encrypted objects |
| Clinic/patient/role isolation | Implemented; independent review pending | security.py, scoped queries, API tests |
| Printed/photo/scanned/mixed OCR | Partial | hybrid/local adapters; layout and handwriting benchmarks pending |
| Structured measurement AI | Implemented increment | medical_contracts.py, medical_validation.py, pipeline.py |
| Exact evidence, unit, range and date metadata | Partial | Structured AI candidates retain metadata; legacy regex fields may lack ranges/dates |
| Clinic verification and corrections | Implemented | Existing clinical-role review and audit preserved |
| Diabetes document relevance | Partial | Source-text classification and uncertainty; no validated semantic classifier |
| Historical comparisons | Implemented increment | Verified dates/values, equal units, conflicts excluded; no diagnosis |
| Clinical explanations | Partial | Versioned English explanatory copy; contextual AI summarization not implemented |
| Personalized targets | Pending | Clinician configuration and clinical rule approval required |
| Medication/insulin history | Pending | No dosing recommendations or structured medication claims |
| Urine albumin, BMI, retinal/foot findings | Pending | Current due dates are not completed examinations |
| CGM/glucometer ingestion | Pending | Report-based values are not live monitoring |
| Duplicate processing avoidance | Implemented increment | Per-patient/clinic hash and transaction lock; legacy duplicates preserved |
| Download summary | Implemented increment | Authenticated JSON export, audited; no PDF exporter yet |
| Comprehensive original-data export/deletion | Pending | Retention purge exists; user-requested workflow incomplete |
| Clinical readiness | Blocked | Representative validation, privacy/security/operations sign-offs |

Acceptance for this increment: AI measurement must survive provider conversion, preserve evidence, never autoapprove, require clinician correction on units, and appear identically in authorized patient/clinic snapshots after review. Existing local work must remain intact. No Git push/deployment is authorized by this implementation request.
