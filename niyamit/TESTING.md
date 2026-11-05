# Verification and manual acceptance

## Automated commands

Run from `niyamit/`, with a disposable local stack running:

```powershell
docker compose exec -T backend pytest -q
cd frontend
npm ci
npm run typecheck
npm run build
npm audit --omit=dev
```

Tests use a separate `_test` database and offline providers. They cover clinic isolation, roles, reminders, retries, patient access, OTP expiry/attempt limits/single use, multi-clinic selection, document ownership, separation of automatic and reviewed values, and OCR failure handling. New release tests check HTTPS/secure-cookie requirements and disabled demo seeding.

GitHub CI uses the same Docker build and backend suite, TypeScript checks, frontend dependency audit and HTTP smoke checks. It has not run remotely before the first push.

## Local release evidence (2026-11-05)

- Frontend TypeScript check: passed.
- Backend pinned dependency audit (`pip-audit --no-deps --disable-pip`): no known vulnerabilities reported.
- Frontend production dependency audit: zero reported vulnerabilities after the PostCSS override.
- Live headless Edge patient/clinic flow: passed with a synthetic printed prescription, Tesseract OCR and configured Sarvam extraction.
- The browser flow checked invalid OTP rejection, patient/staff separation, upload, original download, unverified analysis before review, clinic UI correction/approval, preserved automatic value, separate reviewed value and access denial after logout.
- No SMS was sent. This browser run was not an emulator hardware test.
- Earlier generated-audio checks exercised speech handling; physical microphone acceptance remains manual.

Final backend/build verification results are recorded in `../current_status.md`.

## Manual acceptance

1. Use synthetic records only; start from the README demo accounts and patient number.
2. Patient: request a development code, reject a wrong code, then log in correctly. Verify logout prevents reopening private documents.
3. Upload a clear printed prescription. Check processing status, OCR text, original and unverified label. Confirm a clinic correction does not silently rewrite the original automatic value.
4. Upload a synthetic lab report and verify values/units against the image. Check a blank/unsupported/oversized file gives an understandable failure rather than invented success.
5. Clinic: review the same patient and document; correct a field and approve a plan. Patient: refresh and verify reviewed information and follow-up cards.
6. Patient: send English, Telugu and Hindi messages. Clinic: check originals and English meanings for negation, dates and urgency. Confirm the meaning yourself; successful HTTP responses do not establish translation accuracy.
7. In emulator Chrome at localhost, allow microphone access, speak clearly, send the recording and check the transcript. Test silence and denied permission. Repeat with a real phone over HTTPS before release.
8. Test another clinic account cannot read this patient's document. Test multiple clinic profiles for one phone require explicit selection.
9. Restart the services and verify existing records/originals survive. Rehearse backup restoration in a separate environment before real deployment.

Do not mark manual microphone, real SMS/WhatsApp, handwriting accuracy, external production deployment or clinical approval complete based on automated tests.
