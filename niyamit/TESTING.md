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

## Staff onboarding and shared mobile app verification (2026-11-05)

The backend suite now passes **125 tests**. Added coverage verifies admin-only invitations, allowed roles, hashed single-use tokens, expiration/cancellation/reissue, cross-clinic denial, immediate session revocation, draft templates for new clinics and real-clinic patient exclusion from development OTP.

A local browser run passed admin invitation creation, recipient password setup/login, staff role restriction, patient registration with consent unchecked and immediate access revocation. Mobile clinic navigation and shared Patient/Clinic entry were checked at 393px width. Confirmation and difficulty actions completed; Listen returned audio and the visible player loaded it. Physical speaker/microphone acceptance remains manual.

The public Cloudflare patient report workflow passed earlier in this session. The old temporary hostname subsequently stopped resolving; final updated UI checks are local until a new tunnel URL is supplied. No new Git push was performed.

## Public HTTPS retest — 2026-11-05

After the laptop restart, the new Cloudflare tunnel was verified and PUBLIC_APP_URL updated locally. Both browser workflows passed over the public HTTPS origin:

- Development patient OTP login, wrong-code rejection and staff-access separation.
- Synthetic prescription upload, original download and unverified analysis before review (Tesseract OCR plus configured Sarvam extraction).
- Clinic field correction and plan approval through the UI; patient sees the preserved automatic value separately from the reviewed value; logout denies original access.
- Administrator creates a role-specific invitation on the correct public hostname; recipient sets a password and signs in; non-admin staff cannot manage invitations.
- New staff registers a synthetic patient through the UI with reminder consent unchecked by default.
- Admin revokes the test staff membership; the existing session immediately loses patient access.

No real SMS was sent and no physical microphone/emulator hardware test was performed. Test staff access was revoked after verification. Synthetic QA records remain identifiable by their QA names. No Git commit or push was performed.

## Twilio Verify integration — 2026-11-06

130 backend tests passed, including mocked Twilio send/check, invalid and reused codes, no development-code exposure, provider failures, and real-mode record authentication after provider approval. The suite forces development OTP and blank SMS credentials by default, so test runs cannot send paid SMS. Live delivery remains untested until the user configures a Twilio account.

Mobile report cards and first-use tour checked at 390px width: no page overflow, labelled report rows, desktop table preserved, Skip/completion persistence/replay passed. This is browser viewport testing; physical iPhone Safari acceptance remains manual.

Immediate clinic signup tests cover creation of an isolated empty clinic, administrator permissions, draft templates, password login, duplicate prevention, invalid passwords and preservation of existing accounts. Live SMS login was confirmed by the user on 2026-11-06 after rotating/configuring the Twilio token.

## Demo billing and hosted deployment — 2026-11-06

Full backend suite: 134 passed (one existing test-client deprecation warning). Billing coverage checks admin permissions, tenant isolation, server-side price selection, duplicate-selection suppression and non-demo activation denial. Frontend TypeScript check passed. Hosted Compose and Caddy configurations validated locally; no real domain/server deployment or certificate issuance has been performed.

Mobile browser billing acceptance passed: administrator selects Starter, no-payment labels are visible, selection/history persist after reload, and the page has no horizontal overflow. Updated Docker production build passed. No real payment was attempted.

## Android APK — 2026-11-06

SDK-only debug APK build and apksigner verification passed. Installed and launched on the API 37 emulator. WebView browser checks passed for welcome page, patient OTP interface, clinic password login and mobile role navigation. No new SMS was sent by this test. Native camera, file chooser interaction, physical microphone, downloads and real-device acceptance remain manual. Gradle wrapper checksums verified; a full Gradle dependency build has not been run. See android/README.md.

## Latest health readings — 2026-11-06

137 backend tests passed and the frontend production build/type check passed. Parser tests cover explicit units, glucose types, ambiguous duplicate readings, ranges and missing units. Summary tests cover report-date ordering, undated/older uploads, BP preservation, patient scoping and clinic corrections. Live browser acceptance uploaded two synthetic printed PNG reports through real Tesseract, checked automatic glucose update with BP retained, then corrected glucose via the clinic API and checked the patient reviewed badge. No diagnostic interpretation or physical device accuracy is claimed.

Clinic priority tests cover clinic/role restrictions, required reasons, no automatic classification of extreme unverified OCR, blocking routine before verification, and reassessment when report revisions change. Full suite before the final revision/pending refinements: 139 passed; focused priority/readings checks rerun afterward.

Final mobile browser acceptance passed: nurse saves a reasoned High priority assessment, filters the High queue, sees unverified reading labels and has no horizontal overflow. Updated frontend production build passed. Six focused priority/readings tests passed after the report-revision and pending-report refinements. No clinical numeric rules, emergency alerts or automatic care deadlines were enabled.
## Render/Supabase storage checks

`backend/tests/test_remote_storage.py` uses mocked Supabase HTTP responses and real local PostgreSQL/Tesseract. It verifies encrypted private upload/download/delete, invalid-key rejection, failures without local fallback, patient upload through clinic field review and patient results, cross-clinic denial, table protections, and repeatable Render preparation. Follow [RENDER_FREE.md](RENDER_FREE.md) for actual hosted acceptance, including file persistence after a backend restart.

## Clinic numeric correction regression

Upload a synthetic report containing labelled BP, glucose and HbA1c values with units. In Report Inbox, Correct must show a text editor for each health reading and a date editor for document/follow-up dates. Save a valid correction with a reason; the page must show the previous value with its units without a date-format exception. The patient must see the corrected clinic-reviewed value separately from the unchanged automatic reading. Confirm the latest health reading uses the reviewed value. The local production frontend passed these checks against the live Render API; the frontend patch still requires a GitHub push/merge and Render deployment.

The live image upload/clinic date review/plan approval flow also passed. SMS delivery/valid OTP login were deferred by the user; provider availability and invalid-challenge rejection alone do not count as an SMS end-to-end pass.
