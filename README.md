# Niyamit Care Bridge

One responsive application for patients and clinics: SMS OTP, prescription/report scanning, clinic review, follow-ups, multilingual messages, voice replies and clinic onboarding.

**Hybrid OCR:** optional local PaddleOCR for printed documents and experimental English TrOCR for handwriting, with Tesseract fallback. Mixed PDFs are processed per page. Uncertain health readings require clinic verification before replacing dashboard values. [Configuration, model preparation and limitations](niyamit/OCR.md).

## Free hosted demo

The [Render Free + Supabase guide](niyamit/RENDER_FREE.md) covers persistent encrypted cloud storage, backend/frontend setup and checks before sharing. It is a synthetic demo with free-tier sleep/usage limits, not a real-patient production release.

**Current release: deployable synthetic-data demo.** Twilio SMS login has been tested by the user. Subscriptions simulate billing and collect no money. Real-patient production requires the acceptance gates in the deployment guide.

On the Patient sign-in page, **Try demo patient — no OTP** opens the seeded Ramesh Kumar record at Sunrise Clinic without SMS. This is a shared synthetic account: use fictional uploads only. The entry is available only with `DEMO_MODE=true` outside production. Real patient phone sign-in still uses OTP.

## Android, health readings and clinic priority

- **Android debug app:** an installable Android 10+ WebView shell for the shared Patient/Clinic interface. Includes launcher branding, navigation, file/camera handling and microphone permission handling. It requires the running web backend. Emulator launch, patient login screen and clinic login were checked; physical-device acceptance remains outstanding. [Android build and installation](niyamit/android/README.md).
- **Latest health readings:** BP, glucose types and HbA1c retain their latest usable values, units, report dates and original-report links. New reports update values independently, so a missing BP does not erase an earlier BP. OCR readings remain unverified until clinic confirmation; no accuracy guarantee or diagnosis is implied.
- **Clinic priority queues:** Today groups staff-flagged Urgent/High, Needs verification, staff-assessed Routine and Not assessed. Doctors/nurses assign priority with a reason; new reports flag previous routine assessments for review. No automatic critical-value rules or emergency alerts are enabled.

The APK uses the laptop through localhost port forwarding for emulator testing. Independent use while the laptop is off still requires hosting. The supplied hosted configuration targets a server; it is not a ready-to-deploy card-free hosting configuration.

## Start locally

Install Docker Desktop with Linux containers. From this repository:

```powershell
cd niyamit
Copy-Item backend/.env.example backend/.env
```

Copy only on first setup; preserve existing configuration. Generate a private random SECRET_KEY and save it in backend/.env, then:

```powershell
docker compose up -d --build --wait
```

Open http://localhost:3000/ and choose Patient or Clinic. Linux/macOS users use `cp` instead of `Copy-Item`.

## Documentation

- [Application guide](niyamit/README.md)
- [Android app build and testing](niyamit/android/README.md)
- [Hosted HTTPS demo](niyamit/HOSTED_DEMO.md)
- [Deployment and backups](niyamit/DEPLOYMENT.md)
- [Demo subscriptions](niyamit/BILLING.md)
- [Twilio and database inspection](niyamit/SMS_SETUP.md)
- [Testing](niyamit/TESTING.md)
- [Security](SECURITY.md)

Source lives in niyamit/. Pushing to GitHub does not host the app. A laptop tunnel depends on power and connectivity; server hosting runs independently. Never commit credentials, uploads, model weights or database dumps.


## Diabetes intelligence increment (local, not a production release)

The source audit is in [PROJECT_AUDIT.md](PROJECT_AUDIT.md). Structured medical candidates now reach Sarvam/OpenAI contracts and pass through evidence/unit/date validation and clinical review; regex remains a fallback. A source-linked English monitoring summary, numerical comparisons, JSON summary export and patient-scoped duplicate handling extend the existing application.

This is **not clinically validated or ready for real-patient production**. Medication/insulin history, CGM/glucometer ingestion, screening findings, personalized targets, full export/deletion and representative handwriting validation remain unfinished. No live deployment or APK publication was performed for this increment.

Engineering references: [Architecture](ARCHITECTURE.md), [Requirements](SRS.md), [Database](DATABASE_SCHEMA.md), [APIs](API_DOCUMENTATION.md), [OCR](OCR_PIPELINE.md), [Analysis](DIABETES_ANALYSIS_SPEC.md), [Clinical validation](CLINICAL_VALIDATION.md), [Security](SECURITY_REVIEW.md), [Tests](TEST_REPORT.md), [Deployment](DEPLOYMENT.md), [Operations](OPERATIONS_RUNBOOK.md), [Recovery](BACKUP_AND_RECOVERY.md), [Privacy](PRIVACY_AND_DATA_RETENTION.md).
