"""Narrow, machine-checkable contracts for every AI output (PRD 8.2, 8.3, 7.8).

The model only ever fills these schemas. The server validates them and decides what happens.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.enums import BarrierCategory, Intent, TimeWindow


class ReplyUnderstanding(BaseModel):
    model_config = ConfigDict(extra="ignore")

    intents: list[Intent] = Field(min_length=1)
    requested_date: date | None = None
    requested_day_text: str | None = None
    requested_time_window: TimeWindow | None = None
    barrier_category: BarrierCategory | None = None
    clinical_question_present: bool = False
    urgent_concern_present: bool = False
    opt_out_present: bool = False
    source_text: str = ""
    english_gloss: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    needs_clarification: bool = False
    clarification_reason: str | None = None

    @field_validator("intents")
    @classmethod
    def unique_intents(cls, v: list[Intent]) -> list[Intent]:
        seen: list[Intent] = []
        for i in v:
            if i not in seen:
                seen.append(i)
        return seen


def _nullable(t: str) -> dict[str, Any]:
    return {"type": [t, "null"]}


REPLY_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "intents": {"type": "array", "items": {"type": "string", "enum": [i.value for i in Intent]}, "minItems": 1},
        "requested_date": {**_nullable("string"), "description": "YYYY-MM-DD only if a full date was written"},
        "requested_day_text": _nullable("string"),
        "requested_time_window": {"type": ["string", "null"], "enum": [w.value for w in TimeWindow] + [None]},
        "barrier_category": {"type": ["string", "null"], "enum": [b.value for b in BarrierCategory] + [None]},
        "clinical_question_present": {"type": "boolean"},
        "urgent_concern_present": {"type": "boolean"},
        "opt_out_present": {"type": "boolean"},
        "source_text": {"type": "string"},
        "english_gloss": _nullable("string"),
        "confidence": {"type": "number"},
        "needs_clarification": {"type": "boolean"},
        "clarification_reason": _nullable("string"),
    },
    "required": [
        "intents", "requested_date", "requested_day_text", "requested_time_window", "barrier_category",
        "clinical_question_present", "urgent_concern_present", "opt_out_present", "source_text",
        "english_gloss", "confidence", "needs_clarification", "clarification_reason",
    ],
}

# ------------------------------------------------------------------------------ documents
DOC_FIELDS: dict[str, str] = {
    "document_type": "Type of document: PRESCRIPTION, LAB_REPORT, DISCHARGE_SUMMARY, REGISTER or OTHER",
    "document_date": "Date the document was written or the sample was collected",
    "next_review_date": "Date or interval for the next review / follow-up visit (e.g. 'after 3 months')",
    "hba1c_due_date": "When the next HbA1c test is due (date, interval or 'before next visit')",
    "eye_exam_due_date": "When the next eye / retina / fundus check is due",
    "foot_exam_due_date": "When the next foot examination is due",
    "kidney_test_due_date": "When the next kidney test (creatinine, KFT, urine albumin) is due",
    "refill_due_date": "When medicines run out or the next refill / repeat prescription is due",
}
DATE_FIELDS = [f for f in DOC_FIELDS if f != "document_type"]

FIELD_TO_ITEM = {
    "next_review_date": "REVIEW_VISIT",
    "hba1c_due_date": "HBA1C_TEST",
    "eye_exam_due_date": "EYE_EXAM",
    "foot_exam_due_date": "FOOT_EXAM",
    "kidney_test_due_date": "KIDNEY_TEST",
    "refill_due_date": "MEDICINE_REFILL",
}

FIELD_LABELS = {
    "document_type": "Document type",
    "document_date": "Document date",
    "next_review_date": "Next review visit",
    "hba1c_due_date": "HbA1c test due",
    "eye_exam_due_date": "Eye check due",
    "foot_exam_due_date": "Foot check due",
    "kidney_test_due_date": "Kidney test due",
    "refill_due_date": "Medicine refill due",
}


class FieldCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Literal[
        "document_type", "document_date", "next_review_date", "hba1c_due_date", "eye_exam_due_date",
        "foot_exam_due_date", "kidney_test_due_date", "refill_due_date",
    ]
    value: str = Field(min_length=1, max_length=200)
    quote: str = ""
    block_ids: list[str] = []
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class DocExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    fields: list[FieldCandidate] = []


DOC_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "enum": list(DOC_FIELDS)},
                    "value": {"type": "string"},
                    "quote": {"type": "string"},
                    "block_ids": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                },
                "required": ["name", "value", "quote", "block_ids", "confidence"],
            },
        }
    },
    "required": ["fields"],
}


def sarvam_extract_schema() -> dict[str, Any]:
    """Flat schema for Sarvam Vision Extract: each field plus the exact words it came from."""
    props: dict[str, Any] = {}
    for name, desc in DOC_FIELDS.items():
        props[name] = {"type": "string", "description": desc + ". Copy exactly as written; empty if absent."}
        props[f"{name}__source_text"] = {
            "type": "string",
            "description": f"The exact sentence or line in the document that states the {name.replace('_', ' ')}.",
        }
    return {"type": "object", "properties": props}
