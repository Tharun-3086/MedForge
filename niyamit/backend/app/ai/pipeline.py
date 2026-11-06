"""AI pipelines as explicit steps with fallbacks: AI proposes, deterministic code validates.

understand_reply:   text -> [LLM | rules fallback] -> schema + policy validation -> ReplyUnderstanding
transcribe:         audio -> ASR provider (never invents a transcript on failure)
extract_document:   file -> local blocks (text layer / OCR) -> [Sarvam Vision | LLM | rules] -> validated fields
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from dateutil.relativedelta import relativedelta
from pydantic import ValidationError

from app.ai import rules
from app.ai.contracts import (
    DATE_FIELDS,
    DOC_JSON_SCHEMA,
    REPLY_JSON_SCHEMA,
    DocExtraction,
    FieldCandidate,
    ReplyUnderstanding,
    sarvam_extract_schema,
)
from app.ai.dates import normalize, parse_explicit_date, parse_interval, parse_month_year
from app.ai.prompts import DOC_SYSTEM, REPLY_SYSTEM, doc_user_prompt, reply_user_prompt
from app.ai.providers.base import ProviderError, Transcript
from app.config import settings
from app.enums import Intent

log = logging.getLogger("niyamit.ai")

PIPELINE_VERSION = "reply-v1/intake-v1"


# ------------------------------------------------------------------ provider selection
def get_llm(name: str | None = None):
    name = (name or settings.llm_provider).lower()
    if name == "sarvam" and settings.sarvam_ready():
        from app.ai.providers.sarvam import SarvamLLM

        return SarvamLLM()
    if name == "openai" and settings.openai_ready():
        from app.ai.providers.openai_provider import OpenAILLM

        return OpenAILLM()
    return None


def get_asr():
    name = settings.asr_provider.lower()
    if name == "sarvam" and settings.sarvam_ready():
        from app.ai.providers.sarvam import SarvamASR

        return SarvamASR()
    if name == "openai" and settings.openai_ready():
        from app.ai.providers.openai_provider import OpenAIASR

        return OpenAIASR()
    return None


def get_tts():
    if settings.tts_provider.lower() == "sarvam" and settings.sarvam_ready():
        from app.ai.providers.sarvam import SarvamTTS

        return SarvamTTS()
    return None


def provider_status() -> dict[str, Any]:
    from app.ai.providers.local_docs import tesseract_available

    llm, asr, tts = get_llm(), get_asr(), get_tts()
    return {
        "llm": {"configured": settings.llm_provider, "active": f"{llm.name}:{llm.model}" if llm else "rules (offline)"},
        "asr": {"configured": settings.asr_provider, "active": f"{asr.name}:{asr.model}" if asr else "none (text only)"},
        "tts": {"configured": settings.tts_provider, "active": tts.name if tts else "none"},
        "documents": {
            "configured": settings.doc_provider,
            "vision": "sarvam-vision" if settings.doc_provider == "sarvam" and settings.sarvam_ready() else None,
            "local_ocr": "tesseract" if tesseract_available() else "not installed",
        },
        "sarvam_key_present": settings.sarvam_ready(),
        "openai_key_present": settings.openai_ready(),
    }


# ------------------------------------------------------------------ replies
@dataclass
class UnderstandingResult:
    understanding: ReplyUnderstanding
    source: str  # LLM:sarvam:sarvam-105b | RULES
    notes: list[str] = field(default_factory=list)
    latency_ms: int = 0


def understand_reply(text: str, *, today: date, preferred_language: str = "en",
                     faults: set[str] | None = None, provider: str | None = None) -> UnderstandingResult:
    faults = faults or set()
    notes: list[str] = []
    started = time.monotonic()
    result: ReplyUnderstanding | None = None
    source = "RULES"
    llm = None if (provider or "").lower() == "rules" else get_llm(provider)
    if "LLM_TIMEOUT" in faults:
        notes.append("AI provider timed out (demo fault injection); used offline rules.")
    elif llm is not None:
        try:
            raw = llm.json_completion(REPLY_SYSTEM, reply_user_prompt(text, today, preferred_language),
                                      REPLY_JSON_SCHEMA, "reply_understanding")
            result = ReplyUnderstanding.model_validate(raw)
            source = f"LLM:{llm.name}:{llm.model}"
        except ProviderError as exc:
            notes.append(f"{exc.provider} failed ({exc.code}); used offline rules.")
            log.warning("llm failed", extra={"provider": exc.provider, "error_code": exc.code})
        except ValidationError:
            notes.append(f"{llm.name} returned output outside the allowed schema; used offline rules.")
    if result is None:
        result = rules.classify(text)
    result = validate_understanding(result, text, notes)
    return UnderstandingResult(result, source, notes, int((time.monotonic() - started) * 1000))


def validate_understanding(u: ReplyUnderstanding, text: str, notes: list[str]) -> ReplyUnderstanding:
    """Server-side policy checks on any AI output before it can drive an action."""
    intents = list(u.intents)
    if u.urgent_concern_present and Intent.URGENT_CONCERN not in intents:
        intents.append(Intent.URGENT_CONCERN)
    if u.clinical_question_present and Intent.CLINICAL_QUESTION not in intents and Intent.URGENT_CONCERN not in intents:
        intents.append(Intent.CLINICAL_QUESTION)
    if u.opt_out_present and Intent.OPT_OUT not in intents:
        intents.append(Intent.OPT_OUT)
    if u.barrier_category and Intent.BARRIER_REPORTED not in intents:
        intents.append(Intent.BARRIER_REPORTED)
    if Intent.URGENT_CONCERN in intents and Intent.CLINICAL_QUESTION in intents:
        intents.remove(Intent.CLINICAL_QUESTION)  # the urgent pathway already hands it to a clinician
    if len(intents) > 1 and Intent.OTHER_OR_UNCLEAR in intents:
        intents.remove(Intent.OTHER_OR_UNCLEAR)
    if Intent.BARRIER_REPORTED in intents and u.barrier_category is None:
        u.barrier_category = "OTHER"  # type: ignore[assignment]

    conf = u.confidence
    norm_text = normalize(text)
    if u.source_text and normalize(u.source_text) not in norm_text:
        notes.append("AI quoted text that is not in the message; quote dropped and confidence lowered.")
        u.source_text = ""
        conf = min(conf, 0.5)
    if u.requested_date and not re.search(r"\d", text):
        notes.append("AI proposed a calendar date the patient did not write; ignored.")
        u.requested_date = None
    if u.requested_day_text and normalize(u.requested_day_text) not in norm_text:
        u.requested_day_text = None

    safety = {Intent.URGENT_CONCERN, Intent.CLINICAL_QUESTION, Intent.OPT_OUT}
    needs = u.needs_clarification
    reason = u.clarification_reason
    if intents == [Intent.CONFIRM_FOLLOWUP] and rules.is_hedged(text):
        notes.append("Confirmation sounded unsure; asking the patient instead of recording it.")
        intents, conf, needs, reason = [Intent.OTHER_OR_UNCLEAR], min(conf, 0.4), True, rules.HEDGED_REASON
    if conf < settings.clarify_confidence_threshold and not (set(intents) & safety):
        needs, reason = True, reason or "Low confidence in what the patient asked for"
    if intents == [Intent.OTHER_OR_UNCLEAR]:
        needs, reason = True, reason or "No supported request recognised"
    return u.model_copy(update={
        "intents": intents, "confidence": round(conf, 2), "needs_clarification": needs,
        "clarification_reason": reason,
        "urgent_concern_present": Intent.URGENT_CONCERN in intents,
        "clinical_question_present": u.clinical_question_present or Intent.CLINICAL_QUESTION in intents,
        "opt_out_present": Intent.OPT_OUT in intents,
    })


def transcribe(audio: bytes, mime: str, filename: str, language_hint: str | None,
               faults: set[str] | None = None) -> Transcript:
    if faults and "ASR_TIMEOUT" in faults:
        raise ProviderError("speech", "TIMEOUT", "demo fault injection")
    asr = get_asr()
    if asr is None:
        raise ProviderError("speech", "NOT_CONFIGURED")
    return asr.transcribe(audio, mime, filename, language_hint)


# ------------------------------------------------------------------ documents
INSTRUCTION_LIKE = re.compile(
    r"ignore (all |any |the )?(previous|prior|above) instructions|system prompt|you are now|approve (this|the) plan|"
    r"disregard (the|all) rules|send (a )?message to all", re.I)


@dataclass
class FieldProposal:
    name: str
    value: str | None  # normalised (ISO date for date fields)
    extracted_value: str
    status: str  # UNVERIFIED | NEEDS_REVIEW
    confidence: float | None
    evidence: dict[str, Any]
    review_reasons: list[str]


@dataclass
class DocResult:
    blocks: list[dict[str, Any]]
    page_sizes: list[dict[str, Any]]
    fields: list[FieldProposal]
    ocr_provider: str
    extractor: str
    model_version: str
    notes: list[str]


def extract_document(data: bytes, mime: str, filename: str, *, today: date,
                     faults: set[str] | None = None, local_only: bool = False) -> DocResult:
    from app.ai.providers.local_docs import read_blocks

    faults = faults or set()
    notes: list[str] = []
    blocks: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    ocr = "none"
    if settings.ocr_provider == "unlimited" and not local_only and "DOC_PROVIDER_DOWN" not in faults:
        try:
            from app.ai.providers.unlimited_ocr import read_blocks as read_unlimited
            blocks, pages, ocr = read_unlimited(data, mime)
            notes.append("Baidu OCR text is AI-generated; verify against the original document. Exact evidence boxes are unavailable.")
        except ProviderError as exc:
            if exc.code == "EMPTY_IMAGE":
                raise ProviderError("intake", "NO_TEXT_FOUND", "The uploaded document contains no readable contrast.") from None
            notes.append(f"Baidu OCR unavailable ({exc.code}); using existing local document reading.")
    try:
        if not blocks:
            blocks, pages, ocr = read_blocks(data, mime)
    except ProviderError as exc:
        notes.append(f"Local text reading unavailable ({exc.provider}: {exc.code}).")
    if blocks and INSTRUCTION_LIKE.search(" ".join(b["text"] for b in blocks)):
        notes.append("Document contains instruction-like text. It was treated as data only; nothing was executed.")

    candidates: list[FieldCandidate] | None = None
    extractor, model_version = "", ""
    if local_only:
        notes.append("No consent for AI processing on record; read on this server only (no external AI).")
    elif "DOC_PROVIDER_DOWN" in faults:
        notes.append("Document AI provider unavailable (demo fault injection).")
    else:
        if settings.doc_provider == "sarvam" and settings.sarvam_ready() and mime in (
                "application/pdf", "image/png", "image/jpeg"):
            try:
                from app.ai.providers.sarvam import SarvamVisionExtract

                vx = SarvamVisionExtract()
                out = vx.extract(data, mime, filename, sarvam_extract_schema())
                candidates = _from_sarvam_extract(out.get("result") or {}, blocks)
                extractor, model_version = "sarvam-vision-extract", f"{vx.model} job {out.get('job_id')}"
                if out.get("annotations"):
                    notes.append("Sarvam returned citation annotations; stored with the proposal.")
            except ProviderError as exc:
                notes.append(f"Sarvam Vision failed ({exc.code}); trying the next method.")
        if candidates is None and blocks:
            llm = get_llm()
            if llm is not None:
                try:
                    raw = llm.json_completion(DOC_SYSTEM, doc_user_prompt(blocks), DOC_JSON_SCHEMA, "doc_fields")
                    candidates = DocExtraction.model_validate(raw).fields
                    extractor, model_version = f"llm:{llm.name}", llm.model
                except (ProviderError, ValidationError) as exc:
                    code = exc.code if isinstance(exc, ProviderError) else "SCHEMA_INVALID"
                    notes.append(f"LLM extraction failed ({code}); using offline rules.")
        if candidates is None and settings.doc_provider == "openai" and mime.startswith("image/"):
            llm = get_llm("openai")
            if llm is not None:
                try:
                    raw = llm.json_completion(DOC_SYSTEM, "Extract from the attached document image.",
                                              DOC_JSON_SCHEMA, "doc_fields", images=[(data, mime)])
                    candidates = DocExtraction.model_validate(raw).fields
                    extractor, model_version = "llm:openai-vision", llm.model
                except (ProviderError, ValidationError):
                    notes.append("OpenAI vision extraction failed; using offline rules.")
    if candidates is None:
        if not blocks:
            raise ProviderError("intake", "NO_TEXT_FOUND", "No provider could read this document.")
        candidates = rules.extract_document(blocks)
        extractor, model_version = "rules", "rules-v1"
    fields = validate_fields(candidates, blocks, today)
    from app.services.health_readings import extract as extract_readings
    for name,(value,quote,block_id) in extract_readings(blocks).items():
        fields.append(FieldProposal(name,value,quote,"UNVERIFIED",None,
            {"quote":quote,"block_ids":[block_id] if block_id else []},["VERIFY_MEASUREMENT_AGAINST_ORIGINAL"]))
    return DocResult(blocks, pages, fields, ocr, extractor, model_version, notes)


def _from_sarvam_extract(result: dict[str, Any], blocks: list[dict[str, Any]]) -> list[FieldCandidate]:
    out: list[FieldCandidate] = []
    for name in ["document_type"] + DATE_FIELDS:
        raw = result.get(name)
        if isinstance(raw, dict):  # tolerate {value, citation} shaped results
            value = str(raw.get("value") or "").strip()
            quote = str(raw.get("source_text") or raw.get("citation") or "").strip()
        else:
            value = str(raw or "").strip()
            quote = str(result.get(f"{name}__source_text") or "").strip()
        if not value or value.lower() in {"null", "none", "n/a", "not found"}:
            continue
        ids = _blocks_containing(blocks, quote or value)
        out.append(FieldCandidate(name=name, value=value[:200], quote=quote[:300], block_ids=ids, confidence=None))
    return out


def _squash(s: str) -> str:
    return re.sub(r"[^0-9a-zऀ-෿]+", "", normalize(s))


def _blocks_containing(blocks: list[dict[str, Any]], text: str) -> list[str]:
    target = _squash(text)
    if not target:
        return []
    hits = [b["id"] for b in blocks if target in _squash(b["text"]) or (len(_squash(b["text"])) > 6 and _squash(b["text"]) in target)]
    return hits[:3]


def validate_fields(cands: list[FieldCandidate], blocks: list[dict[str, Any]], today: date) -> list[FieldProposal]:
    """Normalise dates, check quotes against the source, flag conflicts. Nothing is ever auto-approved."""
    by_id = {b["id"]: b for b in blocks}
    full = _squash(" ".join(b["text"] for b in blocks))
    doc_date: date | None = None
    for c in cands:
        if c.name == "document_date":
            doc_date = parse_explicit_date(c.value, today, allow_missing_year=False) or doc_date
    ref = doc_date or today

    proposals: list[FieldProposal] = []
    for c in cands:
        reasons: list[str] = []
        ids = [i for i in c.block_ids if i in by_id] or _blocks_containing(blocks, c.quote or c.value)
        quote = c.quote.strip()
        if blocks:
            if quote and _squash(quote) not in full:
                reasons.append("QUOTE_NOT_FOUND_IN_SOURCE")
            if not quote and not ids:
                reasons.append("NO_SOURCE_EVIDENCE")
        elif not quote:
            reasons.append("NO_SOURCE_EVIDENCE")
        evidence = {
            "quote": quote or None,
            "block_ids": ids,
            "page": by_id[ids[0]]["page"] if ids else None,
            "bboxes": [{"page": by_id[i]["page"], "bbox": by_id[i]["bbox"]} for i in ids if by_id[i].get("bbox")],
        }
        value: str | None = c.value.strip()
        if c.name in DATE_FIELDS:
            value, note = _normalise_date_value(c.value, ref, c.name)
            if note:
                evidence["computed"] = note
            if value is None:
                reasons.append("NO_EXACT_DATE")
            else:
                d = date.fromisoformat(value)
                if c.name != "document_date":
                    if doc_date and d < doc_date:
                        reasons.append("BEFORE_DOCUMENT_DATE")
                    if d > ref + relativedelta(years=2):
                        reasons.append("TOO_FAR_AHEAD")
        elif c.name == "document_type":
            value = c.value.strip().upper().replace(" ", "_")
            if value not in {"PRESCRIPTION", "LAB_REPORT", "DISCHARGE_SUMMARY", "REGISTER", "OTHER"}:
                value = "OTHER"
        if c.confidence is not None and c.confidence < 0.5:
            reasons.append("LOW_CONFIDENCE")
        proposals.append(FieldProposal(c.name, value, c.value, "NEEDS_REVIEW" if reasons else "UNVERIFIED",
                                       c.confidence, evidence, reasons))

    # 'before next visit' style values resolve to the next review date when there is exactly one
    reviews = {p.value for p in proposals if p.name == "next_review_date" and p.value}
    for p in proposals:
        if p.value is None and p.name in DATE_FIELDS and "next visit" in normalize(p.extracted_value) and len(reviews) == 1:
            p.value = next(iter(reviews))
            p.evidence["computed"] = "Linked to the next review visit date"
            p.review_reasons = [r for r in p.review_reasons if r != "NO_EXACT_DATE"]
            p.status = "NEEDS_REVIEW" if p.review_reasons else "UNVERIFIED"

    # Conflicting values for the same field: every candidate needs a human decision.
    seen: dict[str, set[str | None]] = {}
    for p in proposals:
        seen.setdefault(p.name, set()).add(p.value)
    for p in proposals:
        if len(seen[p.name]) > 1:
            p.review_reasons.append("CONFLICTING_VALUES")
            p.status = "NEEDS_REVIEW"
    # Deduplicate identical candidates (same field, same value), keeping the first evidence.
    unique: dict[tuple[str, str | None], FieldProposal] = {}
    for p in proposals:
        unique.setdefault((p.name, p.value), p)
    return list(unique.values())


def _normalise_date_value(raw: str, ref: date, name: str) -> tuple[str | None, str | None]:
    explicit = parse_explicit_date(raw, ref, allow_missing_year=False)
    if explicit:
        return explicit.isoformat(), None
    interval = parse_interval(raw)
    if interval and name != "document_date":
        due = ref + interval
        return due.isoformat(), f"Computed: document date {ref.isoformat()} + {raw.strip()}"
    if parse_month_year(raw):
        return None, "Only a month was written; reviewer must choose the day"
    return None, None
