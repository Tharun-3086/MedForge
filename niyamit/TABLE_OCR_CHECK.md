# Table OCR acceptance - 27 November 2026

## Fix

PaddleOCR cell boxes can have slightly different top coordinates. The old row
assembler processed a right-hand unit first, then refused the label/value to its
left. Printed text was recognised but not assembled into a parseable measurement.

The assembler now groups disjoint cells by their shared baseline before sorting
left to right. Every cell must align with every other cell in a row; different
pages, overlapping alternatives and tall boxes spanning adjacent rows stay
separate. Joined source IDs, bounding boxes, weakest confidence, review flags and
alternative transcriptions are retained. Regression tests include the actual
failed glucose image geometry, reversed input order, separate pages and tall boxes.

## Actual local acceptance

All 202 backend PostgreSQL/Alembic tests passed. Five new actual uploads went
through the running Docker app with the rebuilt hybrid worker:

| Source | Expected result | Actual result |
| --- | --- | --- |
| Glucose/HbA1c printed PDF | HbA1c 8.2%, fasting 154, post-meal 218 mg/dL | All correct |
| Kidney/lipid printed PDF | Creatinine 1.1 mg/dL; eGFR 78 mL/min/1.73m2; UACR 22 mg/g; total 188, LDL 108, HDL 44, triglycerides 165 mg/dL | All correct |
| Glucose/HbA1c PNG | Same three measurements | All correct |
| Kidney/lipid PNG | Same seven measurements | All correct |
| Synthetic cursive-font visit note PNG | Report date 27 November 2026, BP 128/82 mmHg, weight 74 kg, review 11 December 2026 | Correct; clinic verification required |

Both laboratory PDFs were uploaded from the clinic; the images were uploaded
from the patient interface. Source downloads matched uploaded bytes. All ten
lab measurements were captured in each format; no missing fields were manually
inserted to make the test pass. The Tesseract fallback also extracted all expected
measurements from the original PDF/PNG fixture pack in an offline reader check.

The cursive follow-up could not be approved without a verification note (422).
After source verification and explicit plan approval, patient confirmation was
visible in the clinic. Both health-reading API payloads matched, and browser
checks showed all 12 expected latest reviewed measurements with 27 November dates.
The new 11 December follow-up remains open and patient-confirmed, not completed.

## Handwriting limits

The positive follow-up fixture is a digitally rendered cursive font, not a real
clinician handwriting benchmark. The separate user-provided historical handwritten
prescription was tested locally with external AI consent off on a separate
fictional QA patient. It proposed only document type, requiring review; it did
not reliably extract handwritten clinical details or invent a follow-up date.
The unrelated historical sample was explicitly rejected, with no plan created.

Readable lab fixtures do not establish accuracy on real prescriptions. Real,
appropriately de-identified handwriting with known follow-up instructions still
needs acceptance testing. Hindi/Telugu handwriting remains manual verification.
Duplicate equivalent handwriting alternatives can still appear in report review;
the health summary/plot consolidates equivalent measurements.

## Completion semantics and deployment scope

A follow-up due date is not a booked appointment slot. The existing staff
completion endpoint permits an earlier completion; it records the actual action
time, not the future due date. The preceding test explicitly recorded a simulated
visit on 27 November for a follow-up due 11 December. No actual visit occurred.
This pass leaves the new future item open. An early real completion must represent
an actual clinician/staff-confirmed encounter, not an automatic test action.

Local Docker only: no Render deployment, APK rebuild, Git commit or push was
performed. Render Free retains Tesseract; the fallback reader check is not a
hosted end-to-end acceptance test. No new SMS or physical microphone test ran.


## Wrapped labels and abbreviated serum creatinine (27 November 2026)

- Recognise `S. CREATININE` without treating urine creatinine as serum.
- Reconstruct `FASTING BLOOD` + `SUGAR` only with a unique, nearby, same-page left-aligned continuation. Keep original text, source boxes, confidence and review flags.
- Extract the result before the reference range, including OCR text with no space between a unit and its following range.
- Preserve a glucose unit read as `ng/dL`; flag `UNSUPPORTED_MEASUREMENT_UNIT` and require clinic correction. Never silently replace it with `mg/dL` or show it as a confirmed glucose result.
- De-identified regression covers wrong-page/distant/ambiguous continuations, ranges, units, source evidence, and clinic correction reflected in the patient readings endpoint.
- PostgreSQL suite: 217 passed. No additional analytes (urea, uric acid, sodium, potassium or chloride) were added to dashboard coverage in this fix.
