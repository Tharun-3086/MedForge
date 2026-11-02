# Niyamit Care Bridge

Diabetes follow-up coordination for small clinics. Staff see one worklist of who is due, late or waiting;
patients reply in Telugu, Hindi or English (typed, tapped or spoken); AI reads prescriptions and replies but only
**proposes**: a person confirms every date, and nothing is booked or sent as "done" unless it really happened.

Built for Health-a-thon 2026 (Team MedForge) from the Niyamit Care Bridge PRD. Every patient, clinic and document
here is synthetic.

---

## Run it (Docker)

You need Docker Desktop with Compose v2.24 or newer.

```bash
cp backend/.env.example backend/.env      # Windows: copy backend\.env.example backend\.env
# paste your keys into backend/.env (next section); the app also runs without them, offline
docker compose up --build
```

Open **http://localhost:3000** and click any demo account. The first build takes a few minutes; later starts are
quick. Stop with `docker compose down`. Wipe all data and start fresh with `docker compose down -v`.

What starts: PostgreSQL 16, Redis 7, the FastAPI backend (creates the tables and loads the synthetic demo data on
first start), a Celery worker (reminders, reply and document processing, retries, every 15 seconds) and the
Next.js web app.

## Where to paste your keys

Both keys go in **one file: `backend/.env`** (copied from `backend/.env.example`). Paste each key right after the
`=` sign, with no quotes or spaces:

| Line in `backend/.env` | What it powers | Needed? |
|---|---|---|
| `SARVAM_API_KEY=` | Understanding Telugu/Hindi/English replies, voice notes (speech to text), read-aloud, reading documents | Recommended |
| `OPENAI_API_KEY=` | An alternative model for replies and documents | Optional |
| `SECRET_KEY=` | Signs logins and encrypts uploads. Any long random string | Change the placeholder |

- **Sarvam key:** create it at [indus.sarvam.ai/key-management](https://indus.sarvam.ai/key-management). It is shown
  only once, so copy it straight into the file.
- **ChatGPT Plus is not an API key.** The Plus subscription covers chatgpt.com only. An OpenAI API key comes from
  [platform.openai.com/api-keys](https://platform.openai.com/api-keys) and is billed separately. Leave
  `OPENAI_API_KEY` empty if you don't have one; Sarvam covers every AI job.
- No key goes in any `frontend/` file.
- After editing `backend/.env`, run `docker compose up -d` to restart with the new values.
- To check: sign in, open **Settings → AI and messaging**. It shows which provider is active and whether each key
  is added. Keys are never displayed.

Without any key the app still works: replies are understood by offline rules, documents are read by on-server OCR
(Tesseract), and voice notes are switched off with a clear message to the patient.

## Demo accounts

Password for every account: `niyamit-demo` (or just click the account on the sign-in page).

| Email | Role | Use it for |
|---|---|---|
| `nurse@sunrise.demo` | Nurse (Priya Nair) | The main demo: worklist, reports, tasks, plans |
| `doctor@sunrise.demo` | Doctor (Dr. Ananya Rao) | Approving plans, clinical questions |
| `reception@sunrise.demo` | Reception (Ravi Kumar) | Calls and bookings |
| `admin@sunrise.demo` | Clinic admin (Meera Iyer) | Settings, templates, audit log, **Reset demo data** (Test panel) |
| `ops@niyamit.demo` | Platform support | Health and metrics without patient details |
| `doctor@lakeview.demo` | A second clinic | Showing that one clinic cannot see another's patients |

Patients don't sign in with a password. Staff open a patient's record and click **Patient app link**; the link asks
for the year of birth shown on that record. To show the family-helper view, open a patient's app link, go to
**Family access**, tick what the helper may do and press **Give access**; open the link it shows. (A ready-made
link for Kavya Menon's son is also printed in the backend log when the demo data is first loaded.)

## Three-minute demo (PRD section 19)

Sign in as **Priya Nair (nurse)**.

1. **The problem (0:00).** *Today* shows the register: who is late, who replied, what is waiting on the clinic.
2. **Voice/language bridge (0:20).** *Patient phone (simulated)* → pick **Ramesh Kumar (Telugu)** → tap
   "Doctor, Monday nahi aa sakta. Saturday slot unda?". The clinic answers in Telugu with a link to pick a time,
   and Ramesh's record (*Patients*) shows what was understood: the request, the Saturday it resolved (Monday is
   skipped because it was refused) and the real times offered. Tap **hmm ok maybe** to show that an unsure reply
   gets a question, not a guess. With a Sarvam key, open Ramesh's **Patient app link** in the laptop's browser and
   record a voice note (browsers allow the microphone only on `localhost` or HTTPS, so not over plain Wi-Fi IPs).
3. **Document to plan (0:55).** *Report inbox* → **lab_report_hba1c.pdf** (Venkat Rao). Each value is outlined on
   the original, marked "AI proposed, unverified". Click **Matches the original** (or **Correct**), then
   **Approve plan and schedule reminders**.
4. **Booking (1:20).** *Schedule* → **Book a time** for Imran Khan → choose a slot → **Book and send
   confirmation**. A booking reference appears and the confirmation reaches the patient phone.
5. **Barrier to task (1:50).** Patient phone → **Abdul Sattar** → "Paise nahi hain abhi, test baad mein
   karwaunga". *Tasks* now has a cost-barrier task: assign it, start it, resolve it with an outcome.
6. **Safety and reliability (2:15).** Patient phone → **Meena Devi** → "Sugar 300 undi, tablet maarchala?"
   goes to the clinician queue with a safe reply. Farhana Begum's STOP shows as *Not sent* in *Messages*.
   **Deliver last reply again** on the phone proves a repeated webhook creates nothing new. *Test panel* →
   **Run all scenarios** runs the PRD's failure cases live.
7. **Doctor view and evidence (2:40).** Venkat Rao's record → **Visit capsule**. Then *Metrics* and
   *Language evaluation* (**Start run**). Numbers there come only from stored runs on synthetic data.

To start over before a rehearsal: sign in as the admin → *Test panel* → **Reset demo data**.

## Running without Docker

Needs Python 3.12+, Node.js 20.9+, PostgreSQL 16 and Redis 7 on your machine.

```bash
# database, once: the user and database that DATABASE_URL in backend/.env expects (password: niyamit)
createuser -d -P niyamit          # -d lets the tests create their own niyamit_test database
createdb -O niyamit niyamit

# backend (terminal 1)
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                     # paste keys; DATABASE_URL/REDIS_URL point at localhost
alembic upgrade head && python -m app.seed
uvicorn app.main:app --reload --port 8000

# worker (terminal 2, same folder and venv)
celery -A app.worker worker -B --loglevel=INFO
# Windows: -B is not supported there, so run two terminals instead:
#   celery -A app.worker worker --pool=solo --loglevel=INFO
#   celery -A app.worker beat --loglevel=INFO

# web app (terminal 3)
cd frontend
cp .env.example .env.local
npm install && npm run dev                               # http://localhost:3000
```

No Redis or Celery? Add `TASKS_EAGER=true` and `INLINE_SCHEDULER=true` to `backend/.env` and skip terminal 2: jobs
then run inside the API process. Install Tesseract for on-server OCR (`brew install tesseract`,
`apt install tesseract-ocr`, or the Windows installer).

## Tests

```bash
docker compose exec backend pytest -q        # or, without Docker: cd backend && pytest -q
```

87 tests, including all 18 acceptance gates from PRD section 20, the reliability cases from section 15 and the
language rules. They use a separate `<database>_test` database and never call paid AI providers.
`cd frontend && npm run typecheck` checks the web app's types.

## How it is built

```
docker-compose.yml       postgres, redis, backend, worker, frontend
backend/                 FastAPI + SQLAlchemy + Alembic + Celery
  app/routers/           auth, staff, intake (documents), patient_app (+ caregiver), demo, evals, webhooks
  app/services/          plans, replies, booking, messaging, tasks, intake, metrics, recovery …
  app/ai/                Sarvam and OpenAI adapters, offline rules, date handling, document reading
  app/channels/          simulated phone and the WhatsApp Cloud API adapter
  alembic/               database migrations
  eval/corpus_v1.json    52 labelled synthetic test messages (Telugu–English, Hindi–English, English)
  samples/               synthetic prescriptions and a lab report used by the demo
  tests/                 acceptance gates, reliability, language and provider tests
frontend/                Next.js 15 (App Router) + React 19 + TypeScript
  app/(staff)/           clinic screens: today, tasks, reports, patients, schedule, messages, phone, test panel …
  app/p/[token]          patient app (Telugu / Hindi / English)
  app/c/[token]          family-helper view
```

The browser only talks to the Next.js server; `/api/*` is forwarded to the backend, so session cookies stay
first-party and the API is not exposed (port 8000 is bound to your own machine only, for the API docs at
http://localhost:8000/v1/docs).

Ground rules the code enforces:

- **AI proposes, people approve.** Extracted dates stay "AI proposed, unverified" until staff confirm them
  against the outlined source; only a doctor or nurse (configurable) turns them into a plan.
- **Never guess.** Unsure or vague replies ("hmm ok maybe", "next week", "kal") get a short question.
  "Next Saturday" said on a Friday offers both Saturdays.
- **Never fake success.** A message is "Delivered" only when the provider confirms it; a booking exists only after
  it is saved with a reference; failures open a task with an owner.
- **Medical questions and possible emergencies go to people**, with a safe acknowledgement and 108/112 guidance.
- **Privacy:** reminders never mention diabetes; clinics are isolated from each other; external AI is used only
  with the patient's recorded consent; private links inside messages are masked on staff screens, and creating a
  patient link is written to the audit log.

## Defaults chosen where the PRD left decisions open (section 23)

| Decision | Default in this build | Where to change it |
|---|---|---|
| Who owns the follow-up plan | Doctors and nurses approve; the approved plan is the system of record | Settings → Who can approve plans |
| Communication channel | Simulated phone in the app; WhatsApp Cloud API adapter included but off | `WHATSAPP_*` in `backend/.env` |
| Appointments | Seeded synthetic availability, no external scheduling API | — |
| Languages | Telugu–English and Hindi–English code-mix, plus English | — |
| Document samples | Synthetic prescription, conflicting-dates prescription, lab report PDF, prompt-injection test image | `backend/scripts/make_samples.py` |
| Clinical questions / possible urgent | Nurse queue / doctor queue, with draft acknowledgement wording | Settings |
| Reminder policy | Quiet hours 21:00–08:00, sent at 10:00; 3 and 1 days before, on the day, 3 and 7 days after; call task after 7 days late; one reminder a day at most; STOP to opt out | Settings |
| Retention | Voice notes 30 days, documents 365 days | Settings |
| Cost and accuracy | Measured, not assumed: Metrics (cost estimate per message) and Language evaluation (stored runs) | — |

## What has been tested, and what hasn't

- Tested: the backend test suite above; both job modes (Celery worker and inline); every screen in a real browser,
  including the patient app at phone size in Telugu, Hindi and English; and the three-minute demo above, step by
  step, on freshly loaded demo data.
- Not yet run: `docker compose up --build` itself (the build machine had no access to Docker Hub, PyPI or npm), live
  calls with real Sarvam or OpenAI keys (the adapters are tested against mocked responses in the providers'
  documented formats), and real WhatsApp delivery. If the first Docker build or a live AI call fails, the logs (`docker compose logs -f backend worker`)
  will say which step.

## Before any real patient

- The message templates are **draft wording**, marked "pending clinical lead review". A clinician must review
  them, especially the clinical and urgent replies (Settings → Message templates).
- Telugu and Hindi patient-app and message text should be checked by native speakers.
- Set `DEMO_MODE=false`, `APP_ENV=production`, a real `SECRET_KEY`, HTTPS with `COOKIE_SECURE=true`, and review
  the AI providers' data-processing terms before sending any real health data.
- The offline rules were written alongside the evaluation test set, so their score there is optimistic.

## Troubleshooting

- **Settings says "Not added" after pasting a key:** the key must be in `backend/.env` (not `.env.example`),
  then run `docker compose up -d`.
- **Port 3000 or 8000 already in use:** stop the other app, or change the left-hand number under `ports:` in
  `docker-compose.yml` (for 3000, also set `PUBLIC_APP_URL` in `backend/.env` to the new address).
- **`env_file` / `required` error:** your Docker Compose is older than v2.24; update Docker Desktop.
- **"The stored file cannot be read" after changing `SECRET_KEY`:** reset the demo data (admin → Test panel).
- **A patient link says it no longer works:** a **Patient app link** made by staff lasts 24 hours and links inside
  reminder messages last 7 days; make a new one from the patient record.
- **Logs:** `docker compose logs -f backend worker`.
