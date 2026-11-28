# Connected patient and clinic checks

Use fictional patient data in the local demo. These changes do not remove clinic isolation or clinical verification.

## Patient question → clinical inbox → clinician reply

1. In the patient dashboard, use **Ask your clinic** and write in English, Hindi or Telugu. This explicit action creates a clinical task even if the classifier does not understand the wording. The original text is retained. Existing urgent-signal routing remains active; classification is not comprehensive medical triage.
2. On the clinic **Today** dashboard, open **Patient questions & concerns → Read & reply**. This inbox includes all clinical queues and patients without follow-up plans. It refreshes every ten seconds and has a manual refresh button.
3. A doctor or nurse takes ownership and writes a **Patient-visible reply** in a language the patient understands. Replies are shown exactly as entered, without automatic medical translation.
4. The patient sees the reply, clinician name, original question and timestamp in the app. The dashboard refreshes every fifteen seconds or through **Refresh replies**. No SMS or push delivery is implied.
5. Sending a reply keeps the task in progress. Record the actual outcome separately after the concern is addressed. Urgent concerns still require prompt clinical contact; the app is not an emergency service.

## Missing report results

1. Open the original report in **Report inbox** and check the patient, report date and result.
2. Doctor/nurse: expand **Add a missed reading from the original**. Choose a supported measurement, enter the value with its unit, source page, copied row and verification note.
3. Blood sugar is glucose. Choose fasting/post-meal/random only if the original specifies it; otherwise use glucose of unspecified type. Existing candidates must be corrected or rejected rather than duplicated.
4. The saved result is labelled as clinician transcription and confirmed, with an audit entry. The same source-linked reading is available to patient and clinic. Existing report-date/time precedence still applies.
5. For another numeric laboratory test, select **Other laboratory result**, enter its exact name and result with units. Verified results appear in both health dashboards with dated history; units remain separate. Qualitative clinical observations remain report-only. Additional tests have no automatic clinical interpretation.

## Doctor-created appointment

1. Open a patient and select **Book appointment**. The schedule preselects that patient.
2. Select **Day** once, then **Time slot** and clinician/room in the same row. The dropdown includes existing availability and clinic times; it uses the displayed clinic timezone.
3. **Book and send confirmation** reuses a matching open slot or creates a standard 20-minute slot and books it. There is no separate date/duration form. It is confirmed only after a booking reference is returned. Concurrent reservations still use the existing booking safeguards.
4. Confirm the appointment and reference in the patient's dashboard. A future appointment is not marked attended/completed by booking it.
5. Past slots and overlapping open/booked slots for the same clinician/room are rejected. Different clinics remain isolated.
6. The schedule picker offers starts from **11 AM through 7 PM** in the clinic timezone, in 20-minute steps. New slot creation rejects starts outside that range. Existing appointments are retained.

## APIs

- `POST /v1/p/questions`: authenticated patient question (`text`, `client_key`), processed immediately through the clinical handoff path, with the worker as a retry fallback.
- `POST /v1/tasks/{id}/reply`: clinic-scoped doctor/nurse reply (`text`), saved in the patient app, with audit and duplicate-send suppression.
- `GET /v1/p/home`: includes this patient's clinical questions and clinician replies only.
- `POST /v1/intake-proposals/{id}/fields`: doctor/nurse source-backed missing result (`name`, `value`, `quote`, `page`, `reason`, optional observation `label`).
- `POST /v1/availability`: staff-created slot (`starts_at`, `duration_minutes`, `provider_label`). A datetime without offset is interpreted in the clinic timezone; ambiguous clocks require an explicit offset.

Regression coverage is in `backend/tests/test_clinic_workflow_gaps.py`.

## Local verification — 28 November 2026

- PostgreSQL backend suite: **252 passed**. Includes question/reply round-trip without a follow-up plan, Telugu source preservation, cross-clinic and role denial, duplicate-send prevention, manual glucose tracking on both sides, additional report-only observations, future-slot booking, and overlap/past-time rejection.
- Next.js production build and TypeScript checks passed.
- Browser checks confirmed the dashboard clinical inbox, patient-visible reply composer, missing-reading form and catalogue, patient-preselected scheduling/slot creation, and patient question form.
- Backend, PostgreSQL, Redis, frontend and OCR worker are running locally. This does not claim live Render deployment or clinical validation of OCR accuracy.

## Compact dashboard and appointment responses

- The clinical inbox announces waiting questions on dashboard entry and new arrivals while open, using a toast; the persistent inbox remains available after the toast disappears.
- Patient readings use a wider desktop grid and compact mobile groups. History, monitoring summary and report analysis expand on demand. **Ask your clinic** is for clinical questions; **Appointment or reminder message** is for follow-up logistics. The Message clinic shortcut opens the clinical-question form.
- Booked appointments have their own **I will come**, **I can't come** with a reason, **Change the date**, and **Please call me** actions, including appointments created without a follow-up plan.
- `POST /v1/p/appointments/{id}/response` records the authenticated patient's response in the shared timeline; problems create a clinic task. It rejects another patient's appointment, expired bookings and missing barrier reasons. A response does not cancel the booking or mark the visit completed.
- Appointment initiation is unchanged: patients may request a time, and clinic staff may create/book a slot.
- Incremental validation: eight workflow/patient-app tests and the Next.js production build passed.

## Additional laboratory tests and conversation assistance

- The document schema accepts source-named laboratory tests beyond the original diabetes catalogue. Printed-row fallback proposes additional numeric results with explicit laboratory units. Medicines and reference-only rows are excluded.
- Existing reports can use **Find additional lab results in this report**. It reads stored OCR blocks locally, appends new unverified candidates idempotently, and preserves existing reviews and originals.
- Unknown candidates require **Correct** to verify the test name, number and unit. Known synonyms map back to their existing measurement type. Incorrect glucose units cannot be approved unchanged.
- Additional results appear only after doctor/nurse verification, with source evidence and unit-separated history. Unknown results do not gain automatic clinical targets, diagnoses or treatment recommendations.
- **Suggest appointment options from this conversation** is an explicit clinician action. It classifies the selected patient message, latest clinician reply and optional unsent draft, proposes a date and reads existing availability. AI consent is checked; otherwise offline rules are used. Urgent cues suppress scheduling suggestions. Suggestions never book, send messages, alter priority or prescribe; staff reviews the schedule and explicitly confirms.
- Clinician replies remain exactly as typed. This assistant does not continuously monitor all chats or automatically translate clinician advice.

## Appointment-task replies and booking changes

- Doctors/nurses can reply directly from reschedule, attendance-barrier, callback and booking-failure tasks. The patient sees the reply and request status under **Your requests & clinic replies**, alongside their bookings.
- Task controls provide **Cancel appointment**, **Postpone appointment** and **Prepone appointment**. A specific booking must be selected. Cancellation requires a reason; moves send an automatic patient-visible update and allow an optional extra note.
- Cancellation releases the reserved slot and returns a linked follow-up to pending; it does not record attendance or discontinue the care plan.
- Postpone/prepone opens Schedule with the patient and original date already selected. Staff selects a later/earlier replacement and confirms. The backend books the replacement and cancels the original atomically. Failure retains the original booking. Directions and clinic scope are checked server-side.
- The action resolves associated attendance requests for the old booking, records an audit trail and patient-visible update, and retains booking history. Repeated requests do not duplicate changes.
- APIs: `POST /v1/tasks/{id}/reply` and `POST /v1/tasks/{id}/appointment-action` (`action`, `appointment_id`, optional replacement `slot_id`, required patient-visible `message`).
- Regression coverage: `backend/tests/test_appointment_task_actions.py` exercises both patient and clinic APIs, role/clinic isolation, retries, cancellation, both move directions, and unavailable-slot rollback.
