"""Deterministic offline fallback: keyword intent rules and line-based document extraction.

Used when no AI key is configured or a provider fails. Transparent and labelled as 'RULES' everywhere.
Lexicons cover English, Hindi and Telugu (Latin + native script). Extend them as the test corpus grows.
"""
from __future__ import annotations

import re

from app.ai.contracts import FieldCandidate, ReplyUnderstanding
from app.ai.dates import _contains_word, normalize, parse_explicit_date, parse_interval, parse_month_year, resolve_day_expression
from app.enums import BarrierCategory, Intent, TimeWindow

URGENT = [
    "chest pain", "chest is paining", "pain in chest", "fainted", "fainting", "unconscious", "not waking up",
    "can't breathe", "cannot breathe", "breathless", "difficulty breathing", "shortness of breath",
    "sugar is very low", "very low sugar", "sugar very low", "shaking and sweating", "sweating and shaking",
    "slurred speech", "seizure", "fits", "emergency",
    "seene mein dard", "seene me dard", "chhati mein dard", "chhati me dard", "saans nahi", "saans lene mein",
    "behosh", "sugar bahut kam", "sugar bahut low", "सीने में दर्द", "बेहोश", "सांस नहीं",
    "chest lo noppi", "chaati lo noppi", "chaathi noppi", "chaati noppi", "gunde noppi", "gundelo noppi",
    "upiri adatledu", "upiri adatam ledu", "spruha ledu", "spruha tappindi", "sugar chala takkuva",
    "ఛాతీ నొప్పి", "గుండె నొప్పి", "స్పృహ లేదు", "ఊపిరి ఆడటం లేదు",
]
CLINICAL = [
    "dose", "dosage", "tablet", "tablets", "medicine", "medicines", "insulin", "metformin", "glimepiride",
    "side effect", "side effects", "should i take", "can i take", "can i stop", "sugar level", "sugar is high",
    "sugar high", "high sugar", "what does my report", "is my report", "report normal", "what should i eat",
    "can i eat", "numbness", "burning feet", "itching", "pain",
    "dawai", "dawa", "goli", "goliyan", "kitni goli", "dose badha", "dose kam", "sugar zyada", "sugar badh",
    "report mein kya", "kya khana", "khana kya", "दवा", "दवाई", "गोली", "शुगर ज्यादा",
    "mandu", "mandulu", "golilu", "maatra", "sugar ekkuva", "sugar perigindi", "report lo emundi",
    "emi tinali", "tinavaccha", "noppi", "మందు", "మందులు", "మాత్ర", "షుగర్ ఎక్కువ", "నొప్పి",
]
OPT_OUT_PHRASES = [
    "stop messages", "stop sending", "stop reminders", "stop these", "unsubscribe", "don't message",
    "dont message", "do not message", "no more messages", "don't send", "dont send", "remove me", "opt out",
    "optout", "band karo", "band kar do", "message mat bhejo", "messages mat bhejo", "mat bhejo",
    "messages band", "मैसेज मत भेजो", "बंद करो", "messages vaddu", "message vaddu", "pampakandi", "pampoddu",
    "aapandi", "aapeyandi", "మెసేజ్ వద్దు", "పంపకండి", "ఆపండి",
]
CALLBACK = [
    "call me", "call back", "callback", "please call", "give me a call", "ring me", "talk to someone",
    "speak to the doctor", "speak to doctor", "speak to nurse", "call karo", "call kijiye", "call kar do",
    "phone karo", "phone kijiye", "baat karni hai", "baat karna hai", "फोन करो", "कॉल करो", "call cheyandi",
    "phone cheyandi", "call cheyyandi", "maatladali", "matladali", "ఫోన్ చేయండి", "కాల్ చేయండి",
]
REPORT_WORDS = ["report", "reports", "रिपोर्ट", "రిపోర్ట్"]
UPLOAD_WORDS = ["upload", "send", "sending", "share", "attach", "bhej", "bhejunga", "bhejungi", "bhejta", "bhejti",
                "pampistha", "pampista", "pamputa", "pampanu", "pampinchanu", "chestha", "chesta", "భేజ", "भेज",
                "పంపిస్తా", "అప్‌లోడ్"]
RESCHEDULE = [
    "reschedule", "change the date", "change date", "another date", "another day", "different day", "postpone",
    "prepone", "can't come", "cannot come", "can not come", "won't be able to come", "not able to come",
    "unable to come", "slot", "slots", "later date", "move my appointment", "shift my appointment",
    "nahi aa sakta", "nahi aa sakti", "nahi aa paunga", "nahi aa paungi", "nahin aa", "nahi aa", "date badal",
    "tarikh badal", "dusre din", "doosre din", "koi aur din", "aage kar", "नहीं आ सकता", "नहीं आ सकती",
    "raalenu", "raaleka", "raalenanu", "raavadam kudaradu", "vere roju", "date maarchandi", "date marchandi",
    "vere slot", "postpone cheyandi", "రాలేను", "వేరే రోజు",
]
NEGATIVE_ATTENDANCE = [
    "can't come", "cannot come", "can not come", "won't come", "not able to come", "unable to come",
    "won't be able to come", "nahi aa", "nahin aa", "नहीं आ", "raalenu", "raaleka", "raalenanu", "raanu",
    "రాలేను", "kaadu",
]
CONFIRM = [
    "yes", "ok", "okay", "confirm", "confirmed", "i will come", "i'll come", "will come", "will be there",
    "i am coming", "coming", "sure", "haan", "ji haan", "theek hai", "thik hai", "aa jaunga", "aa jaungi",
    "aaunga", "aaungi", "pakka", "zaroor", "हाँ", "आऊंगा", "आऊंगी", "ठीक है", "avunu", "sare", "ok andi",
    "vastanu", "vasthanu", "vasta", "vastha", "tappakunda", "అవును", "సరే", "వస్తాను",
]
# A hedged "ok" is not a confirmation: these words turn a bare confirmation into a clarifying question.
HEDGES = [
    "maybe", "may be", "not sure", "don't know", "dont know", "hmm", "later", "perhaps", "might", "will try",
    "shayad", "pata nahi", "dekhte hain", "dekhenge", "baad mein", "शायद", "पता नहीं", "देखते हैं",
    "emo", "chuddam", "chustanu", "chustha", "telidu", "ఏమో", "తెలియదు", "చూద్దాం",
]
BARRIERS: list[tuple[BarrierCategory, list[str]]] = [
    (BarrierCategory.COST, ["money", "cost", "expensive", "afford", "fees", "charges", "paisa", "paise", "kharcha",
                            "mehenga", "पैसे", "खर्चा", "dabbulu", "dabbu", "kharchu", "డబ్బులు", "ఖర్చు"]),
    (BarrierCategory.TRANSPORT, ["bus", "transport", "vehicle", "travel", "too far", "distance", "gaadi",
                                 "door hai", "kiraya", "dooram", "dooranga", "vehicle ledu", "దూరం", "బస్సు"]),
    (BarrierCategory.CAREGIVER_LOGISTICS, ["no one to bring", "nobody to bring", "no one to come with", "son is away",
                                           "no one to take me", "nobody to take me", "no one can bring",
                                           "nobody can bring", "no one can take", "no one to accompany",
                                           "daughter is away", "koi saath", "koi nahi hai saath", "beta bahar",
                                           "akela", "akeli", "evaru leru", "todu evaru", "koduku ledu",
                                           "okkadine", "okkatine", "తోడు ఎవరూ"]),
    (BarrierCategory.TIMING, ["work", "office", "duty", "night shift", "leave", "busy", "no time", "exam",
                              "kaam", "chutti", "time nahi", "fursat", "pani", "leave dorakadu", "time ledu",
                              "సమయం లేదు", "ఆఫీస్"]),
    (BarrierCategory.FEELING_WELL, ["feeling fine", "feel fine", "i am fine", "feeling good", "no need",
                                    "sugar is normal", "sugar is under control", "theek hoon", "thik hoon",
                                    "sab theek", "zarurat nahi", "baagane unna", "bagane unnanu", "baagunna",
                                    "avasaram ledu", "control lo undi", "అవసరం లేదు"]),
    (BarrierCategory.CONFUSION, ["don't understand", "dont understand", "confused", "not clear", "samajh nahi",
                                 "pata nahi kya", "ardham kaaledu", "ardham kaledu", "emi cheyyalo", "అర్థం కాలేదు"]),
]
TIME_WINDOWS: list[tuple[TimeWindow, list[str]]] = [
    (TimeWindow.MORNING, ["morning", "subah", "podduna", "poddunne", "udayam", "सुबह", "ఉదయం"]),
    (TimeWindow.AFTERNOON, ["afternoon", "dopahar", "madhyahnam", "दोपहर", "మధ్యాహ్నం"]),
    (TimeWindow.EVENING, ["evening", "shaam", "sham", "saayantram", "sayantram", "शाम", "సాయంత్రం"]),
]


def _hits(t: str, words: list[str]) -> list[str]:
    return [w for w in words if _contains_word(t, w)]


HEDGED_REASON = "Sounds unsure — ask before recording a confirmation"


def is_hedged(text: str) -> bool:
    return bool(_hits(normalize(text), HEDGES))


def classify(text: str) -> ReplyUnderstanding:
    """Keyword rules. Conservative: unclear input -> OTHER_OR_UNCLEAR with low confidence."""
    t = normalize(text)
    intents: list[Intent] = []
    evidence: list[str] = []

    urgent = _hits(t, URGENT)
    clinical = _hits(t, CLINICAL)
    opt_out = _hits(t, OPT_OUT_PHRASES) or (["stop"] if t.strip(" .!") in {"stop", "stop all"} else [])
    callback = _hits(t, CALLBACK)
    report = _hits(t, REPORT_WORDS) and _hits(t, UPLOAD_WORDS)
    resched = _hits(t, RESCHEDULE)
    negative = _hits(t, NEGATIVE_ATTENDANCE)
    confirm = _hits(t, CONFIRM) if not negative else []
    barrier_cat, barrier_words = None, []
    for cat, words in BARRIERS:
        if h := _hits(t, words):
            barrier_cat, barrier_words = cat, h
            break

    if urgent:
        intents.append(Intent.URGENT_CONCERN)
        evidence += urgent
    elif clinical and not (report and not re.search(r"\?|kya|enti|emiti|what|why|enduku", t)):
        intents.append(Intent.CLINICAL_QUESTION)
        evidence += clinical
    if opt_out:
        intents.append(Intent.OPT_OUT)
        evidence += opt_out
    if callback:
        intents.append(Intent.CALLBACK_REQUEST)
        evidence += callback
    if resched or (negative and not opt_out):
        intents.append(Intent.RESCHEDULE_REQUEST)
        evidence += resched or negative
    if report:
        intents.append(Intent.REPORT_UPLOAD_INTENT)
        evidence += report
    if barrier_cat and Intent.URGENT_CONCERN not in intents:
        intents.append(Intent.BARRIER_REPORTED)
        evidence += barrier_words
    if confirm and not intents:
        intents.append(Intent.CONFIRM_FOLLOWUP)
        evidence += confirm

    day = resolve_day_expression(text, _today_for_rules())
    window = next((w for w, words in TIME_WINDOWS if _hits(t, words)), None)
    if not intents and day.kind in {"WEEKDAY", "EXPLICIT", "RELATIVE"}:
        intents.append(Intent.RESCHEDULE_REQUEST)  # a bare new day is a scheduling request
        evidence.append(day.matched or "")

    if not intents:
        return ReplyUnderstanding(intents=[Intent.OTHER_OR_UNCLEAR], source_text=text[:200], confidence=0.3,
                                  needs_clarification=True, clarification_reason="No supported request recognised")
    if intents == [Intent.CONFIRM_FOLLOWUP] and is_hedged(text):
        return ReplyUnderstanding(intents=[Intent.OTHER_OR_UNCLEAR], source_text=text[:200], confidence=0.4,
                                  needs_clarification=True, clarification_reason=HEDGED_REASON)

    strong = len(set(evidence))
    confidence = 0.55 if (intents == [Intent.CONFIRM_FOLLOWUP] and len(t) <= 3) else min(0.85, 0.6 + 0.1 * strong)
    source = _source_span(text, evidence)
    needs_clar = Intent.RESCHEDULE_REQUEST in intents and day.kind in {"VAGUE", "AMBIGUOUS"}
    return ReplyUnderstanding(
        intents=intents,
        requested_day_text=day.matched if day.kind in {"WEEKDAY", "EXPLICIT", "RELATIVE", "VAGUE", "AMBIGUOUS"} else None,
        requested_time_window=window,
        barrier_category=barrier_cat if Intent.BARRIER_REPORTED in intents else None,
        clinical_question_present=Intent.CLINICAL_QUESTION in intents,
        urgent_concern_present=Intent.URGENT_CONCERN in intents,
        opt_out_present=Intent.OPT_OUT in intents,
        source_text=source,
        english_gloss=None,
        confidence=round(confidence, 2),
        needs_clarification=needs_clar,
        clarification_reason=day.question if needs_clar else None,
    )


def _source_span(text: str, evidence: list[str]) -> str:
    parts = re.split(r"(?<=[.?!।])\s+", text.strip())
    for part in parts:
        p = normalize(part)
        if any(_contains_word(p, w) for w in evidence if w):
            return part[:200]
    return text[:200]


def _today_for_rules():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Kolkata")).date()


# ------------------------------------------------------------------------------ documents
DOC_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("document_date", re.compile(r"^\s*(date|dated|report date|visit date)\b", re.I)),
    ("next_review_date", re.compile(r"\b(review|next visit|follow[\s-]?up|revisit|f/u|come back)\b", re.I)),
    ("hba1c_due_date", re.compile(r"\bhb\W?a\W*[1il]\W*c|glycated|glycosylated", re.I)),  # tolerant of OCR noise
    ("eye_exam_due_date", re.compile(r"\b(eye|retina|retinal|fundus|ophthalm)\w*", re.I)),
    ("foot_exam_due_date", re.compile(r"\bfoot|feet\b", re.I)),
    ("kidney_test_due_date", re.compile(r"\b(kidney|kft|rft|creatinine|uacr|urine albumin|microalbumin)\b", re.I)),
    ("refill_due_date", re.compile(r"\b(refill|repeat prescription|medicines? for \d+ (days|weeks)|until)\b", re.I)),
]
DOC_TYPE_HINTS = [
    ("PRESCRIPTION", re.compile(r"\b(rx|prescription|advice|plan / follow-up)\b", re.I)),
    ("LAB_REPORT", re.compile(r"\b(lab|laboratory|test report|sample collected|specimen)\b", re.I)),
    ("REGISTER", re.compile(r"\b(register|opd list)\b", re.I)),
]


def extract_document(blocks: list[dict]) -> list[FieldCandidate]:
    """Line rules over OCR/text blocks. Every candidate cites the block it came from."""
    out: list[FieldCandidate] = []
    full = "\n".join(b["text"] for b in blocks)
    doc_type = next((name for name, pat in DOC_TYPE_HINTS if pat.search(full)), "OTHER")
    first = blocks[0]["id"] if blocks else ""
    out.append(FieldCandidate(name="document_type", value=doc_type, quote=blocks[0]["text"][:120] if blocks else "",
                              block_ids=[first] if first else [], confidence=0.5))
    for b in blocks:
        line = b["text"]
        for name, pat in DOC_PATTERNS:
            if not pat.search(line):
                continue
            value = _date_phrase(line)
            if value:
                out.append(FieldCandidate(name=name, value=value, quote=line.strip()[:200], block_ids=[b["id"]],
                                          confidence=0.6))
    return out


def _date_phrase(line: str) -> str | None:
    t = normalize(line)
    from datetime import date as _date

    ref = _date(2000, 1, 1)
    for pat in (r"\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}\b", r"\b\d{4}-\d{2}-\d{2}\b",
                r"\b\d{1,2}(?:st|nd|rd|th)?[\s\-]+[a-z]{3,9}\.?,?[\s\-]*\d{2,4}\b",
                r"\b[a-z]{3,9}\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4}\b"):
        if m := re.search(pat, t):
            if parse_explicit_date(m.group(0), ref):
                return m.group(0)
    if parse_month_year(t):
        m = re.search(r"\b[a-z]{3,9}\.?[\s\-,]+\d{4}\b", t)
        return m.group(0) if m else None
    if parse_interval(t):
        m = re.search(r"(after|in|within)?\s*\d{1,2}\s*(day|days|week|weeks|month|months|mo)\b", t)
        return m.group(0).strip() if m else None
    if "before next visit" in t or "at next visit" in t or "next visit" in t and "foot" in t:
        return "at next visit" if "at next visit" in t else "before next visit"
    return None
