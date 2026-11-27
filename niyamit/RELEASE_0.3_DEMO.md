# Publish health history and the Ramesh showcase

Prepared locally: 199 PostgreSQL/Alembic tests passed; frontend build and two
trend tests passed previously. Ramesh has three watermarked fictional source
reports and 36 fixture-verified results. The additive showcase initializer runs
on Render demo startup and preserves existing records. It never seeds production
or ordinary patients. Fictional clinic confirmations are explicitly identified
as fixture checks in audit notes, not actual medical reviews.

The final [patient journey check](PATIENT_FLOW_CHECK.md) also covers completed
report status, source-review task closure, plan approval, patient confirmation,
care history after visit completion and consent enforcement for Listen.

## 1. GitHub branch and review

Run in PowerShell. Do not discard uncommitted work or force-push main.

```powershell
cd D:\niyamit\MedForge-Git
git status --short
git switch -c feature/health-history-showcase
git add -- .github/workflows/ci.yml README.md current_status.md niyamit
git diff --cached --check
git diff --cached --name-only
```

Real `.env`, `.env.local`, signing keys, database dumps, model weights and APKs
must not be staged. Template `.env.example` files are intentional. Current Git
candidates were checked for sensitive filenames and configured secret values,
with no matches. Review the staged diff before committing.

```powershell
git diff --cached --stat
git commit -m "Add verified health history and Ramesh demo showcase"
git fetch origin
git merge --no-edit origin/main
git push -u origin feature/health-history-showcase
```

If the merge reports conflicts, stop and resolve/review them before pushing.
Open a pull request with base `main`, compare `feature/health-history-showcase`.
Review Files changed, wait for CI, then Squash and merge. Never bypass failed
checks. Suggested title: **Add verified health history and Ramesh demo showcase**.

Before merging, turn off frontend Auto-Deploy for this update if you want strict
backend-first deployment. After merge:

```powershell
git switch main
git pull --ff-only origin main
```

## 2. Backend Render service first

Open the existing **MedForge** backend service. Keep branch `main`, the existing
database/storage/Sarvam/Twilio secrets and the same encryption SECRET_KEY.
Keep the normal lightweight backend Dockerfile, not Dockerfile.ocr.

For the existing Free demo profile confirm these non-secret settings:

```dotenv
DEMO_MODE=true
APP_ENV=development
COOKIE_SECURE=true
TASKS_EAGER=true
INLINE_SCHEDULER=true
OCR_PROVIDER=local
STORAGE_PROVIDER=supabase
PUBLIC_APP_URL=https://niyamit-app.onrender.com
```

Keep the existing Docker Command `python -m app.render_start`. The startup runs
the additive migration and idempotent fictional showcase update. Do not run
`seed --force`, reset Supabase, rotate the encryption key, or enable heavy hybrid
models on the 512 MB Free API. Local Docker can continue using its hybrid worker.

Choose Manual Deploy → Deploy latest commit, unless the merged commit is already
deploying. Wait for Live. Check https://medforge-rg8q.onrender.com/healthz.
Review logs if migration, storage or fixture extraction fails; do not erase data.

## 3. Frontend Render service next

Open **niyamit-app**, branch `main`. Keep
`BACKEND_INTERNAL_URL=https://medforge-rg8q.onrender.com` and the existing frontend
Dockerfile. Do not add backend keys here. Manual Deploy → Deploy latest commit;
wait for Live and verify the deployed commit matches the merged main commit.
You can re-enable Auto-Deploy afterward.

Check https://niyamit-app.onrender.com/api/healthz, then open `/patient` and choose
**Try demo patient — no OTP**. Ramesh should show HbA1c, fasting/post-meal glucose,
BP, kidney results, lipids and weight. History has September/October/November
2026 report dates. Select a measurement to see the three-date confirmed trend.

Clinic: open `/login`, select the synthetic doctor account, find **Ramesh Kumar,
SDC-1001**, and compare the same values/history and source reports. Demo password
is `niyamit-demo`. Reload after a backend redeploy to confirm originals persist.
Use fictional documents only. Free services can sleep and take time to wake.

## 4. Android APK and GitHub Release

The prepared hosted APK is `D:\niyamit\releases\Niyamit-0.3.0-demo.apk`.
Version code 3 uses the same debug signing certificate as version code 2, and
opens https://niyamit-app.onrender.com/. No backend keys are embedded.

SHA-256:
`bccb28b72ba76b6546014f8a0e6d9cd82136e52fb10aafe513177e0ff2f1d0e2`

The APK loads the hosted frontend; installing it does not deploy the new web/API
code. Existing installed APKs also load the update after hosted deployment/Reload.
This remains a debug demo build, not a production/store-signed release.

After hosted acceptance, open GitHub → MedForge → Releases → Draft a new release:

- Tag: `v0.3.0-demo`; Target: merged `main`.
- Title: **Niyamit 0.3.0 Demo — Health History & Showcase**.
- Attach the APK and `D:\niyamit\releases\Niyamit-0.3.0-demo.sha256.txt` as
  release assets, not Git source files.
- Mark **Pre-release**, publish, and retain the older release for reference.

Release notes: Patient/clinic kidney, lipid and weight history; confirmed dated
trends; uncertainty verification; Ramesh fictional showcase; Android update code
3. Patient demo requires no OTP; normal phone sign-in still does. Hosted demo:
https://niyamit-app.onrender.com/. No real patient uploads.

On Android, download the new APK and install it over the old app. Keep the same
signing identity; do not uninstall or erase app data just to update. Test Ramesh
demo, clinic login, report upload and microphone/camera on a physical device.

Official references: [Render deployment controls](https://render.com/docs/deploys),
[GitHub releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).
