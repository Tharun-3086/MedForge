# Latest local update: table OCR fix (27 November 2026)

Automatic now selects the eligible printed-PDF fast path without a manual
Printed selection. All 215 backend tests passed, including OCR-routing guards.
Actual default-style patient/clinic lab PDF uploads extracted in 0.489/0.166
seconds on an isolated synthetic QA patient. Reviewed values matched across
both APIs. Local backend/worker rebuilt; no Git push or hosted deployment.

Printed PDF latency fixed locally: pure text PDFs explicitly marked Printed can
skip heavy OCR, and supported source-linked rules skip unnecessary external AI.
208 backend tests passed. Existing pending glucose PDF recovered without a new
upload or automatic approval; patient shows 142/190 mg/dL awaiting clinic review.
Actual fixture extraction-only timings: PDF 0.038s, cold-model PNG 23.787s.

Same-day clock ordering added: report date, clinic-approved collection/report
time, then upload time. The clock is a separately reviewable field and appears
on shared patient/clinic reading cards and history. 205 backend tests, two trend
tests and frontend production build passed. Local services updated. Intraday
charts and mixed-zone clock conversion are not included. No Git push or deploy.

Fixed baseline grouping of printed table cells before left-to-right ordering.
202 backend tests passed. Live local PDF and PNG acceptance extracted all ten
lab measurements in each format; patient and clinic showed identical reviewed
health records. Synthetic cursive follow-up date extraction and verification-note
gating passed. The new 11 December item is confirmed but not completed. Actual
historical handwriting remained unverified, without an invented follow-up;
real handwriting accuracy is not established. See niyamit/TABLE_OCR_CHECK.md.
No assistant Git commit/push, Render deploy or APK rebuild in this pass.

## Previous local update: extended report history (26 November 2026)

Final patient journey acceptance: 199 backend tests, two trend tests and final
frontend build/type check passed. Fresh actual uploads exercised printed,
cursive-font and PDF reports through clinical review, plan approval, patient
confirmation, document-task resolution and simulated clinician-recorded visit
completion. Access isolation and logout passed. Fixed stuck lab-review status,
pending health review after plan approval, document-task closure, automatic
patient refresh and AI-consent enforcement for Listen. My records retains
clinic-recorded care history. See PATIENT_FLOW_CHECK.md. Hosted/physical-device
acceptance remains separate; no Git push, hosted deploy or APK rebuild in this pass.

Release preparation: Ramesh's fixed public synthetic demo now has three clearly
watermarked fictional source reports and 36 fixture-verified measurements with
three-date trends. Additive initialization on demo startup preserves existing
records and skips non-demo/production. 196 backend tests passed. Hosted APK
0.3.0-demo/code 3 was built and signature-verified with the same certificate as
the previous APK. No install on a physical device/emulator was performed. Git
candidates passed sensitive-filename/current-secret-value checks. Full push,
merge, backend-first Render and APK release steps are in RELEASE_0.3_DEMO.md.
No push/merge/hosted deployment/public release was performed by the assistant.

Added serum creatinine, eGFR, UACR, total/LDL/HDL cholesterol, triglycerides and weight with explicit units. Patients and authorised clinic staff share source-linked history and latest values. Charts use only clinic-confirmed values/dates, keep units and glucose types separate, and exclude same-date conflicts and inequalities. Uncertain readings remain behind clinic verification; pending readings also prevent routine priority assignment. No automatic diagnosis or thresholds were introduced.

194 PostgreSQL/Alembic tests, two trend tests and the frontend production build/type check passed. Actual local Docker uploads produced 16 reviewed entries from two synthetic printed reports. A doctor verified a newer cursive-font creatinine result through the UI, and the confirmed value reached patient history/trends. Sarvam structured chat and a synthetic Document AI extraction succeeded without exposing keys or sending real patient data. Local images/services updated; no push, Render deployment or APK rebuild performed. READINGS.md documents rules, validation and the local source-image build fallback after a slow apt download.

---

# Earlier local update: hybrid OCR and verification (22 November 2026)

Patient visibility follow-up: moved the health summary above the large action tiles. HbA1c, blood glucose (with fasting/post-meal/random types kept separate) and blood pressure now have persistent patient-facing cards, including explicit missing-reading states and a direct upload button. Report dates, source details and clinic verification labels remain visible. These are report-based values, not continuous glucose monitoring or inferred clinical statistics. The shared Ramesh demo currently has no uploaded measurements; values are never copied from another QA patient.

Added optional local PaddleOCR and experimental English TrOCR, retaining Tesseract fallback. PDFs route per page, including scanned regions on native-text pages in hybrid mode. Uploads persist writing style and document language. Extracted fields preserve source coordinates, engine identity, confidence routing hints and conflicting alternatives.

Uncertain measurements stay out of latest patient readings until clinic verification. A doctor or nurse must supply a verification/correction note. Conflicting candidates and report-date alternatives require resolution. Patient and clinic interfaces expose upload options, uncertainty messages and source comparison.

Validation: 192 PostgreSQL/Alembic tests passed, frontend production build passed, and mocked mobile UI checks passed. Actual PaddleOCR and TrOCR were exercised through patient upload, extraction, review gating, staff correction and patient retrieval in an isolated PostgreSQL/API check using synthetic printed/cursive-font images. This is not real medical handwriting validation. Hindi/Telugu handwriting remains manual review. Medication interpretation, autonomous diagnosis, new clinical thresholds and longitudinal analysis were not added.

OCR.md documents setup, optional worker model preparation and limitations. No Git push or hosted deployment was performed. Deploy the migration/backend before the frontend. A heavier worker is required to enable the optional models; the small hosted API can retain its lightweight fallback.

Follow-up local Docker acceptance: safely purged disposable pip caches using pip's cleaner (about 3.84 GB on C and 0.89 GB on D), reset the temporary native test environment, and moved future pip caching to D:/Caches/pip. Docker WSL data already targets D:/Docker/wsl via its existing junction. A database backup was saved before applying the additive migration. The heavy worker image now builds and runs; real offline PaddleOCR/TrOCR/fallback container checks passed.

Actual browser uploads through the Docker app passed for synthetic printed and cursive-font reports. Printed BP/glucose/HbA1c reached the patient; the uncertain cursive reading was withheld until a nurse checked the original and recorded confirmation/correction notes, after which the newer clinic-reviewed glucose appeared. TrOCR's incorrect unit stayed visible as alternative evidence. Fixed a raw technical review label. The local hybrid stack remains running; no Git push or Render deployment was performed. Real clinical handwriting accuracy remains unvalidated.

---

# Latest local update: patient OTP retries and demo recording kit

The friend reported too many requests after Send SMS code. Inspection found that premature taps and failed provider sends consumed process-memory phone/IP quotas, with a misleading one-minute message for an hour-long limit. The exact provider response from the friend's attempt was not available, so a provider throttle/trial restriction cannot be excluded.

The fix moves successful per-phone send accounting into PostgreSQL (one/minute, five/hour) with row locking and an additive Alembic migration. Cooldown taps do not consume send allowances, failed provider sends preserve the previous challenge, and provider outages do not count as incorrect OTP attempts. The shared-network backstop permits 120 possible sends/hour, with a separate coarse verification limit and the existing five-attempt challenge guard. Rate limits remain enabled. Generic and provider throttles now supply accurate/bounded Retry-After. Twilio trial errors explain recipient verification.

The login UI restores pending challenges and countdowns across reloads, never saves entered/development OTPs, keeps code verification available during normal resend cooldown, and handles provider check blocks and expiry without automatic resend. This is a hosted UI change, so the existing APK can load it after reload.

Validation: 171 backend tests passed, frontend type checking and production build passed, and four browser retry/restore scenarios passed with mocked APIs. No real SMS was sent for these tests. This update is not yet committed, pushed or deployed by the assistant. Deploy backend migrations before the frontend, then verify real delivery manually. Multi-instance production still needs shared infrastructure and correct proxy identity handling.

DEMO_VIDEO.md contains a three-minute shot list and narration for patient OTP, a synthetic report scan, clinic source review and patient confirmed results. The PDF/PNG fixtures are under niyamit/docs/demo-assets. The PNG was read by local Tesseract with the expected BP, glucose and HbA1c. The recording kit is also under D:/niyamit/demo-video. No finished walkthrough video has been recorded yet.

---

# Live Render acceptance: patient upload and clinic review

Live URLs: https://niyamit-app.onrender.com (frontend), https://medforge-rg8q.onrender.com (API). Tested with fictional patients and generated documents only. Health, real clinic login, secure session cookies, patient access-link login, correct public link origin, image upload through mobile UI, Tesseract readings (BP 120/80 mmHg, fasting glucose 110 mg/dL, HbA1c 6.2%), private original download, clinic date correction and follow-up plan approval through UI, patient results with immutable automatic values separate from reviewed information, cross-clinic/patient denial and CSRF protection passed. Image upload plus processing took 8.6 seconds for the generated 1600x1000 test image; this is a sample measurement, not a performance guarantee.

SMS delivery and real OTP sign-in were explicitly deferred by the user. Live OTP configuration reports available=true/development=false; invalid random challenges return 401, but this does not prove SMS delivery or valid-code login. No SMS was sent. Voice, AI translation quality, restart persistence and reminder timing were not tested in this pass.

Found a live clinic UI defect: health-reading corrections used date inputs, and corrected numeric history was passed to date formatting. Fixed locally: date inputs remain for document/follow-up dates; other values accept text/units; history uses the field display formatter. Type checking and a production build passed. BP, glucose and HbA1c corrections were exercised in the local production frontend against the live API; patient reviewed values/latest readings updated and retained separate originals. A generated prescription PDF also uploaded, extracted via its text layer, and downloaded unchanged. These local frontend fixes are NOT deployed; the assistant did not commit or push. The earlier modern Supabase secret-key compatibility changes are also still local; origin/main remains b6b57ec at time of verification.

Verification scripts/results/screenshots are outside Git under D:/niyamit/verification. Preserve synthetic QA records as test evidence; do not treat them as real clinical records.

---

# Latest local fix: modern Supabase secret keys

Storage now sends modern sb_secret_ keys on the apikey header only; legacy service_role JWTs retain Bearer compatibility. The existing SUPABASE_SERVICE_ROLE_KEY setting accepts either format. Deployment guidance now recommends modern secret keys and retiring exposed legacy credentials. This compatibility fix is not committed or pushed by the assistant.

---

# Latest update: Render Free and private Supabase storage

Prepared an opt-in Supabase Storage adapter: originals remain Fernet-encrypted, downloads use the authenticated private-object API, and upload failures never fall back to ephemeral disk. Local storage remains the default. Object keys are validated; remote errors return a generic 503 without credentials/provider details.

Added `python -m app.render_start` for the synthetic Render Free profile: startup validation, Alembic migration, RLS/grant protection on application tables, seed only when the database is empty, then one Uvicorn process on PORT. Small connection pools, eager jobs, inline scheduling and conservative upload limits are documented in `niyamit/backend/.env.render.example`. Supabase Data API must be disabled before first deployment; Storage stays enabled. `niyamit/RENDER_FREE.md` gives exact Git, Supabase, backend/frontend Render and hosted acceptance steps.

Validation: 160 backend tests passed; Docker image `niyamit-render-check` built. Remote HTTP storage is mocked in automated tests, with real local PostgreSQL migrations and Tesseract. Patient upload -> original download -> clinic field review -> patient reviewed result and cross-clinic denial passed. Repeat startup preserves clinics. Source-candidate scan found no configured secret values; real environment files remain ignored.

Live Supabase/Render deployment and hosted persistence/phone acceptance are NOT completed: private values must be entered into the hosting dashboards, and source must be pushed/merged by the user first. No assistant commit or push was performed. Free services sleep and cannot guarantee timed reminders, retention deadlines, availability or real-patient production suitability.

---

# Latest update: demo subscriptions and hosted deployment

Clinic admins can select illustrative INR/month plans based on current active follow-up patients, with persistent SIMULATED_NO_PAYMENT history. No merchant account, tax invoice, charge or automatic renewal is implemented. Care records remain accessible. Activation is disabled outside demo mode.

Both READMEs were rewritten. BILLING.md defines usage/prices; HOSTED_DEMO.md and compose.hosted.yml provide a server-hosted HTTPS demo configuration independent of the laptop. Compose/Caddy config validation passed. Real server deployment and production acceptance remain outstanding. Backend suite: 134 tests passed.

No assistant Git commit or push was performed for these changes.

---

# Latest local update — staff onboarding and mobile roles

The original release was pushed and merged by the user. New work is on `feature/clinic-staff-onboarding` and has not been committed or pushed by the assistant.

- 125 backend tests passed; updated frontend type checking and production build passed.
- Clinic administrators can invite ordinary staff, who set their own passwords; invitations expire and are single-use. Admins can revoke access immediately.
- Private non-demo clinic provisioning creates an initial admin and draft message templates. Real-clinic patients are not marked synthetic or allowed through development OTP.
- Patient registration is available in the clinic UI, with consent unchecked by default.
- One responsive app supports Patient and Clinic entry points, mobile clinic quick navigation and backend-enforced roles.
- Confirmation and difficulty actions passed locally. Listen now has loading feedback and a visible player for browsers that block automatic playback. Errors are visible on the difficulty screen.
- Public HTTPS retest passed on the replacement tunnel: patient OTP, report scanning, clinic review, staff invitation/acceptance, patient registration and immediate staff revocation. See TESTING.md for details.
- Real SMS, account recovery, production hosting/security/clinical approval and physical microphone acceptance remain outstanding.

See `niyamit/README.md`, `niyamit/TESTING.md` and `niyamit/DEPLOYMENT.md` for current instructions, including database inspection.

---

# Release status — 2026-11-05

## Ready for GitHub and local demo deployment

Patient and clinic interfaces run together in the Docker stack. The patient app supports development phone OTP for synthetic records, report upload, original-file access and separately labelled automatic analysis and clinic-reviewed information. Tesseract is the default OCR; Baidu remains optional and is stopped locally.

Release preparation includes refreshed setup/deployment/testing/security documentation, GitHub CI, locked frontend installation, a pinned backend dependency snapshot, enforced TypeScript builds and production startup/demo-seeding safeguards. The obsolete ZIP source snapshot has been moved outside the working tree. No commit or push was performed.

## Verified locally

- Backend: **121 tests passed**, including migrations, tenant/access controls, OTP, analysis ownership and production configuration guards. One Starlette/httpx test-client deprecation warning remains.
- Frontend: TypeScript check and Docker production build passed.
- Dependency audits: frontend production dependencies and pinned Python dependencies reported no known vulnerabilities at check time.
- Live browser: synthetic patient OTP login, wrong-code rejection, prescription upload, Tesseract OCR, original download, clinic correction/approval, preserved automatic analysis, separate reviewed information and logout access denial passed.
- Live scan used Tesseract plus the configured Sarvam document extractor; it was not a claim of fully offline or clinically validated interpretation.
- Compose validation and local service health passed. Baidu is not running.
- Candidate-file scan found no configured secret values/private-key markers and no files over 5 MB. This is not a full historical Git secret audit.

GitHub-hosted CI has not run yet because nothing has been pushed. Manual emulator microphone/camera acceptance and external deployment are not claimed.

## Outstanding before real-patient production use

Real SMS OTP integration, clinical/native-language approval, production account provisioning, HTTPS/infrastructure/security review, backup restore rehearsal and real-device acceptance remain required. The supplied Compose file uses public demo credentials and is for synthetic data. See [deployment gates](niyamit/DEPLOYMENT.md).

## Historical release publishing commands (already completed by the user)

From PowerShell:

```powershell
cd D:\niyamit\MedForge-Git
git status
git add .
git diff --cached --check
git diff --cached --stat
# Review the staged changes before committing.
git commit -m "Prepare Niyamit patient and clinic demo for deployment"
git push -u origin kiran/backend-infrastructure
```

Remote verified: `https://github.com/Tharun-3086/MedForge.git`. The local branch is `kiran/backend-infrastructure`; it did not already exist on the remote when checked. Do not force-push. Secrets and local build/model artifacts are ignored.


## Diabetes intelligence audit and first increment — 27 November 2026

- Audit and architecture/requirements/schema/security/operations/validation documents added at repository root; see PROJECT_AUDIT.md and TEST_REPORT.md.
- Structured medical measurement proposals now flow from Sarvam/OpenAI schema through source/unit/date validation and rule reconciliation; unknown parameters are retained for non-approvable manual review. Explicit local document processing cannot select an external LLM.
- Shared English monitoring summary with source links, comparable reviewed-history changes and audited JSON export; patient-scoped duplicate-upload reuse; original/review preservation.
- 242 PostgreSQL tests passed; frontend production build/type checks and 2 trend tests passed. Live synthetic patient upload → hybrid OCR + Sarvam → source-checked test review → matching patient/clinic readings and export passed; duplicate reused. No real patient records sent externally in these checks.
- Local services rebuilt/restarted. No GitHub push, Render deployment or APK update. Clinical validation and production gates remain open, as do medication/CGM/screening/target/full portability workflows.
