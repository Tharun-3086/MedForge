"""Small shared helpers: clinic time, scoped lookups, current follow-up item, fault flags."""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import utcnow
from app.enums import ItemStatus, PlanStatus
from app.models import Clinic, FollowUpItem, FollowUpPlan, Patient, SystemFlag

FAULTS = {
    "ASR_TIMEOUT": "Speech-to-text provider times out",
    "LLM_TIMEOUT": "Language model times out (rules fallback is used)",
    "DOC_PROVIDER_DOWN": "Document AI provider is unavailable",
    "BOOKING_PROVIDER_DOWN": "Booking service is unavailable",
    "CHANNEL_SEND_FAIL": "Messaging channel rejects messages (permanent failure)",
}


def clinic_tz(clinic: Clinic) -> ZoneInfo:
    return ZoneInfo(clinic.timezone or "Asia/Kolkata")


def day_label(d: date, weekday: str = "") -> str:
    """'9 Nov', or 'Mon 9 Nov' / 'Monday 9 Nov' with weekday='%a' / '%A' (no leading zeros)."""
    return (f"{d:{weekday}} " if weekday else "") + f"{d.day} {d:%b}"


def time_label(local: datetime) -> str:
    """'4:00 PM' (no leading zero)."""
    return f"{local.hour % 12 or 12}:{local:%M} {'AM' if local.hour < 12 else 'PM'}"


def slot_label(local: datetime, year: bool = False) -> str:
    """'Sat 31 Oct, 10:00 AM' in the clinic's local time."""
    return f"{day_label(local.date(), '%a')}{f' {local.year}' if year else ''}, {time_label(local)}"


MONTH_NAMES = {
    "hi": ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"],
    "te": ["జనవరి", "ఫిబ్రవరి", "మార్చి", "ఏప్రిల్", "మే", "జూన్", "జూలై", "ఆగస్టు", "సెప్టెంబర్", "అక్టోబర్", "నవంబర్",
           "డిసెంబర్"],
}
WEEKDAY_NAMES = {
    "hi": ["सोम", "मंगल", "बुध", "गुरु", "शुक्र", "शनि", "रवि"],
    "te": ["సోమ", "మంగళ", "బుధ", "గురు", "శుక్ర", "శని", "ఆది"],
}


def local_day_label(d: date, lang: str, weekday: bool = False) -> str:
    """'21 Oct' / '21 अक्टूबर' / '21 అక్టోబర్' for patient messages, in the patient's language."""
    if lang not in MONTH_NAMES:
        return day_label(d, "%a" if weekday else "")
    text = f"{d.day} {MONTH_NAMES[lang][d.month - 1]}"
    if weekday:
        text = f"{WEEKDAY_NAMES[lang][d.weekday()]}, {text}"
    # Telugu templates attach case endings ("{due_date}న"); a zero-width non-joiner keeps the final halant visible.
    return text + ("\u200c" if lang == "te" else "")


def local_slot_label(local: datetime, lang: str) -> str:
    return slot_label(local) if lang not in MONTH_NAMES else f"{local_day_label(local.date(), lang, True)}, {time_label(local)}"


def clinic_today(clinic: Clinic) -> date:
    return datetime.now(clinic_tz(clinic)).date()


def local_dt(clinic: Clinic, d: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(d, time(hour, minute), tzinfo=clinic_tz(clinic))


def in_quiet_hours(clinic: Clinic, when: datetime) -> bool:
    h = when.astimezone(clinic_tz(clinic)).hour
    start, end = clinic.quiet_hours_start, clinic.quiet_hours_end
    return (h >= start or h < end) if start > end else (start <= h < end)


def next_allowed_send_time(clinic: Clinic, when: datetime) -> datetime:
    local = when.astimezone(clinic_tz(clinic))
    if not in_quiet_hours(clinic, when):
        return when
    target = local.replace(hour=clinic.quiet_hours_end, minute=0, second=0, microsecond=0)
    if local.hour >= clinic.quiet_hours_end:
        target += timedelta(days=1)
    return target


def active_faults(db: Session) -> set[str]:
    if not settings.demo_mode:
        return set()
    return set(db.scalars(select(SystemFlag.key).where(SystemFlag.enabled.is_(True))))


def set_fault(db: Session, key: str, enabled: bool) -> None:
    flag = db.get(SystemFlag, key)
    if flag is None:
        db.add(SystemFlag(key=key, enabled=enabled))
    else:
        flag.enabled = enabled


def get_clinic(db: Session, clinic_id: uuid.UUID) -> Clinic:
    clinic = db.get(Clinic, clinic_id)
    assert clinic is not None
    return clinic


def active_items(db: Session, patient_id: uuid.UUID) -> list[FollowUpItem]:
    return list(db.scalars(
        select(FollowUpItem)
        .join(FollowUpPlan, FollowUpItem.plan_id == FollowUpPlan.id)
        .where(FollowUpItem.patient_id == patient_id, FollowUpPlan.status == PlanStatus.ACTIVE,
               FollowUpItem.status.in_([ItemStatus.PENDING, ItemStatus.CONFIRMED_BY_PATIENT, ItemStatus.BOOKED]))
        .order_by(FollowUpItem.due_date)
    ))


def same_visit_items(db: Session, item: FollowUpItem) -> list[FollowUpItem]:
    """Open follow-ups of the same patient due on the same day: one visit, so they are confirmed and booked together."""
    return [i for i in active_items(db, item.patient_id) if i.due_date == item.due_date] or [item]


def current_item(db: Session, patient_id: uuid.UUID) -> FollowUpItem | None:
    """The follow-up a patient's reply most likely refers to: the earliest open item of the active plan."""
    items = active_items(db, patient_id)
    return items[0] if items else None


def first_name(patient: Patient) -> str:
    return (patient.display_name or "").split()[0] if patient.display_name else ""


def hours_from_now(hours: int) -> datetime:
    return utcnow() + timedelta(hours=hours)
