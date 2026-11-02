"""Deterministic date handling. The AI never computes dates; this module does, and it refuses to guess.

Day words cover English, Hindi and Telugu (Latin and native script) for the tested language pairs.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

WEEKDAY_WORDS: dict[int, list[str]] = {
    0: ["monday", "mon", "somvar", "somwar", "somavaram", "somavaaram", "सोमवार", "సోమవారం"],
    1: ["tuesday", "tue", "tues", "mangalvar", "mangalwar", "mangalavaram", "मंगलवार", "మంగళవారం"],
    2: ["wednesday", "wed", "budhvar", "budhwar", "budhavaram", "बुधवार", "బుధవారం"],
    3: ["thursday", "thu", "thur", "thurs", "guruvar", "guruwar", "brihaspativar", "guruvaram", "गुरुवार", "గురువారం"],
    4: ["friday", "fri", "shukravar", "shukrawar", "sukravaram", "shukravaram", "शुक्रवार", "శుక్రవారం"],
    5: ["saturday", "sat", "shanivar", "shaniwar", "sanivaram", "shanivaram", "शनिवार", "శనివారం"],
    6: ["sunday", "sun", "ravivar", "raviwar", "itvar", "aadivaram", "adivaram", "रविवार", "आदित्यवार", "ఆదివారం"],
}
TOMORROW = ["tomorrow", "tmrw", "repu", "రేపు"]
DAY_AFTER = ["day after tomorrow", "ellundi", "ఎల్లుండి"]
AMBIGUOUS_DAY = ["kal", "कल", "parso", "परसों"]  # Hindi 'kal' means both yesterday and tomorrow
VAGUE = ["next week", "agle hafte", "agle week", "vachhe vaaram", "vache varam", "vacche vaaram",
         "వచ్చే వారం", "this week", "is hafte", "ee vaaram", "weekend", "later", "baad mein", "tarvata",
         "some other day", "another day", "vere roju", "dusre din", "दूसरे दिन", "వేరే రోజు"]
# A day word directly followed or preceded by one of these is the day the patient CANNOT do.
NEGATION_AFTER = ["nahi", "nahin", "नहीं", "kaadu", "kadu", "కాదు", "raalenu", "raanu", "rakudadu", "రాలేను",
                  "not possible", "is not", "won't", "cannot", "can't"]
NEGATION_BEFORE = ["not", "no", "except"]
# "next Saturday" said on a Friday may mean tomorrow or the Saturday after; the patient is asked which one.
NEXT_WORDS = ["next", "agle", "agli", "agla", "vachhe", "vache", "vacche", "vachche", "अगले", "अगली", "అగ్లే", "వచ్చే"]

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5,
    "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "").lower()
    return re.sub(r"\s+", " ", text).strip()


def _contains_word(text: str, word: str) -> bool:
    if re.search(r"[^\x00-\x7f]", word):  # native script: substring match
        return word in text
    return re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", text) is not None


@dataclass
class DayResolution:
    kind: str  # EXPLICIT | WEEKDAY | RELATIVE | VAGUE | AMBIGUOUS | NONE
    candidate: date | None
    matched: str | None
    question: str | None  # narrow clarification question when we cannot resolve
    options: list[date] = field(default_factory=list)  # the dates the patient chooses between (AMBIGUOUS only)


def next_weekday(today: date, weekday: int) -> date:
    days = (weekday - today.weekday()) % 7
    return today + timedelta(days=days or 7)


def _positions(text: str, word: str) -> list[int]:
    if re.search(r"[^\x00-\x7f]", word):
        return [m.start() for m in re.finditer(re.escape(word), text)]
    return [m.start() for m in re.finditer(rf"(?<![a-z]){re.escape(word)}(?![a-z])", text)]


def _word_before(text: str, start: int) -> str:
    """The whitespace-separated token right before a position ('' across a comma). Works for any script."""
    before = text[max(0, start - 24): start].rstrip()
    if not before or before.endswith(","):
        return ""
    return before.split()[-1].strip(".!?;:'\"()")


def _next_weekday_mention(t: str, pos: int, word: str, cand: date, today: date) -> DayResolution:
    """'next Saturday': unambiguous when the coming Saturday is already in next week, otherwise ask."""
    prev = _word_before(t, pos)
    if prev not in NEXT_WORDS:
        return DayResolution("WEEKDAY", cand, word, None)
    matched = f"{prev} {word}"
    if cand.isocalendar()[:2] != today.isocalendar()[:2]:
        return DayResolution("WEEKDAY", cand, matched, None)
    later = cand + timedelta(days=7)
    return DayResolution("AMBIGUOUS", None, matched,
                         f"Do you mean {cand:%A} {cand.day} {cand:%b} or {later:%A} {later.day} {later:%b}? "
                         "Pick a time on the day you mean.", [cand, later])


def _tokens(text: str) -> list[str]:
    """Whitespace tokens without edge punctuation. (\\w splits Telugu and Hindi words at vowel signs.)"""
    return [t for t in (w.strip(".,!?;:'\"()") for w in text.split()) if t]


def _negated(text: str, start: int, word: str) -> bool:
    after = text[start + len(word): start + len(word) + 18]
    before = text[max(0, start - 14): start]
    after_words = _tokens(after)[:2]
    if any(n in " ".join(after_words) for n in NEGATION_AFTER if " " in n) or any(w in NEGATION_AFTER for w in after_words):
        return True
    before_words = _tokens(before)
    if before_words and before_words[-1] in NEXT_WORDS:  # "not next Monday"
        before_words = before_words[:-1]
    # only the word directly before the day counts ("not Monday"), and only without a comma in between
    direct = before_words[-1] if before_words and not before.rstrip().endswith(",") else ""
    return direct in NEGATION_BEFORE or before.rstrip().endswith("instead of")


def resolve_day_expression(text: str | None, today: date) -> DayResolution:
    """Turn a patient's day words into a candidate date. Candidates always need the patient to confirm
    (by choosing a slot on that day); vague or ambiguous phrases return a question instead.

    'Monday nahi aa sakta, Saturday slot unda?' -> Saturday (the negated day is skipped)."""
    t = normalize(text or "")
    if not t:
        return DayResolution("NONE", None, None, None)
    explicit = parse_explicit_date(t, today)
    if explicit:
        return DayResolution("EXPLICIT", explicit, t, None)
    dom = _day_of_month(t, today)
    if dom:
        return DayResolution("EXPLICIT", dom[0], dom[1], None)
    mentions: list[tuple[int, str, date | None, str]] = []  # (pos, kind, candidate, word)
    for w in DAY_AFTER:
        mentions += [(p, "RELATIVE", today + timedelta(days=2), w) for p in _positions(t, w)]
    for w in TOMORROW:
        mentions += [(p, "RELATIVE", today + timedelta(days=1), w) for p in _positions(t, w)]
    for wd, words in WEEKDAY_WORDS.items():
        for w in words:
            mentions += [(p, "WEEKDAY", next_weekday(today, wd), w) for p in _positions(t, w)]
    # drop shorter words inside longer matches (e.g. 'sat' inside 'saturday') and negated mentions
    mentions.sort(key=lambda m: (m[0], -len(m[3])))
    kept: list[tuple[int, str, date | None, str]] = []
    for m in mentions:
        if kept and m[0] < kept[-1][0] + len(kept[-1][3]):
            continue
        kept.append(m)
    usable = [m for m in kept if not _negated(t, m[0], m[3])]
    if usable:
        pos, kind, cand, word = usable[-1]
        if kind == "WEEKDAY" and cand is not None:
            return _next_weekday_mention(t, pos, word, cand, today)
        return DayResolution(kind, cand, word, None)
    for w in AMBIGUOUS_DAY:
        if _contains_word(t, w):
            return DayResolution("AMBIGUOUS", None, w, "Which day would you like to come? Please pick a date.")
    for w in VAGUE:
        if _contains_word(t, w):
            return DayResolution("VAGUE", None, w, "Which day suits you? Please pick a date below.")
    if kept:  # only negated days were mentioned ("not Monday")
        return DayResolution("VAGUE", None, kept[-1][3], "Which other day suits you? Please pick a date below.")
    return DayResolution("NONE", None, None, None)


# "12 tareekh", "12 date ko", "on the 5th", "12 తేదీ": a day of the month without a month name
_DOM = re.compile(r"\b(\d{1,2})\s*(?:st|nd|rd|th)?\s*(?:tareekh|tarikh|taarikh|tarik|tedi|tedhi|thedi|date)\b"
                  r"|\b(\d{1,2})(?:st|nd|rd|th)\b|\b(\d{1,2})\s*(?:तारीख|తేదీ)")


def _day_of_month(t: str, today: date) -> tuple[date, str] | None:
    """Next calendar date with that day number (this month if still ahead, otherwise the next month)."""
    m = _DOM.search(t)
    if not m:
        return None
    day = int(next(g for g in m.groups() if g))
    year, month = today.year, today.month
    for _ in range(3):
        try:
            d = date(year, month, day)
            if d >= today:
                return d, m.group(0).strip()
        except ValueError:
            pass
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return None


_NUMERIC = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b")
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DAY_MON = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s\-]+([a-z]{3,9})\.?,?[\s\-]*(\d{2,4})?\b")
_MON_DAY = re.compile(r"\b([a-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})?\b")
_MON_YEAR = re.compile(r"\b([a-z]{3,9})\.?[\s\-,]+(\d{4})\b")


def _year(y: str | None, today: date) -> int | None:
    if not y:
        return None
    n = int(y)
    return 2000 + n if n < 100 else n


def parse_explicit_date(text: str, today: date, *, allow_missing_year: bool = True) -> date | None:
    """Parse a written calendar date. Indian convention: day first (dd/mm/yyyy)."""
    t = normalize(text)
    if m := _ISO.search(t):
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    if m := _NUMERIC.search(t):
        try:
            return date(_year(m[3], today) or today.year, int(m[2]), int(m[1]))
        except ValueError:
            return None
    if m := _DAY_MON.search(t):
        mon = MONTHS.get(m[2])
        if mon:
            yr = _year(m[3], today)
            if yr is None and not allow_missing_year:
                return None
            try:
                d = date(yr or today.year, mon, int(m[1]))
            except ValueError:
                return None
            if yr is None and d < today:
                d = date(today.year + 1, mon, int(m[1]))
            return d
    if m := _MON_DAY.search(t):
        mon = MONTHS.get(m[1])
        if mon:
            yr = _year(m[3], today)
            if yr is None and not allow_missing_year:
                return None
            try:
                d = date(yr or today.year, mon, int(m[2]))
            except ValueError:
                return None
            if yr is None and d < today:
                d = date(today.year + 1, mon, int(m[2]))
            return d
    return None


def parse_month_year(text: str) -> tuple[int, int] | None:
    """'Dec 2026' -> (2026, 12). A month without a day is not a due date; the reviewer must pick a day."""
    t = normalize(text)
    if m := _MON_YEAR.search(t):
        mon = MONTHS.get(m[1])
        if mon:
            return int(m[2]), mon
    return None


_INTERVAL = re.compile(
    r"\b(?:after|in|within|next)?\s*(\d{1,2}|one|two|three|four|six|twelve)\s*"
    r"(day|days|week|weeks|wk|wks|month|months|mo|mths|mnths)\b"
)
_WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "six": 6, "twelve": 12}


def parse_interval(text: str) -> relativedelta | None:
    """'after 3 months' -> relativedelta(months=3)."""
    t = normalize(text)
    m = _INTERVAL.search(t)
    if not m:
        return None
    n = int(m[1]) if m[1].isdigit() else _WORD_NUM[m[1]]
    unit = m[2]
    if unit.startswith("d"):
        return relativedelta(days=n)
    if unit.startswith("w"):
        return relativedelta(weeks=n)
    return relativedelta(months=n)
