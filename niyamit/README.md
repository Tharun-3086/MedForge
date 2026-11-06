# Niyamit Care Bridge

Niyamit connects a patient web app to a clinic workspace. Patients can sign in, upload reports, see extracted information, exchange messages and send voice replies. Clinic staff review the same records and explicitly confirm extracted fields and follow-up plans.

## What works

- Separate patient and clinic entry points, with role and clinic access checks.
- Phone login using **development OTP for synthetic records only**; clinic-issued links remain supported.
- Patient dashboard with report/prescription upload, original-file access and analysis status.
- Separate **automatic, unverified analysis** and **clinic-reviewed information**. AI extraction does not approve treatment or a care plan.
- Clinic intake review, corrections, approved plans, follow-ups, booking requests and messaging.
- Telugu/Hindi/English reply flows and English meaning display; live speech/translation depend on configured providers.
- Encrypted uploaded artifacts, migrations, worker jobs, retries and automated tests.
- Tesseract OCR by default. Baidu is optional experimental code, not required for startup.

## Quick start

From the Git repository root:

```powershell
cd niyamit
Copy-Item backend/.env.example backend/.env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the generated value into `SECRET_KEY` in `backend/.env`. Keep this file private. Do not change this key after storing documents unless you have preserved the encryption key and planned a migration.

```powershell
docker compose up -d --build --wait
docker compose ps
```

Docker Desktop must be running with Linux containers. Initial downloads require network access and disk space. Node/Python on the host are only needed for host-side development/checks. Linux/macOS users substitute `cp` for `Copy-Item`.

Open http://localhost:3000. API health: http://localhost:8000/healthz; API documentation: http://localhost:8000/v1/docs.

## Try both sides

1. Open `/login`, sign in as `nurse@sunrise.demo` with password `niyamit-demo`. Other demo roles include `doctor@sunrise.demo` and `admin@sunrise.demo` with the same password.
2. In a separate browser context, open `/patient`. Enter synthetic phone `+919000000101`, request a test code and enter the code displayed on screen. **This is not SMS delivery.**
3. Choose **Scan a report**, select the document type and upload a clear, synthetic PNG/JPEG/PDF. Use no real patient data in demo mode.
4. Open **View analysis**, then **Refresh analysis** while the background job completes. Automatic extraction must be labelled unverified; the original remains available.
5. In the clinic, review the pending intake for that patient. Correct a field, confirm the reviewed fields and approve the appropriate follow-up plan.
6. Refresh the patient analysis. The clinic-confirmed result must appear separately from the original automatic extraction.
7. Send a patient text reply, then check the same patient's clinic message history. Repeat with Telugu/Hindi; check the displayed English meaning against the intended message.
8. For voice, allow browser microphone access and record a short sentence in a quiet room. Check transcription and meaning before treating it as correct. If recognition fails, retry or type the message.

The patient must already have a clinic record. Development OTP cannot open non-synthetic records. If the same phone belongs to multiple clinic profiles, the patient chooses the intended clinic explicitly.

## Android emulator

This repository provides a responsive **web app**, not a native Android APK. Open it in emulator Chrome.

```powershell
& "D:\Android\Sdk\platform-tools\adb.exe" reverse tcp:3000 tcp:3000
```

Adjust the SDK path on another machine. Then type `http://localhost:3000/patient` directly in emulator Chrome; no patient link is needed for OTP login. Keep the clinic open at `http://localhost:3000/login` on your laptop. Re-run port reversal after restarting the emulator. Localhost is important for microphone permissions; an HTTP LAN IP may not permit recording. Physical microphone quality still needs a user test.

## Configuration

All server secrets belong in `backend/.env`, never `NEXT_PUBLIC_*`, Git, screenshots or logs.

| Setting | Purpose |
| --- | --- |
| `OCR_PROVIDER=local` | Default local OCR; no Baidu service required |
| `DOC_PROVIDER=local` | Deterministic local extraction; use this for an entirely offline document path |
| `DOC_PROVIDER=sarvam` | Optional document understanding with a configured key; local extraction remains available |
| `LLM_PROVIDER=rules` | Offline reply interpretation; limited language coverage |
| `ASR_PROVIDER=none`, `TTS_PROVIDER=none` | Disable external speech services |
| `SARVAM_API_KEY` | Optional live speech, translation/understanding and document provider |
| `PATIENT_OTP_PROVIDER=development` | On-screen test codes, synthetic records only |
| `PATIENT_OTP_PROVIDER=disabled` | Disable phone OTP when no SMS provider is configured |
| `PUBLIC_APP_URL` | Address used when generating patient links |
| `DEMO_MODE=true` | Synthetic accounts, simulated channel and test controls |
| `SECRET_KEY` / `STORAGE_ENCRYPTION_KEY` | Authentication and artifact encryption; preserve securely with backups |

Missing provider keys must not be represented as successful speech/translation. Tesseract works best on clear printed text; the image includes its default English language data. Handwriting, skewed photos, regional-script prescriptions and drug doses require careful human review. The application extracts information; it does not establish medical accuracy.

## Architecture and source

```text
Browser / emulator Chrome
  -> Next.js :3000 (patient + staff UI, /api proxy)
     -> FastAPI :8000 -> PostgreSQL
                     -> Redis -> Celery worker/scheduler
                     -> encrypted artifact volume
                     -> optional external AI/channel providers
```

- `frontend/app`: routes and responsive UI; `components/patient`: patient dashboard and analysis.
- `backend/app/routers`: authenticated API routes.
- `backend/app/services`: OTP, clinic workflows, messages and review logic.
- `backend/app/ai`: provider adapters and local extraction.
- `backend/alembic`: database migrations; `backend/tests`: isolated test suite.
- `docker-compose.yml`: local demo stack; optional Baidu overlays are separate.

## Development and verification

```powershell
docker compose exec -T backend pytest -q
cd frontend
npm ci
npm run typecheck
npm run build
npm audit --omit=dev
```

Run tests against disposable development infrastructure only. The test suite creates/resets a separate database ending in `_test`. Docker builds enforce TypeScript correctness; frontend dependency installation uses `npm ci`. Backend Docker dependencies are constrained by `backend/requirements.lock` (Linux/Python 3.13); regenerate and audit this snapshot deliberately when upgrading.

For frontend hot reload, stop the Compose frontend and run `npm run dev` from `frontend`, setting `BACKEND_INTERNAL_URL=http://localhost:8000` in the shell. Keep the backend/worker/database running. API rewrite destinations are fixed at build time for production builds.

See [TESTING.md](TESTING.md), [DEPLOYMENT.md](DEPLOYMENT.md) and [../SECURITY.md](../SECURITY.md) for acceptance and deployment details.

## Current limitations

Twilio Verify SMS integration is implemented but requires configured credentials and live delivery acceptance; do not enable development OTP for real patients. Live speech/translation require provider credentials, connectivity and consent. Real WhatsApp delivery and native Android packaging are not release-verified. Clinical and native-language template approval, production infrastructure/security review, backup restore rehearsal and physical microphone testing remain launch gates. No regulatory certification or medical accuracy claim is made.

## Clinic patient registration and staff approval

Clinic users open **Patients → Add patient** to register a patient. Consent boxes start unchecked and must reflect the patient's actual agreement. A patient inherits the clinic's synthetic/real status; development OTP cannot authenticate a real-clinic patient.

A clinic **administrator** opens **Settings → Clinic staff access**, enters the new staff member's name/email, selects Nurse, Doctor or Reception, and creates an invitation. Privately share the generated link with the verified intended person. No email is sent automatically. The link expires in 24 hours, works once, and lets the recipient choose their own password before signing in at `/login`. Reissuing an invitation invalidates the previous one. Admins can cancel pending invitations and revoke ordinary staff access immediately, including existing sessions. Other roles cannot manage staff. Administrator/operator privileges cannot be granted or removed through this screen.

Existing-account clinic transfers, password recovery and administrator succession are not implemented. The public demo still uses synthetic clinics and public demo credentials; do not use it for real clinic identities or patient information.

For a new non-demo clinic, see the private provisioning command in [DEPLOYMENT.md](DEPLOYMENT.md).

## One app on mobile

Open `/` to choose Patient or Clinic in the same application. Patient and staff sessions remain separate, and backend permissions determine access. Clinic mobile screens include quick navigation for Today, Patients, Reports and Tasks (filtered by role), plus a full Menu and Switch app link. The manifest launches the shared entry point. This is a responsive web app/home-screen experience, not a native Android APK or an offline medical-record store.

Patient Listen now shows audio preparation status and a player with manual Play/Pause controls if the browser blocks automatic playback. Reply action errors are visible on all patient views, including difficulty selection. The original confirmation and barrier workflows remain server-validated.

## Real SMS setup

Twilio Verify is supported with local challenge limits and provider approval checks. See [SMS_SETUP.md](SMS_SETUP.md). No account credentials or live SMS delivery were available during automated testing. The default remains development OTP.

## First-use tour and mobile reports

A skippable three-step introduction appears once per browser profile and can be reopened through App tour. Reports use labelled cards below 700px; desktop keeps the table. Other clinic tables scroll within their container rather than squeezing words into single-character columns.

## New clinic owner signup

Clinic owners can open `/register-clinic` from the welcome or login page, enter clinic details and choose their administrator password. Signup immediately creates an isolated clinic and signs its owner in as ADMIN. It never joins an existing clinic or changes another account. In demo mode the new clinic is synthetic. Templates begin as drafts. Email addresses and professional credentials are not verified by signup.

The new administrator opens Settings > Clinic staff access to invite doctors, nurses or reception staff. Staff use the private invitation to set their password, then sign in at `/login`; they do not create another clinic. Existing account transfers, email verification and password recovery remain separate outstanding work.
