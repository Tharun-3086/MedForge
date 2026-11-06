# Render Free + Supabase synthetic demo

This profile hosts the API and frontend independently of the laptop. Supabase stores PostgreSQL records and encrypted originals; Render runs the application containers. It does not use the laptop's Docker volumes, Cloudflare tunnel, or VPS Compose stack. Existing local records/files are not automatically migrated.

This is a synthetic-data demo. Free hosting sleeps and has resource/usage limits; it is not a real-patient production deployment. Development OTPs are visibly labelled and do not send SMS. SMS/AI providers can charge separately even if hosting is free.

## 1. Prepare Supabase (before deploying)

1. Use a dedicated, empty Supabase project for Niyamit, on the Free plan.
2. Create a **private** Storage bucket named `niyamit-artifacts`. Keep it private. If restricting MIME types, allow `application/octet-stream`: stored files are encrypted `.bin` objects, not directly viewable photos. A 10 MB bucket file limit accommodates encryption overhead for the app's 5 MB originals.
3. Disable the project's **Data API** in its Data API integration/settings. Niyamit accesses PostgreSQL through its backend, not the Supabase database REST/GraphQL API. Leave Storage enabled. Startup additionally enables RLS and removes `PUBLIC`, `anon`, and `authenticated` grants on Niyamit tables. No browser RLS policies are required. This does not modify Supabase's auth/storage tables.
4. In **Connect**, select **Session pooler**, IPv4, port **5432**. Copy its exact hostname and `postgres.PROJECT_REF` username. Do not guess the regional hostname or use transaction-pooler port 6543.
5. For `DATABASE_URL`, change `postgresql://` to `postgresql+psycopg://`, insert the database password with reserved characters percent-encoded, and append `?sslmode=require` (or `&sslmode=require` if parameters already exist). This is the database password, not an API key.
6. Find the project URL and **secret API key (`sb_secret_...`)** in project API settings/API Keys. Use the new secret key for the existing setting `SUPABASE_SERVICE_ROLE_KEY`, not an anon/publishable key or personal access token. The backend sends modern keys only on the `apikey` header; legacy JWT keys also use Bearer authorization. If a legacy key was exposed, replace it and retire the compromised key using https://supabase.com/docs/guides/security/rotate-leaked-api-keys . Never place it in frontend variables, an APK, screenshots, Git, or chat.

Keep these values private; enter them directly in Render's Environment screen. The Supabase project URL itself is public, but its keys and connection string are secrets.

## 2. Publish the prepared source

The Render profile needs the source changes in GitHub before it can deploy them. From PowerShell:

```powershell
cd D:\niyamit\MedForge-Git
git fetch origin
git switch -c feature/render-supabase-demo origin/main
git add README.md current_status.md niyamit/README.md niyamit/DEPLOYMENT.md niyamit/TESTING.md niyamit/RENDER_FREE.md niyamit/backend/.env.example niyamit/backend/.env.render.example niyamit/backend/app/config.py niyamit/backend/app/db.py niyamit/backend/app/main.py niyamit/backend/app/storage.py niyamit/backend/app/render_start.py niyamit/backend/tests/conftest.py niyamit/backend/tests/test_remote_storage.py
git diff --cached --check
git diff --cached --name-only
git diff --cached
```

Check that only source, documentation and placeholder `.env.*.example` files are staged. Real `.env`, `.env.render`, keys, database dumps and APK outputs must stay excluded. Once reviewed:

```powershell
git commit -m "Prepare Render Free demo with private Supabase storage"
git push -u origin feature/render-supabase-demo
```

Create a pull request into `main`, wait for required checks/review, and merge it. These instructions do not execute a push automatically. For future work start from an updated `main` with a clean working tree.

## 3. Create the Render backend

Select **New > Web Service**, connect GitHub, and select `Tharun-3086/MedForge`. The repository owner may need to approve Render's GitHub access. Set:

| Field | Value |
| --- | --- |
| Name | `niyamit-api` (or an available name) |
| Branch | `main` after the PR merge |
| Root Directory | `niyamit/backend` |
| Language/runtime | Docker |
| Dockerfile Path | `./Dockerfile` relative to the root directory |
| Docker Build Context | `.` relative to the root directory, if shown |
| Region | A free region close to the Supabase region, e.g. Singapore if available |
| Instance type | **Free** |
| Docker Command (Advanced) | `python -m app.render_start` |
| Health Check Path | `/healthz` |

Do not create Render Postgres, a paid disk, a paid worker, or use a paid pre-deploy command. The container startup command handles migrations before starting one Uvicorn process on Render's `PORT`.

Use `backend/.env.render.example` as the environment-variable reference. Enter **all** its settings in Render, replacing these placeholders:

| Variable | Private value to enter |
| --- | --- |
| `SECRET_KEY` | New random secret, at least 32 characters; save it securely and keep it stable |
| `DATABASE_URL` | Supabase session-pooler URI with `postgresql+psycopg` and TLS |
| `SUPABASE_URL` | Your project's HTTPS origin, without `/storage` or other paths |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-only secret API key (`sb_secret_...`) |
| `PUBLIC_APP_URL` | Frontend HTTPS URL once created; temporary placeholder must be replaced before testing patient links |

Generate the secret locally, then paste it only into Render:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

The other reference settings deliberately use development OTPs, local OCR, offline rules, and no paid voice service. They set `TASKS_EAGER=true`, `INLINE_SCHEDULER=true`, rate limits enabled, a small database pool, 5 MB uploads, 3 PDF pages, and an 8-million-pixel image guard. Keep one worker. There is no external Redis; the existing process-memory rate-limit fallback is used.

Click **Deploy Web Service**. If Render requests a card or switches to a paid plan, stop and check the selected plan; this guide does not authorize spending.

Startup validates settings, runs Alembic, protects application tables, and seeds an empty database with synthetic fixtures. Existing clinics are preserved; startup never uses `--force`. Failed configuration/storage/migration stops deployment rather than pretending it succeeded.

When Live, open `https://YOUR-ACTUAL-API-HOST.onrender.com/healthz`. Expected:

```json
{"ok": true, "demo_mode": true}
```

Share only that public backend URL to continue frontend setup. Never share its environment-variable values. A green health check confirms API/database connectivity; it is not the full patient/report acceptance test.

## 4. Deploy the frontend next

Create a second **Free Web Service**, same repository/branch, Docker runtime:

- Root Directory: `niyamit/frontend`; Dockerfile Path `./Dockerfile`; context `.`.
- Set `BACKEND_INTERNAL_URL` to the actual **HTTPS backend URL**, without a trailing slash. Render provides it as the Docker build argument used by Next.js rewrites. Rebuild the frontend when this value changes.
- Use the Dockerfile's default command. Do not add Supabase or Twilio credentials here.
- After Live, update the backend's `PUBLIC_APP_URL` to the actual frontend HTTPS URL and redeploy the backend. `COOKIE_SECURE=true` must remain set.

The browser uses the frontend's same-origin `/api` proxy. Clinic `/login` and Patient `/patient` share this frontend with separate sessions/permissions. Update/rebuild the Android APK to use this stable frontend URL; a localhost APK still depends on the laptop/ADB.

## 5. Hosted acceptance before sharing

1. Check both service deploys and `/api/healthz` through the frontend.
2. Clinic login: synthetic `nurse@sunrise.demo` / `niyamit-demo`. Patient login: synthetic `+919000000101`, using the clearly labelled development code. Do not use personal/real medical data with public demo accounts.
3. Patient: upload a synthetic image prescription and a lab PDF within the reference limits. Wait for extraction; confirm automatic analysis is labelled separately from clinic-reviewed values.
4. Clinic: locate the same patient's report, open the original, review/correct a field. Patient: refresh and verify the reviewed result and latest health reading provenance.
5. Check a different clinic cannot open that report. Test staff invitation acceptance, role permissions and revocation.
6. Send a patient reply; verify it arrives at the clinic. Voice/AI translations need separately configured providers and are unavailable in the default no-charge profile.
7. Restart/redeploy the backend and reopen the uploaded original. It must persist through Supabase, not the Render filesystem. Check the Supabase private bucket contains ciphertext objects, not plaintext reports.
8. Open the frontend on a phone with the laptop turned off. Allow cold-start time; do not promise uninterrupted service or timed reminders on Free.

Validation for this change: 160 backend tests passed and the deployment Docker image built successfully. Local automated tests mock the Supabase HTTP service, use real PostgreSQL migrations and Tesseract, and test private storage, patient upload, clinic review, patient results, cross-clinic denial, outage handling and restart preparation. Live Supabase/Render acceptance still requires the actual deployed services and credentials entered in their dashboards.

## Viewing data, backups and limitations

Patient OTP retry update: apply the latest Alembic migration via `python -m app.render_start` before deploying the matching frontend. Phone send limits persist in PostgreSQL, with one successful send per minute and five per hour. Cooldown taps and failed provider sends do not use that allowance. A separate shared-network backstop limits possible starts to 120/hour. Retry-After reaches the frontend countdown, which survives reloads without storing the entered OTP. Keep rate limits enabled. Twilio trial recipient restrictions and provider limits still apply. APK users receive the hosted UI fix after Reload; no APK rebuild or database reset is needed.

View records in Supabase's Table Editor/SQL Editor and ciphertext objects in Storage. The backend's trusted database role can access the application tables; browser roles cannot. Do not make the bucket public to preview a file: use Niyamit's authorized original-file endpoint, which decrypts after checking access.

Back up the database, bucket objects, and the exact `SECRET_KEY`/optional `STORAGE_ENCRYPTION_KEY` together. Losing/changing the encryption key makes existing originals unreadable. Redeploying code is not a database rollback. Supabase cloud data is separate from local Docker volumes.

Render Free sleeps after 15 minutes idle, loses local files and shares 750 free instance hours per workspace/month across services. Two continuously running services would exceed that allowance. Watch bandwidth/build quotas too; do not enable paid overages. No artificial keep-alive loop is required. Supabase Free also has quotas/inactivity policies. The inline scheduler only runs while the API is awake: retention and reminder jobs can be late. Large/complex OCR can exceed free memory/CPU and must be assessed on the deployed host. This is a demo profile, not an always-on or clinical-production guarantee.

References: [Render Free](https://render.com/docs/free), [Render Docker](https://render.com/docs/docker), [Supabase connections](https://supabase.com/docs/guides/database/connecting-to-postgres), [Supabase API hardening](https://supabase.com/docs/guides/api/securing-your-api), [private Storage access](https://supabase.com/docs/guides/storage/security/access-control).
