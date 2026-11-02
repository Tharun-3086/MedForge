# MedForge

# Niyamit Care Bridge (Team MedForge)

Diabetes follow-up coordination for small clinics. Staff see one worklist of who is due, late or waiting. Patients reply in Telugu, Hindi or English (typed, tapped or spoken). AI only **proposes**: a person confirms every date, and nothing is shown as booked or sent unless it really happened.

All patients, clinics and documents are **synthetic demo data**.

---

## 1. Run it with Docker (recommended)

**You need:** Docker Desktop with Compose v2.24 or newer, and Git.

```bash
# 1. Get the code
git clone https://github.com/Tharun-3086/MedForge.git
cd MedForge

# 2. Create your settings file
cp backend/.env.example backend/.env          # Windows (cmd): copy backend\.env.example backend\.env

# 3. (Optional) open backend/.env and paste your keys, see section 2

# 4. Build and start everything (first build takes a few minutes)
docker compose up --build
```

Open **http://localhost:3000** and click any demo account.
The API docs are at http://localhost:8000/v1/docs.

| Action | Command |
|---|---|
| Stop | `docker compose down` |
| Start again (no rebuild) | `docker compose up -d` |
| Wipe all data and start fresh | `docker compose down -v` |
| See logs | `docker compose logs -f backend worker` |
| Run the tests | `docker compose exec backend pytest -q` |

What starts: PostgreSQL 16, Redis 7, the FastAPI backend (creates tables and loads demo data on first start), a Celery worker (reminders, replies, documents), and the Next.js web app.

## 2. Where to put the AI keys

Everything goes in **one file: `backend/.env`**. Paste the key right after the `=`, with no quotes or spaces.

| Line | What it does | Required? |
|---|---|---|
| `SARVAM_API_KEY=` | Telugu/Hindi/English understanding, voice notes, read-aloud, document reading. Get it at https://indus.sarvam.ai/key-management | Recommended |
| `OPENAI_API_KEY=` | Alternative model (a ChatGPT Plus plan is **not** an API key) | Optional |
| `SECRET_KEY=` | Signs logins, encrypts uploads. Use a long random string | Change it |

Generate a secret: `python -c "import secrets; print(secrets.token_urlsafe(48))"`

After editing: `docker compose up -d`. Then sign in and open **Settings → AI and messaging** to confirm the key shows as added.

**With no key the app still works.** Replies use offline rules, documents use on-server OCR, and voice notes are switched off with a clear message.

## 3. Demo accounts

Password for all: `niyamit-demo` (or just click the account on the login page).

| Email | Role |
|---|---|
| `nurse@sunrise.demo` | Nurse: worklist, reports, tasks (**main demo account**) |
| `doctor@sunrise.demo` | Doctor: approves plans, clinical questions |
| `reception@sunrise.demo` | Reception: calls and bookings |
| `admin@sunrise.demo` | Admin: settings, audit log, **Reset demo data** |
| `ops@niyamit.demo` | Platform support (no patient details) |
| `doctor@lakeview.demo` | Second clinic (proves clinics are isolated) |

Patients have no password. Open a patient record and click **Patient app link**. The link asks for the patient's year of birth, which is shown on the record.

## 4. Three-minute demo script

Sign in as **nurse@sunrise.demo**. Before each rehearsal: sign in as admin, go to **Test panel → Reset demo data**.

1. **Today**: the worklist of who is late, who replied, what is waiting.
2. **Language bridge**: *Patient phone (simulated)* → **Ramesh Kumar** → tap "Doctor, Monday nahi aa sakta. Saturday slot unda?". Then tap **hmm ok maybe**: an unsure reply gets a question, not a guess.
3. **Document to plan**: *Report inbox* → **lab_report_hba1c.pdf** (Venkat Rao) → confirm each outlined value → **Approve plan and schedule reminders**.
4. **Booking**: *Schedule* → **Book a time** for Imran Khan → pick a slot → **Book and send confirmation**. A booking reference appears.
5. **Barrier to task**: Phone → **Abdul Sattar** → "Paise nahi hain abhi, test baad mein karwaunga". *Tasks* now shows a cost task: assign, start, resolve.
6. **Safety**: Phone → **Meena Devi** → "Sugar 300 undi, tablet maarchala?" goes to the clinician queue. Click **Deliver last reply again** to show a repeated event creates nothing new. *Test panel → Run all scenarios* runs the failure cases live.
7. **Doctor view**: Venkat Rao's record → **Visit capsule**. Then *Metrics* and *Language evaluation → Start run*.

## 5. Run without Docker

**You need:** Python 3.12+, Node.js 20.9+, PostgreSQL 16, Redis 7 (and optionally Tesseract for offline OCR).

```bash
# one-time database setup (password: niyamit)
createuser -d -P niyamit
createdb -O niyamit niyamit

# Terminal 1: backend
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head && python -m app.seed
uvicorn app.main:app --reload --port 8000

# Terminal 2: worker (same folder, same venv)
celery -A app.worker worker -B --loglevel=INFO
# Windows: -B is not supported. Use two terminals instead:
#   celery -A app.worker worker --pool=solo --loglevel=INFO
#   celery -A app.worker beat --loglevel=INFO

# Terminal 3: web app
cd frontend
cp .env.example .env.local
npm install
npm run build && npm start        # or: npm run dev
```

Open http://localhost:3000.
No Redis or Celery? Add `TASKS_EAGER=true` and `INLINE_SCHEDULER=true` to `backend/.env` and skip Terminal 2.

**Tests:** `cd backend && pytest -q` (87 tests, including all 18 PRD acceptance gates). Web types: `cd frontend && npm run typecheck`.

## 6. Open the app on a phone (same Wi-Fi)

1. Find your laptop's IP, for example `192.168.1.20`.
2. In `backend/.env` set `PUBLIC_APP_URL=http://192.168.1.20:3000`, then `docker compose up -d`.
3. Allow port 3000 through your firewall, then open `http://192.168.1.20:3000` on the phone.

Typing and buttons work this way. **Voice notes need `localhost` or HTTPS**, because browsers only allow the microphone on secure pages.

## 7. Troubleshooting

- **"Not added" after pasting a key:** the key must be in `backend/.env` (not `.env.example`). Run `docker compose up -d`.
- **Port 3000 or 8000 in use:** stop the other app, or change the left-hand number under `ports:` in `docker-compose.yml`.
- **`env_file` / `required` error:** your Docker Compose is older than v2.24. Update Docker Desktop.
- **"The stored file cannot be read":** you changed `SECRET_KEY`. Reset demo data (admin → Test panel).
- **Patient link says it no longer works:** staff links last 24 hours, links in messages last 7 days. Make a new one.
- **A build fails:** run `docker compose logs backend worker` and check the error.

## 8. Status and what is left

**Done and tested** (on synthetic data): backend (87 tests passing), clinic web dashboard, patient web app in Telugu/Hindi/English, family-helper view.

**Built but not yet run on real infrastructure**
- `docker compose up --build` itself.
- Live Sarvam calls (voice, read-aloud, document reading). Tested only against mocked responses so far.
- WhatsApp channel (adapter written, switched off, never tested against Meta).
- Android patient app (Jetpack Compose): the source is **not in this repository yet** and it has never been compiled. To build it once added: open the `android/` folder in Android Studio and press Run, then set **Server address** in the app to your laptop's IP and allow port 3000 through the firewall.
- Push notifications: not built.

**Before the demo**
1. Run `docker compose up --build` on a team laptop and fix anything it reports.
2. Add the Sarvam key, then try a voice note, **Listen**, and a prescription upload.
3. Run **Language evaluation** again to get a live accuracy number.
4. Rehearse the 3-minute demo on freshly reset data.

**Before any real patient**
- A doctor must review every message template, especially the clinical and urgent replies (marked "pending clinical lead review").
- Native Telugu and Hindi speakers must check the app text and messages.
- Set `DEMO_MODE=false`, `APP_ENV=production`, a real `SECRET_KEY`, and HTTPS with `COOKIE_SECURE=true`.
- Review Sarvam's (and OpenAI's) data-processing terms before sending any real health data.

**Known limits**
- The offline rules scored 48 of 52 synthetic messages (92%). They were written alongside that test set, so the figure is optimistic. Quote the live Sarvam result once you have it.
- Offline OCR reads English text only.
- Everything is synthetic: patients, clinics, documents and message wording.

## 9. Project layout

```
docker-compose.yml   postgres, redis, backend, worker, frontend
backend/             FastAPI + SQLAlchemy + Alembic + Celery
  app/               routers, services, AI adapters, channels
  eval/              52 labelled synthetic test messages
  samples/           synthetic prescriptions and a lab report
  tests/             acceptance gates, reliability, language tests
frontend/            Next.js 15 + React 19 + TypeScript
  app/(staff)/       clinic screens
  app/p/[token]      patient app
  app/c/[token]      family-helper view
```

Built for Health-a-thon 2026 from the Niyamit Care Bridge PRD.
