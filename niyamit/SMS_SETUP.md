# Twilio Verify phone login

The integration is implemented. Live SMS delivery still requires your own configured Twilio account and a physical-phone test. Development login remains the local default until then.

1. Create a Twilio account and a Verify Service in the Twilio Console. Set its code length to **6 digits**. Review the account's destination-country permissions and any trial restrictions before testing.
2. Put these values in the ignored `backend/.env`, never in Git or frontend variables:

```dotenv
PATIENT_OTP_PROVIDER=twilio
TWILIO_ACCOUNT_SID=your-account-sid
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_VERIFY_SERVICE_SID=your-verify-service-sid
```

3. Restart with `docker compose up -d --no-deps backend worker`. Rebuild first if deploying newly changed source.
4. Register the exact phone number in the intended clinic. Open `/patient`, press **Send SMS code**, enter the SMS code and choose the clinic if multiple profiles exist.
5. Verify incorrect, expired and reused codes fail. Check no development code appears. SMS delivery may incur provider charges; no live SMS was sent during automated validation.

With DEMO_MODE=true, even SMS-authenticated login opens only synthetic records. Real-clinic records require an isolated non-demo deployment and the production requirements in DEPLOYMENT.md. Production continues to reject development OTP. The local challenge expires after five minutes, permits five attempts and enforces resend cooldown and phone/IP limits. Provider errors fail closed without exposing provider response bodies. SMS verifies possession of the registered number; clinic registration and record ownership must still be checked by staff.

Official API contracts: https://www.twilio.com/docs/verify/api/verification and https://www.twilio.com/docs/verify/api/verification-check

## View Docker PostgreSQL

From the app directory:

```powershell
docker compose exec db psql -U niyamit -d niyamit
```

Then enter:

```sql
BEGIN READ ONLY;
\dt
SELECT id, name, is_synthetic FROM clinics;
SELECT count(*) AS patients FROM patients;
ROLLBACK;
\q
```

The data is in the PostgreSQL named volume. Rebuilding containers preserves it; deleting volumes destroys it. GUI access should use a private connection or SSH tunnel; the public web tunnel must not expose the database.

If creating a Verify Service asks for an upgrade, check Identity > Verify > Overview > Try out Verify. Twilio documents copying the trial API request, including its Service SID, from that page. Trial recipients must be verified. Availability is account-dependent; if restricted, keep PATIENT_OTP_PROVIDER=development until you choose to upgrade or use another supported provider. Never substitute the Account SID for the Verify Service SID.
