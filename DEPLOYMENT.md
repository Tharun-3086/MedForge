# Deployment status and gates

Current supported hosted path is the synthetic demo documented in [Render Free guide](niyamit/RENDER_FREE.md) and [existing deployment guide](niyamit/DEPLOYMENT.md). This increment has not been pushed, deployed to Render or packaged into an APK.

For local verification use existing Docker Compose plus optional docker-compose.ocr.yml. Run PostgreSQL tests only against the test database. Never use `down -v` against the developer/live stack. Keep keys in ignored env files/server settings.

Before production: complete CLINICAL_VALIDATION.md and SECURITY_REVIEW.md gates; use APP_ENV=production, DEMO_MODE=false, Secure cookies, HTTPS, real OTP provider, private storage, stable separate storage key, persistent workers and managed DB backups. The current `app.render_start` rejects production: do not bypass this guard to make a free demo appear production-ready. Build a separately reviewed production entrypoint/profile.

No migration is required for this additive evidence/summary increment. Deploy backend before frontend that calls new endpoints; verify original/review/history APIs. Canary with synthetic fixtures; verify role/tenant checks; retain previous application images. Do not automatically re-extract or overwrite previously reviewed medical records.
