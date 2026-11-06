# Deployment and operations

For an independent server-hosted synthetic demo with HTTPS, use [HOSTED_DEMO.md](HOSTED_DEMO.md) and the standalone compose.hosted.yml file. Only its proxy publishes host ports. Demo subscriptions collect no money; see [BILLING.md](BILLING.md).


## Supported release deployment

The included Compose stack is a **single-host synthetic-data demo/development deployment**. It is reproducible from source and does not depend on another laptop or Baidu. It is not a publicly exposed real-patient production configuration.

1. Clone the repository; enter `niyamit/`.
2. Copy `backend/.env.example` to `backend/.env` once and configure secrets locally.
3. Keep `OCR_PROVIDER=local`. For fully local document processing also set `DOC_PROVIDER=local`.
4. Run `docker compose up -d --build --wait`.
5. Check `docker compose ps`, `/healthz`, patient login and clinic login.
6. Run the acceptance checks in `TESTING.md` before handing over the environment.

The Compose database and Redis have no host ports. Backend port 8000 binds to loopback. Frontend port 3000 is published on the host: restrict it with the host firewall or bind it to loopback for private testing. Demo credentials are public and must never protect real data.

## Updating and rollback

Back up first. Record the deployed Git commit and image IDs. Build the new images, then run `docker compose up -d --build --wait`; the API runs Alembic migrations before serving, and the worker waits for a healthy API. Demo seeding is skipped when demo mode is disabled or the environment is production. Never use `python -m app.seed --force` on data you need.

A code rollback is not automatically a database rollback. Restore the matching database, artifacts and encryption configuration together if a migration is incompatible. Keep the old images until acceptance passes. `docker compose down` preserves named data volumes; **`down -v` destroys them** and is only appropriate for disposable CI/demo resets.

## Persistence and backups

PostgreSQL uses the `pgdata` named volume; uploads use `appdata`. Back up both and preserve `SECRET_KEY` plus any explicit `STORAGE_ENCRYPTION_KEY` separately in a secret manager. Losing the encryption configuration can make uploaded originals unreadable.

For a consistent backup, stop the worker and backend temporarily, dump PostgreSQL inside the database container, copy the dump out, and snapshot/archive the appdata volume using your infrastructure's backup mechanism. Example database commands from `niyamit/`:

```powershell
docker compose stop worker backend
docker compose exec -T db pg_dump -U niyamit -d niyamit -Fc -f /tmp/niyamit.dump
docker compose cp db:/tmp/niyamit.dump ./niyamit.dump
# Back up the appdata volume and encryption configuration before restarting.
docker compose up -d backend worker
```

Store backups outside the repository with restricted access. Restore into an isolated environment using `pg_restore`, restore matching artifacts/configuration, then verify patient ownership, originals and clinic-reviewed results. A successful backup command is not proof of a successful restore. A restore rehearsal has not been completed for this release.

## Real-patient production launch gates

- Configure Twilio Verify and verify live SMS delivery; development OTP is blocked in production. Until then phone OTP must be disabled, not disguised as SMS.
- Use a managed secret store, a fresh strong secret, unique database credentials and least-privilege database users. The supplied Compose database password is demo-only.
- Set `APP_ENV=production`, `DEMO_MODE=false`, `PATIENT_OTP_PROVIDER=twilio` with valid credentials (or `disabled` when phone login is unavailable), `COOKIE_SECURE=true`, and an HTTPS `PUBLIC_APP_URL`. Startup rejects unsafe combinations.
- Provision real clinic/staff accounts through an approved administrative process; do not seed demo accounts into a production database. Use the private provisioning command below; never expose it as public self-registration.
- Deploy behind a trusted HTTPS reverse proxy, expose only required public ports, and validate proxy/rate-limit configuration. Build the frontend with the correct internal API URL.
- Keep one scheduler instance; the demo Celery worker embeds beat (`-B`) and must not be blindly replicated. Separate scheduling before scaling workers.
- Establish monitoring for API health, queue failures, disk capacity, provider timeouts and backup failures. Redact personal information and credentials from logs.
- Complete access-control/security review, clinical review, Telugu/Hindi wording review, consent/privacy/retention decisions and provider agreements for the intended use.
- Test real SMS, real microphone/camera, provider failures, recovery and backup restoration in the target environment.

These are explicit outstanding release gates, not work silently claimed as completed. No remote deployment or Git push is performed by these instructions.

## Provision a clinic and its first administrator

Run only in an isolated deployment after the production gates above are satisfied. Do not convert the shared public demo database into a production clinic. Configure `DEMO_MODE=false` and disable development OTP first. The command checks startup configuration and refuses demo mode. It never overwrites an existing account or clinic.

```powershell
docker compose exec backend python -m app.bootstrap_clinic --name "Example Clinic" --short-name "Example" --admin-email "owner@example.com" --admin-name "Clinic Owner"
```

Replace example details with the verified clinic administrator's information. The command prompts privately for a password and confirmation; do not put the password in command arguments. It creates a non-synthetic clinic, one administrator and **draft** message templates. An authorized reviewer must approve wording before messaging. The administrator can then invite ordinary staff from Settings. No email verification/delivery or real SMS is added by this command; complete those production requirements separately.

## Inspect the database without exposing it publicly

On the Docker host, enter `niyamit/` and run:

```powershell
docker compose exec db psql -U niyamit -d niyamit
```

Inside psql, use a read-only transaction:

```sql
BEGIN READ ONLY;
\dt
SELECT id, name, is_synthetic FROM clinics;
SELECT count(*) AS patients FROM patients;
SELECT count(*) AS staff_accounts FROM users;
ROLLBACK;
\q
```

These credentials are for the supplied demo Compose stack. Use the configured database user on a real deployment. PostgreSQL lives in a container, but its data lives in the `pgdata` named volume. A normal container rebuild/restart preserves it; deleting volumes does not. Uploads live separately in `appdata` and need their own backup plus the encryption key.

On a remote host, SSH into that host and run the same commands there. A GUI such as DBeaver/pgAdmin should connect through a private network or SSH tunnel with restricted credentials. Do not publish PostgreSQL port 5432 through the public app tunnel. The HTTPS demo URL exposes the web app, not a database management interface.
