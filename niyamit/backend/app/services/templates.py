"""Approved message templates. Only APPROVED templates can be sent (PRD 10.5).

Wording below is DRAFT copy for the demo, seeded as approved so the demo runs. The clinical lead must
review it (especially CLINICAL_ACK and URGENT_ESCALATION) before any real patient sees it.
Reminder texts are deliberately minimal so a lock screen does not reveal health details (FR-32).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MessageTemplate

TEMPLATES: dict[str, dict[str, str]] = {
    "REMINDER_PRE_DUE": {
        "en": "Namaste {first_name}, you have a follow-up at {clinic} on {due_date}. Open to confirm or change: {link}",
        "hi": "नमस्ते {first_name}, {clinic} में आपका फॉलो-अप {due_date} को है। पुष्टि करने या तारीख बदलने के लिए खोलें: {link}",
        "te": "నమస్తే {first_name}, {clinic}లో మీ ఫాలో-అప్ {due_date}న ఉంది. నిర్ధారించడానికి లేదా తేదీ మార్చడానికి తెరవండి: {link}",
    },
    "REMINDER_DUE": {
        "en": "Namaste {first_name}, your follow-up at {clinic} is due today. Open to confirm or change: {link}",
        "hi": "नमस्ते {first_name}, {clinic} में आपका फॉलो-अप आज है। पुष्टि करें या तारीख बदलें: {link}",
        "te": "నమస్తే {first_name}, {clinic}లో మీ ఫాలో-అప్ ఈరోజు ఉంది. నిర్ధారించండి లేదా తేదీ మార్చండి: {link}",
    },
    "REMINDER_OVERDUE": {
        "en": "Namaste {first_name}, your follow-up at {clinic} was due on {due_date}. Open to pick a new time or ask for a call: {link}",
        "hi": "नमस्ते {first_name}, {clinic} में आपका फॉलो-अप {due_date} को था। नया समय चुनने या कॉल के लिए खोलें: {link}",
        "te": "నమస్తే {first_name}, {clinic}లో మీ ఫాలో-అప్ {due_date}న ఉండేది. కొత్త సమయం ఎంచుకోవడానికి లేదా కాల్ కోసం తెరవండి: {link}",
    },
    "CLINICAL_ACK": {
        "en": "We have passed your question to the clinic nurse, who will contact you. The clinic does not give medicine or treatment advice by message. If you feel unwell now, call {clinic_phone}.",
        "hi": "आपका सवाल क्लिनिक की नर्स को भेज दिया गया है, वे आपसे संपर्क करेंगी। क्लिनिक मैसेज पर दवा या इलाज की सलाह नहीं देता। अभी तबीयत ठीक न हो तो {clinic_phone} पर कॉल करें।",
        "te": "మీ ప్రశ్నను క్లినిక్ నర్సుకు పంపాము, వారు మిమ్మల్ని సంప్రదిస్తారు. క్లినిక్ మెసేజ్ ద్వారా మందులు లేదా చికిత్స సలహా ఇవ్వదు. ఇప్పుడు ఆరోగ్యం బాగోలేకపోతే {clinic_phone}కు కాల్ చేయండి.",
    },
    "URGENT_ESCALATION": {
        "en": "If this is an emergency, call 108 or 112 now or go to the nearest hospital. We have alerted the clinic team.",
        "hi": "अगर यह आपातकाल है, तो अभी 108 या 112 पर कॉल करें या नज़दीकी अस्पताल जाएँ। हमने क्लिनिक टीम को सूचित कर दिया है।",
        "te": "ఇది అత్యవసరమైతే, వెంటనే 108 లేదా 112కు కాల్ చేయండి లేదా దగ్గరలోని ఆసుపత్రికి వెళ్లండి. క్లినిక్ బృందానికి సమాచారం ఇచ్చాము.",
    },
    "CALLBACK_ACK": {
        "en": "Thank you. The clinic team will call you back.",
        "hi": "धन्यवाद। क्लिनिक टीम आपको कॉल करेगी।",
        "te": "ధన్యవాదాలు. క్లినిక్ బృందం మీకు కాల్ చేస్తుంది.",
    },
    "BARRIER_ACK": {
        "en": "Thank you for telling us. A clinic team member will contact you about the next step.",
        "hi": "बताने के लिए धन्यवाद। क्लिनिक टीम का कोई सदस्य आगे के कदम के लिए आपसे संपर्क करेगा।",
        "te": "చెప్పినందుకు ధన్యవాదాలు. తదుపరి దశ గురించి క్లినిక్ బృందం నుండి ఒకరు మిమ్మల్ని సంప్రదిస్తారు.",
    },
    "CONFIRM_ACK": {
        "en": "Thank you for confirming your follow-up on {due_date}.",
        "hi": "{due_date} के फॉलो-अप की पुष्टि के लिए धन्यवाद।",
        "te": "{due_date} ఫాలో-అప్‌ను నిర్ధారించినందుకు ధన్యవాదాలు.",
    },
    "RESCHEDULE_OPTIONS": {
        "en": "We received your request for a new time. Open to choose an available slot: {link}",
        "hi": "नए समय का आपका अनुरोध मिल गया है। उपलब्ध स्लॉट चुनने के लिए खोलें: {link}",
        "te": "కొత్త సమయం కోసం మీ అభ్యర్థన అందింది. అందుబాటులో ఉన్న స్లాట్ ఎంచుకోవడానికి తెరవండి: {link}",
    },
    "BOOKING_CONFIRMED": {
        "en": "Booked: {slot_time} at {clinic}. Reference {ref}.",
        "hi": "बुक हो गया: {slot_time}, {clinic}। संदर्भ {ref}।",
        "te": "బుక్ అయింది: {slot_time}, {clinic}. రిఫరెన్స్ {ref}.",
    },
    "BOOKING_NOT_DONE": {
        "en": "We could not book that time. The clinic will call you to fix a time.",
        "hi": "हम यह समय बुक नहीं कर सके। समय तय करने के लिए क्लिनिक आपको कॉल करेगा।",
        "te": "ఆ సమయాన్ని బుక్ చేయలేకపోయాము. సమయం నిర్ణయించడానికి క్లినిక్ మీకు కాల్ చేస్తుంది.",
    },
    "CLARIFY": {
        "en": "Sorry, we did not understand. Reply 1 to confirm, 2 to change the date, 3 for a call back, or open: {link}",
        "hi": "माफ़ कीजिए, हम समझ नहीं पाए। पुष्टि के लिए 1, तारीख बदलने के लिए 2, कॉल के लिए 3 भेजें, या खोलें: {link}",
        "te": "క్షమించండి, మాకు అర్థం కాలేదు. నిర్ధారించడానికి 1, తేదీ మార్చడానికి 2, కాల్ కోసం 3 పంపండి, లేదా తెరవండి: {link}",
    },
    "VOICE_FAILED": {
        "en": "We could not understand the voice note. Please type your message, or reply 1 to confirm, 2 to change the date, 3 for a call back.",
        "hi": "हम वॉइस मैसेज समझ नहीं पाए। कृपया लिखकर भेजें, या पुष्टि के लिए 1, तारीख बदलने के लिए 2, कॉल के लिए 3 भेजें।",
        "te": "వాయిస్ మెసేజ్ అర్థం కాలేదు. దయచేసి టైప్ చేసి పంపండి, లేదా నిర్ధారించడానికి 1, తేదీ మార్చడానికి 2, కాల్ కోసం 3 పంపండి.",
    },
    "OPT_OUT_CONFIRMED": {
        "en": "You will not get reminders from {clinic} any more. To start again, reply START or open: {link}",
        "hi": "अब आपको {clinic} से रिमाइंडर नहीं मिलेंगे। फिर से शुरू करने के लिए START भेजें या खोलें: {link}",
        "te": "ఇకపై మీకు {clinic} నుండి రిమైండర్లు రావు. మళ్లీ మొదలుపెట్టడానికి START పంపండి లేదా తెరవండి: {link}",
    },
    "REPORT_UPLOAD_LINK": {
        "en": "You can upload your report here: {link}",
        "hi": "आप अपनी रिपोर्ट यहाँ अपलोड कर सकते हैं: {link}",
        "te": "మీ రిపోర్ట్‌ను ఇక్కడ అప్‌లోడ్ చేయవచ్చు: {link}",
    },
    "CAREGIVER_INVITE": {
        "en": "{patient_first_name} has shared limited follow-up access with you for {clinic}: {link}",
        "hi": "{patient_first_name} ने {clinic} के फॉलो-अप के लिए आपको सीमित पहुँच दी है: {link}",
        "te": "{patient_first_name} {clinic} ఫాలో-అప్‌ల కోసం మీకు పరిమిత యాక్సెస్ ఇచ్చారు: {link}",
    },
}
DEMO_APPROVAL = "Demo approval (synthetic) — pending clinical lead review"


class _Safe(dict):
    def __missing__(self, key: str) -> str:
        return ""


class TemplateNotApproved(Exception):
    pass


def approved_template(db: Session, clinic_id: uuid.UUID, key: str, language: str) -> MessageTemplate:
    for lang in (language, "en"):
        tpl = db.scalar(select(MessageTemplate).where(
            MessageTemplate.clinic_id == clinic_id, MessageTemplate.key == key, MessageTemplate.language == lang,
            MessageTemplate.status == "APPROVED").order_by(MessageTemplate.version.desc()))
        if tpl:
            return tpl
    raise TemplateNotApproved(f"No approved template {key}")


def _value(v: object, language: str) -> str:
    """Dates and times are written in the message's language (pass clinic-local datetimes)."""
    from app.services.common import local_day_label, local_slot_label

    if isinstance(v, datetime):
        return local_slot_label(v, language)
    if isinstance(v, date):
        return local_day_label(v, language)
    return str(v)


def render(db: Session, clinic_id: uuid.UUID, key: str, language: str, **values: object) -> tuple[str, MessageTemplate]:
    tpl = approved_template(db, clinic_id, key, language)
    return tpl.body.format_map(_Safe({k: _value(v, tpl.language) for k, v in values.items()})), tpl


def seed_templates(db: Session, clinic_id: uuid.UUID) -> None:
    from app.db import utcnow

    for key, langs in TEMPLATES.items():
        for lang, body in langs.items():
            db.add(MessageTemplate(clinic_id=clinic_id, key=key, language=lang, version=1, body=body,
                                   status="APPROVED", approved_by_label=DEMO_APPROVAL, approved_at=utcnow()))
