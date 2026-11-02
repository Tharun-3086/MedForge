"""Plain-English names for patient choices, used wherever staff see what a patient tapped or typed."""
from __future__ import annotations

from app.enums import BarrierCategory

BARRIER_NAMES = {"TIMING": "the time does not suit", "TRANSPORT": "travel or transport", "COST": "cost",
                 "CONFUSION": "not sure what to do", "FEELING_WELL": "feels fine, sees no need",
                 "CAREGIVER_LOGISTICS": "no one to come with", "OTHER": "something else",
                 "PREFER_NOT_TO_SAY": "prefers not to say"}
CHOICE_LABELS: dict[str, str] = {
    "CONFIRM": "I will come", "1": "I will come", "RESCHEDULE": "Change the date", "2": "Change the date",
    "CALLBACK": "Please call me", "3": "Please call me", "UPLOAD": "Share a report", "STOP": "Stop reminders",
    "OPT_OUT": "Stop reminders", "START": "Start reminders again",
    **{f"BARRIER:{b.value}": f"Difficulty coming: {BARRIER_NAMES[b.value]}" for b in BarrierCategory},
}
