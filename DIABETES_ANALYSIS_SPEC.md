# Diabetes analysis specification

Implemented rule version: `diabetes-summary-v1`; extraction contract: `diabetes-measurements-v1`.

## Implemented

- Plain-English explanations for current supported parameters, source-document links and available page metadata.
- Numerical comparison of the two latest distinct dates with clinic-approved values AND dates, exact matching units, excluding conflicting results on the same date. Direction is increased/decreased/unchanged, not medically improving/worsening.
- Simple explicit numeric laboratory-range comparison using Decimal. Only comparable copied units and a complete low–high range are supported. The UI/export identifies the range as copied, not separately verified and not a personalized target. No diagnosis/urgency is derived from it.
- Scope labels DIABETES_RELATED/OUT_OF_SCOPE/UNCERTAIN based on extracted fields and explicit source terms. Kidney/lipid findings are relevant to monitoring, not evidence that the patient has diabetes. Uncertain/unrelated documents retain original/review access.
- Shared patient/clinic summary and audited JSON download. Missing entries mean absent from verified records, not clinically required investigations.

## Not implemented or clinically validated

Contextual AI longitudinal explanations, personalized target profiles, medication changes/insulin history, screening-result interpretation, CGM/glucometer ingestion, BMI calculation and a comprehensive PDF medical summary. Dates due for screening are not completed findings. Comparison rules are engineering rules and require clinical acceptance before clinical use.

No model arithmetic, clinical thresholds or treatment targets are hardcoded. No autonomous diagnosis, prescription, dose adjustment or criticality scoring is permitted. A future target registry must include author/approver, version, applicability, units, effective date and patient-specific overrides, with tests and clinician sign-off.


## Explanatory reference material

Plain-language concepts were checked against [NIDDK: A1C test](https://www.niddk.nih.gov/health-information/diagnostic-tests/a1c-test), [NIDDK: diabetic kidney disease](https://www.niddk.nih.gov/health-information/diabetes/overview/preventing-problems/diabetic-kidney-disease), and [CDC: diabetes care schedule](https://www.cdc.gov/diabetes/treatment/your-diabetes-care-schedule.html). These references support general explanations; they do not approve this software, substitute for individualized care or establish validation of its extraction/clinical rules. No thresholds or schedules from those pages were automatically applied to patients in this increment.
