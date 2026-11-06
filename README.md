# Niyamit Care Bridge

One responsive application for patients and clinics: SMS OTP, prescription/report scanning, clinic review, follow-ups, multilingual messages, voice replies and clinic onboarding.

**Current release: deployable synthetic-data demo.** Twilio SMS login has been tested by the user. Subscriptions simulate billing and collect no money. Real-patient production requires the acceptance gates in the deployment guide.

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
- [Hosted HTTPS demo](niyamit/HOSTED_DEMO.md)
- [Deployment and backups](niyamit/DEPLOYMENT.md)
- [Demo subscriptions](niyamit/BILLING.md)
- [Twilio and database inspection](niyamit/SMS_SETUP.md)
- [Testing](niyamit/TESTING.md)
- [Security](SECURITY.md)

Source lives in niyamit/. Pushing to GitHub does not host the app. A laptop tunnel depends on power and connectivity; server hosting runs independently. Never commit credentials, uploads, model weights or database dumps.
