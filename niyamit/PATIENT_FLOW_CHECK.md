# Patient journey acceptance — 26 November 2026

Scope: the actual local Docker frontend/API/PostgreSQL/Celery stack, actual
PaddleOCR/TrOCR and native/scanned PDF reading, using fictional patients and
generated printed/cursive-font documents only. Real handwriting accuracy is not
established by these checks. No Git push or hosted deployment was performed.

## Journey checked

1. Authenticate the patient through the clinic link and birth-year verification;
   the separate Ramesh one-click demo entry was also checked. Automated OTP tests
   remain part of the backend suite; no real SMS was sent in this pass.
2. Reject a broken PNG and allow another file without restarting the upload view.
3. Upload a printed report, retain its original, extract dated measurements and
   show automatic analysis separately from clinic-reviewed information.
4. Upload a cursive-font report. Keep uncertain readings out of latest values;
   require a clinician's source-verification note. Preserve/review OCR alternatives.
5. Confirm fields, resolve duplicate alternatives, finish lab-report review and
   return source-linked reviewed values/history/trends to the patient.
6. Upload a prescription PDF with a future review date. Verify the date, approve
   the care plan, and display it on the patient's home screen.
7. Patient chooses **I will come**. The clinic sees the confirmation; repeat
   confirmation returns **Already noted**, without creating another plan.
8. Resolve the matching document-review tasks. Confirm that approving a plan does
   not lock outstanding health-field review, and a source-date edit cannot
   silently change an already approved plan.
9. Clinician records simulated visit completion. The patient has no remaining due
   item, while clinic-recorded completion remains in My records care history.
10. Verify different patients/clinics cannot read the originals or proposals;
    patient-only sessions cannot use clinic routes. Logout returns 401 for home.

The fresh final API run passed all steps, including three resolved document-review
tasks. Browser checks covered upload-error recovery, handwritten upload, source
comparison, duplicate rejection, required notes, automatic result/status refresh,
follow-up confirmation and preserved care history.

## Fixes found during this pass

- Added terminal `REVIEWED` for fully checked reports without an approved follow-up
  date. They no longer remain indefinitely in the To review inbox. Approved
  follow-up dates still require explicit plan approval.
- Added polling for clinic changes to analysis, home care plans and My records.
- Resolve only the report's matching document-review task after review/plan
  completion or rejection. Other tasks remain untouched.
- Outstanding health fields remain reviewable after plan approval. Already
  approved plan dates require the plan editor for changes.
- External Listen/TTS now requires recorded AI-processing consent, both in
  availability and on the audio endpoint. Tests verify no provider call without
  consent and successful delegation with consent.
- Patient My records now shows permission-filtered clinic plan/completion events
  even after a completed plan is no longer active.
- The reminder preference label now follows recorded consent as well as opt-out,
  instead of saying reminders are enabled when no consent has been given.

Validation: **199 PostgreSQL/Alembic tests**, two frontend trend tests and final
frontend production build/type checking passed. Current real SMS delivery,
physical microphone/camera, physical APK update and hosted Render acceptance are
still manual checks. The hosted Free profile uses Tesseract rather than the heavy
local hybrid worker; repeat hosted document acceptance after deployment.

Local test receipts and screenshots are outside Git under
`D:/niyamit/verification`. Fictional test records are retained for review.
