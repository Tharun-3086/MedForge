# Report readings, history and trends

Patients and clinic administrators, doctors and nurses see the same source-linked
latest values and dated history. Patient access uses the patient session; clinic
access uses the current clinic membership. Reception and other clinics cannot
use the clinical-history endpoint. Staff verify or correct the original in Report
Inbox. Historical report rows remain visible after newer uploads.

## Supported measurements

| Group | Measurements | Explicit units supported |
|---|---|---|
| Existing | HbA1c; fasting, post-meal, random and unspecified glucose; BP | %, mg/dL, mmol/L, mmHg |
| Kidney | Serum/blood/plasma creatinine; eGFR; urine albumin/creatinine ratio (UACR) | mg/dL or µmol/L; mL/min/1.73m²; mg/g or mg/mmol |
| Lipids | Total cholesterol, LDL cholesterol, HDL cholesterol, triglycerides | mg/dL or mmol/L |
| Weight | Body weight | kg or lb |

Extraction requires a supported label and explicit unit. Reference ranges and
targets are not measurements. Missing units, unsupported formats and conflicting
OCR candidates are not guessed. Creatinine requires a blood/serum/plasma label
to avoid presenting urine creatinine as a serum result. eGFR inequalities such
as `>90` retain the inequality and are not plotted as exact numbers. No eGFR,
UACR, BMI, unit conversion, clinical target or diagnosis is calculated here.

## Verification and chart rules

- All machine readings are labelled unverified. Handwriting, low OCR confidence,
  fallback and engine disagreements require source verification. Uncertain values
  do not replace previous usable readings or enter numeric history responses.
- Doctors and nurses check the original value/unit and record a required note for
  uncertain confirmations or corrections. Conflicting candidates need resolution.
  Automatic text remains separate from clinic-reviewed information.
- Charts require clinic-confirmed measurements and confirmed report dates, with
  at least two distinct dates for the same metric and unit. Different units and
  glucose types never combine. Conflicting same-date values are omitted from the
  chart rather than averaged or arbitrarily selected; source history remains.
- Unknown, conflicting and future dates do not become clinical dates. Upload
  dates are identified separately and never substituted on a trend axis.
- Trends carry no automatic good/bad judgement, urgency, treatment advice or alert.
  Follow-up priority remains staff-assigned. Unresolved readings block routine.

## Local acceptance, 26 November 2026

194 PostgreSQL/Alembic tests and two frontend trend tests passed. Frontend
production build/type checking passed. Two actual Docker patient uploads of
synthetic printed reports produced 16 reviewed history rows across the eight
new metrics. Patient and clinic returned identical data. A third synthetic
cursive-font creatinine report stayed pending until a doctor verified the source
date/value with notes in the UI, then appeared in the three-date patient trend.
These are software checks, not real clinical handwriting validation.

The configured Sarvam key accepted structured chat; a synthetic Document AI job
completed with results. No key was displayed or real patient document sent. The
history QA patient had external AI consent disabled and used local OCR/rules.
Provider availability does not establish clinical accuracy or future quota.

The final local API image reused existing dependencies after a fresh base-image
apt download stalled; the normal Dockerfile remains the clean-build path. The
heavy worker pins its tested Python base digest. No Git push, Render deployment
or APK rebuild was performed for this update.

References: [NIDDK kidney markers](https://www.niddk.nih.gov/health-information/professionals/advanced-search/quick-reference-uacr-gfr),
[Sarvam authentication](https://docs.sarvam.ai/api-reference/authentication).
