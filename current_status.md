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
