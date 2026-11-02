"""Patient app behaviour that the PRD's gates do not spell out: day questions, offered times, button taps."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from tests.conftest import login, new_patient, patient_session


def _reply(client, path: str, body: dict) -> dict:
    r = client.post(path, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_next_saturday_offers_both_saturdays_and_asks(nurse, seeded):
    client = nurse
    pid = new_patient(client, "Next Saturday Test", "+919000300001", language="en", plan_days=12)
    patient_session(client, "nurse@sunrise.demo", pid)
    view = _reply(client, "/v1/p/replies", {"text": "Cannot come this week. Next Saturday possible?", "client_key": "next-saturday-0001"})
    act = next(a for a in view["actions"] if a["intent"] == "RESCHEDULE_REQUEST")
    today = date.fromisoformat(client.get("/v1/p/home").json()["today"])
    upcoming = today + timedelta(days=(5 - today.weekday()) % 7 or 7)
    if upcoming.isocalendar()[:2] == today.isocalendar()[:2]:
        assert act["question_key"] == "WHICH_DAY"
        assert act["date_options"] == [upcoming.isoformat(), (upcoming + timedelta(days=7)).isoformat()]
        assert act["slots"] and {s["date"] for s in act["slots"]} <= set(act["date_options"])
    else:  # run on a weekend: the coming Saturday is already next week, so there is nothing to ask
        assert act["question_key"] in ("CONFIRM_DAY", "NO_SLOTS_ON_DAY") and act["candidate_date"] == upcoming.isoformat()


def test_times_offered_without_a_day_are_spread_and_not_too_soon(nurse, seeded):
    client = nurse
    pid = new_patient(client, "Spread Slots Test", "+919000300002", language="hi", plan_days=8)
    patient_session(client, "nurse@sunrise.demo", pid)
    view = _reply(client, "/v1/p/replies/button", {"choice": "RESCHEDULE", "client_key": "spread-slots-0001"})
    act = next(a for a in view["actions"] if a["intent"] == "RESCHEDULE_REQUEST")
    slots = act["slots"]
    assert act["question_key"] == "PICK_DAY" and slots
    per_day: dict[str, int] = {}
    for s in slots:
        per_day[s["date"]] = per_day.get(s["date"], 0) + 1
    assert max(per_day.values()) <= 3 and len(slots) <= 9
    soonest = min(datetime.fromisoformat(s["starts_at"]) for s in slots)
    assert soonest >= datetime.now(ZoneInfo("UTC")) + timedelta(minutes=85)


def test_a_tapped_button_is_described_not_quoted(nurse, seeded):
    client = nurse
    pid = new_patient(client, "Button Words Test", "+919000300003", language="te")
    patient_session(client, "nurse@sunrise.demo", pid)
    view = _reply(client, "/v1/p/replies/button", {"choice": "BARRIER:COST", "client_key": "button-words-0001"})
    assert view["processing"] is False  # buttons need no AI and are answered at once
    assert any(a["intent"] == "BARRIER_REPORTED" and a["status"] == "DONE" for a in view["actions"])
    login(client, "nurse@sunrise.demo")
    task = next(t for t in client.get("/v1/tasks", params={"patient_id": pid}).json()["tasks"] if t["category"] == "BARRIER")
    assert task["patient_statement"] is None and task["barrier_category"] == "COST"
    events = client.get(f"/v1/patients/{pid}/timeline").json()["events"]
    tapped = next(e for e in events if e["type"] == "PATIENT_REPLY")
    assert "tapped" in tapped["summary"] and "Difficulty coming: cost" in tapped["summary"]
    assert tapped["patient_words"] is None and "BARRIER:COST" not in tapped["summary"]
