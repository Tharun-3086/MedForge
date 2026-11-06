# Niyamit demo video walkthrough

Target length: about three minutes. Show real patient OTP login, report scanning, clinic review and the updated patient dashboard. Use synthetic records throughout. This is a recording plan and test media, not an already recorded video.

## Before recording

1. Push/merge the OTP retry fix. Deploy the backend first, then the frontend. Startup applies the new database migration; no reset or reseeding is needed.
2. In the APK, tap Reload or close/reopen after deployment. These hosted interface changes do not require a new APK.
3. Open the [app](https://niyamit-app.onrender.com/) and [API health check](https://niyamit-app.onrender.com/api/healthz) before recording so the free-host cold start finishes.
4. Keep the Patient session on the phone and open [Clinic login](https://niyamit-app.onrender.com/login) in a separate desktop browser/private window. The synthetic nurse account is documented in the project README.
5. Use a synthetic record named DEMO PATIENT with a phone its owner has agreed to use. Reuse an existing matching test profile rather than adding duplicates. Use SIMULATED as the message channel and leave optional consents unchecked unless testing them.
6. A Twilio trial requires the recipient number to be verified in Twilio. A clinic record alone does not satisfy that restriction. See [Twilio trial Verify instructions](https://www.twilio.com/docs/usage/trials/try-out-verify).
7. Copy [the synthetic image report](docs/demo-assets/Niyamit-Synthetic-Lab-Report.png) to the phone's Downloads. The [PDF alternative](docs/demo-assets/Niyamit-Synthetic-Lab-Report.pdf) tests PDF text extraction. Use the PNG to demonstrate Tesseract OCR.
8. Conceal the phone number and OTP. Pause/cut code entry and resume on the dashboard, or blur those fields when editing. Keep provider keys, environment screens and other people's records out of the recording.

Expected fixture values: BP 120/80 mmHg, fasting glucose 110 mg/dL, HbA1c 6.2%, document date 6 November 2026 and next review date 20 December 2026. Update the future review date before recording after that date. All fixture values are fictional software inputs.

## Shots and narration

| Time | Show and click | Say |
| --- | --- | --- |
| 0:00-0:15 | Open the app. Show Patient/Clinic choices. Complete or skip the tour once. | “Niyamit connects patients and clinic teams for follow-up care. The same application provides separate patient and clinic interfaces.” |
| 0:15-0:40 | Choose Patient. Enter the registered test number. Tap Send SMS code once. Enter the received code privately and tap Verify and sign in. If asked, choose the intended clinic. Resume recording on the dashboard. | “A patient signs in using the phone number registered with their clinic. The app sends an SMS code and opens the patient's care page after verification.” |
| 0:40-1:10 | Tap Scan a report. Select Lab report. Choose Files/Gallery and upload the synthetic PNG. Wait, then tap View analysis. | “The patient uploads a lab report from their phone. Niyamit keeps the original and reads the document. Here we use a clearly labelled synthetic report.” |
| 1:10-1:30 | Show Latest health readings, Unverified OCR and the separate automatic/clinic-reviewed sections. | “Extracted readings appear with their source and review status. Automatic readings can contain mistakes. They remain separate from information confirmed by the clinic.” |
| 1:30-2:20 | Switch to Clinic. Open Reports, find this patient's upload and click Review. Compare the original with the fields. Click Matches the original for BP, fasting glucose and HbA1c only if they match. Check and confirm Next review visit, select its approved date if needed, then click Approve plan and schedule reminders. | “The clinic receives the same report. A nurse or doctor checks each field against the original. If a value is wrong, staff can correct it with a reason. Here the readings match, so we confirm them and approve the review date.” |
| 2:20-2:45 | Return to Patient. Tap Refresh analysis and Refresh readings if needed. Show Clinic-reviewed labels, unchanged automatic values and the approved follow-up visit. | “The patient now sees clinic-confirmed readings and the approved follow-up plan. The original automatic extraction remains visible separately, so the review history is clear.” |
| 2:45-3:00 | Show the live URL and a closing card. | “Niyamit's hosted demo and Android app connect both sides of the workflow. This is a synthetic-data demo. Clinical validation and physical-device checks remain before real-patient use.” |

Trim waiting time between actions. If OCR already matches, use Matches the original rather than inventing an error for the recording. An optional extra clip can show Correct, its units-aware text box and the required reason. Only save a correction that matches the source.

## OTP troubleshooting

- Stop repeated Send/Resend taps. Use the latest SMS while it is valid.
- After the fix, follow the actual Retry-After countdown for cooldown, hourly allowance or provider backoff.
- Per-phone policy remains one successful request per minute and five per hour. Cooldown taps and failed provider sends do not consume the hourly allowance. The allowance persists across API restarts.
- A shared-network backstop permits 120 possible sends per hour. Narrow phone limits prevent one patient from consuming another patient's phone allowance. Multi-instance production needs shared rate-limit infrastructure and verified proxy configuration.
- Twilio verification limits can require about ten minutes before retrying. The app cannot override provider limits. See [Twilio error 60203](https://www.twilio.com/docs/api/errors/60203).
- Trial accounts require verified recipients. The updated UI explains this separately from rate limiting.
- APK refresh does not remove a genuine server/provider restriction. Private patient access links can support testing while SMS is unavailable, but do not present access-link login as OTP login in the video.

## Recording and export

Record the APK patient flow on the phone and the clinic flow on the desktop, then combine the clips. A browser-only recording with a narrow patient window is also acceptable; label the interface you show. Use your device's screen recorder and record the narration separately or while presenting.

Capture at 1080p where available. Hide notifications and unrelated records. Pause after each status update. Use simple cuts and captions: Patient OTP login, Upload synthetic report, Automatic readings, Clinic reviews original, Patient sees confirmed results. End with https://niyamit-app.onrender.com/ and “Synthetic demo”. Export MP4/H.264 at 1080p if your editor supports it.

Optional credits: Team MedForge. M. Shrinidhi, Doctor, Osmania University. Chandrashen and Tharun Tej, IIT Bombay CSE. V. Hasini and B. M. Kiran, Malla Reddy College.

Add the video URL to the solution brief only after uploading the real recording.
