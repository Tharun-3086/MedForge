# Niyamit Care Bridge

Connected patient and clinic interfaces for follow-up care, messages, voice replies and prescription/report review. Next.js frontend, FastAPI API, PostgreSQL, Redis and Celery run together on one machine with Docker Compose.

**Release scope:** runnable synthetic-data demo and development deployment. Real-patient production launch is not approved: SMS OTP integration, clinical/language review and operational security acceptance remain required. No real SMS is sent by development OTP.

## Start

Install Docker Desktop with Linux containers, then run from this repository:

```powershell
cd niyamit
Copy-Item backend/.env.example backend/.env
# Edit backend/.env locally; generate a random SECRET_KEY before uploading files.
docker compose up -d --build --wait
```

On Linux/macOS use `cp backend/.env.example backend/.env`. Do not overwrite an existing configured `.env`.

Open [Niyamit](http://localhost:3000), [patient login](http://localhost:3000/patient), or [clinic login](http://localhost:3000/login). Demo staff: `nurse@sunrise.demo`, password `niyamit-demo`. Synthetic patient phone: `+919000000101`; use the explicitly labelled development code shown on screen.

## Documentation

- [Complete app guide](niyamit/README.md): setup, patient/clinic workflows, configuration and architecture.
- [Deployment and operations](niyamit/DEPLOYMENT.md): deployment boundaries, persistence, backups and production checklist.
- [Twilio SMS setup](niyamit/SMS_SETUP.md): real OTP integration, local credentials and database inspection.
- [Testing](niyamit/TESTING.md): automated checks and manual acceptance steps.
- [Security](SECURITY.md): secret handling and reporting.
- [Optional Baidu OCR](niyamit/BAIDU_OCR.md): experimental only; Tesseract is the default.
- [Current release status](current_status.md).

Source lives in `niyamit/`. GitHub Actions builds the Docker stack, runs backend tests, checks TypeScript and audits frontend production dependencies. CI results become available after you push; local results are recorded separately.
