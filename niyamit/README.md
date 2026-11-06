# Niyamit Care Bridge

Patient care and clinic coordination in one responsive web application. The shared entry page supports separate authenticated patient/staff sessions and backend clinic isolation. The home-screen manifest launches `/`; the Android debug shell is documented below; offline records and iPhone builds are not implemented.

## Features

- Twilio Verify SMS login or clearly labelled development OTP. Development OTP opens synthetic records only and is rejected in production.
- Immediate clinic-owner signup with administrator access and isolated records.
- Role-specific staff invitations, private password setup and immediate access revocation.
- Patient uploads, encrypted originals and separate automatic/clinic-reviewed results.
- Clinic patients, tasks, report review, appointments, messages, settings and audit history.
- Telugu/Hindi/English flows, English meanings and optional speech recognition/read-aloud with playback controls.
- Tesseract OCR by default; optional Baidu code is experimental.
- Mobile report cards, clinic quick navigation, first-use tour and a reduced-motion-aware logo intro.
- Demo monthly clinic subscriptions in INR with active-patient usage and simulated billing history.

## First setup

Install Docker Desktop with Linux containers. Enter niyamit/ from the Git root:

```powershell
Copy-Item backend/.env.example backend/.env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy only on first setup. Save the generated SECRET_KEY in backend/.env. Preserve encryption configuration after uploading files; changing it can make originals unreadable. Never commit credentials. Linux/macOS users substitute `cp`.

```powershell
docker compose up -d --build --wait
docker compose ps
```

Open http://localhost:3000/. API health: http://localhost:8000/healthz; docs: http://localhost:8000/v1/docs. Initial builds require downloads and disk space.

## Accounts

Patients open `/patient` using their clinic-registered number. Development mode displays a test code without SMS; Twilio mode sends real SMS. Multiple profiles require a clinic choice. Phone verification does not automatically share records across clinics.

Owners open `/register-clinic` and choose a password of at least 12 characters. They become ADMIN immediately. Demo clinics remain synthetic; templates start as drafts. Signup does not verify email ownership or professional credentials.

Admins invite Nurse/Doctor/Reception staff from Settings > Clinic staff access. Links expire after 24 hours and work once. Recipients set their password and sign in at `/login`. No email is automatically sent. Staff should accept an invitation rather than create another clinic. Existing-account transfers, administrator succession and account recovery are not implemented.

Public synthetic demo accounts use password `niyamit-demo`:

| Role | Email |
| --- | --- |
| Admin | admin@sunrise.demo |
| Nurse | nurse@sunrise.demo |
| Doctor | doctor@sunrise.demo |

With development OTP, seeded phone +919000000101 is fictional, not a real SMS destination. Live SMS testing uses your verified phone against a fictional profile. Never upload real health information to a demo.

## Connected acceptance test

1. Use separate browser profiles for clinic and patient.
2. Patient uploads a fictional prescription/report and opens its original/analysis.
3. Clinic checks the same document, corrects a field and approves an appropriate plan.
4. Patient refreshes and sees the original automatic value separately from reviewed information.
5. Send multilingual messages and check originals/English meanings, especially dates, negation and urgency.
6. Over HTTPS/localhost, allow microphone access, record a short sentence and check transcription. Test Listen and manual Play.
7. Register another clinic, invite/revoke staff and check record isolation.
8. Admin opens Subscription and simulates a plan selection. No money is collected.

Extraction can contain errors. It does not diagnose conditions, establish medication safety or approve treatment. Physical-device acceptance differs from browser viewport/generated-audio checks.

## Configuration

| Setting | Purpose |
| --- | --- |
| APP_ENV / DEMO_MODE | Demo versus guarded production startup |
| SECRET_KEY / STORAGE_ENCRYPTION_KEY | Authentication/encryption keys; preserve with backups |
| PUBLIC_APP_URL / COOKIE_SECURE | Generated links and HTTPS cookies |
| PATIENT_OTP_PROVIDER | development, twilio or disabled |
| TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_VERIFY_SERVICE_SID | Private SMS credentials |
| OCR_PROVIDER=local | Tesseract/local reading |
| DOC_PROVIDER=local | Local document extraction |
| DOC_PROVIDER / LLM_PROVIDER | Optional external interpretation or local/rules fallback |
| ASR_PROVIDER / TTS_PROVIDER | Optional speech providers; none disables them |
| SARVAM_API_KEY / OPENAI_API_KEY | Server-only provider credentials |
| WHATSAPP_ENABLED | Optional real channel; demo uses simulated messaging |

Provider charges are separate from simulated subscription prices. Tesseract works best on clear printed text; bundled language data is English. Handwriting, regional-script documents and clinical interpretation require review. Provider failures must not be presented as successful speech/translation.

## Mobile and development

Open the same app in mobile/emulator Chrome. Use `adb reverse tcp:3000 tcp:3000` for emulator localhost. This laptop's SDK is D:/Android/Sdk. Physical phones need the public HTTPS address. Laptop tunnels depend on laptop power/internet; see HOSTED_DEMO.md for independent hosting.

```text
Browser/mobile -> Next.js app and /api proxy -> FastAPI
 -> PostgreSQL, Redis/Celery, encrypted artifacts, optional providers
```

Source is in frontend/app, frontend/components, backend/app/routers, services and ai. Migrations: backend/alembic. Tests: backend/tests. Laptop stack: docker-compose.yml. Hosted demo: compose.hosted.yml.

```powershell
docker compose exec -T backend pytest -q
cd frontend
npm ci
npm run typecheck
npm run build
npm audit --omit=dev
```

Tests reset a separate database ending in _test; use development infrastructure. Provider tests run offline/mocked by default. Frontend Docker builds enforce TypeScript and npm ci; Python uses requirements.lock constraints for Linux/Python 3.13. For hot reload, stop the Compose frontend, set BACKEND_INTERNAL_URL=http://localhost:8000 and run npm run dev. Production rewrites are fixed at build time.

## Deployment and limits

See [HOSTED_DEMO.md](HOSTED_DEMO.md), [DEPLOYMENT.md](DEPLOYMENT.md), [BILLING.md](BILLING.md), [SMS_SETUP.md](SMS_SETUP.md) and [TESTING.md](TESTING.md).

The demo is deployable; it is not a certified real-patient production service. Remaining requirements include email verification/account recovery, clinical/native-language approval, real-device acceptance, restore rehearsal and operational/security acceptance. Real payments, tax invoices, refunds, proration and recurring charges are absent from demo subscriptions.

## Android debug APK

A native Android shell now packages the existing patient and clinic web interface. See [android/README.md](android/README.md) for building, emulator setup, HTTPS configuration and limitations. It is a debug/test APK requiring the web backend, not a native UI rewrite or a store release.

Android 10+ is supported by the shell. The SDK-only Windows build was executed and its APK signature verified; the Gradle wrapper checksums were verified but a full Gradle dependency build has not been executed. Camera, native file chooser, physical microphone and download behavior still need device acceptance. iPhone support is not implemented.

On this laptop, from the Git root:

```powershell
cd niyamit/android
.\build-debug.ps1
& "D:\Android\Sdk\platform-tools\adb.exe" reverse tcp:3000 tcp:3000
& "D:\Android\Sdk\platform-tools\adb.exe" install -r .\build\Niyamit-debug.apk
```

Start the emulator and Docker web stack first. Open Niyamit from the emulator app list. The default URL is localhost:3000 through adb reverse. A phone needs its own adb reverse connection or an APK configured for a reachable HTTPS origin. Build outputs and signing keys are ignored; publish source through Git, not a debug keystore or generated APK.

## Latest patient health readings

The patient dashboard retains latest BP, fasting/post-meal/random/unspecified glucose and HbA1c readings with units and source-report links. New OCR processing adds these values as individually reviewable fields. Older existing OCR text is considered as unverified fallback. Rejected/deleted/failed reports are excluded. New dated readings replace older values per measurement; a report missing BP does not erase prior BP. Undated readings do not replace an existing dated value. Unverified report dates are labelled; uploads are never represented as measurement dates. Ambiguous values, reference ranges and missing units are not guessed. Clinic corrections/approval update the reviewed label, independently of follow-up-plan approval. This is a source-linked summary, not diagnosis or guaranteed OCR accuracy.

Readings refresh while the dashboard is open and can be refreshed manually. Inspect the original and verify the patient, date, value and units before using a number clinically. BP requires mmHg, glucose requires mg/dL or mmol/L, and HbA1c currently requires percent; values are not converted between units. Missing/unsupported readings remain absent rather than being filled with assumed normal values.

## Clinic follow-up priority

Today includes a patient priority panel: staff-flagged Urgent/High, Needs verification, staff-assessed Routine and Not assessed. Unverified OCR never automatically assigns clinical urgency or normality. No numeric medical thresholds are configured. Only Doctor/Nurse roles can set priority with a reason; Admin can view. Changes are audited and clinic-scoped.

Readings and source review status are visible beside the patient. Routine is blocked while readings are unverified or processing. New/changed reports or readings flag a previous routine assessment for review; existing urgent/high priorities persist until staff changes them. This does not create an emergency alert, follow-up deadline or new care task. Existing doctor-task workflows remain separate. The list is paginated, urgent/high first across pages; category counts/filters refer to the current page. Missing readings or Not assessed must never be interpreted as normal health.

To test, sign in as a synthetic doctor/nurse, open Today, select Assess priority for a patient and save a reason. Filter the current page by priority and verify the audit history. An administrator can view the panel but cannot assign a clinical priority through an administrator role. Reception/platform-operator roles cannot read this clinical panel. Review the source fields in Report inbox before assigning Routine.
