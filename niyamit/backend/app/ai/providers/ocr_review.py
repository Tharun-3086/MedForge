"""One review policy shared by extraction, staff confirmation and patient readings."""
from app.config import settings

VERIFICATION_REASONS = frozenset({"LOW_OCR_CONFIDENCE", "HANDWRITING_REQUIRES_REVIEW", "OCR_DISAGREEMENT",
    "UNSUPPORTED_HANDWRITING_LANGUAGE", "HANDWRITING_UNAVAILABLE", "OCR_INCOMPLETE", "OCR_FALLBACK",
    "CONFLICTING_MEASUREMENTS", "UNSUPPORTED_MEASUREMENT_UNIT", "AI_MEASUREMENT_REQUIRES_REVIEW",
    "MEDICAL_SOURCE_NOT_GROUNDED", "MEDICAL_VALUE_UNIT_NOT_GROUNDED", "POSSIBLE_REFERENCE_VALUE",
    "REFERENCE_RANGE_NOT_GROUNDED", "MEASUREMENT_DATE_NOT_GROUNDED", "FUTURE_MEASUREMENT_DATE", "UNSUPPORTED_MEDICAL_PARAMETER"})


def evidence_for(blocks: list[dict], ids: list[str]) -> tuple[dict, list[str], float | None]:
    selected = [b for b in blocks if b["id"] in ids]
    source_ids = {i for b in selected if b.get("reconstruction") for i in b.get("source_block_ids", [])}
    selected += [b for b in blocks if b["id"] in source_ids and b not in selected]
    ids = list(dict.fromkeys(ids + [b["id"] for b in selected]))
    reasons = set()
    scores = []
    for block in selected:
        reasons.update(block.get("review_reasons", []))
        if block.get("ocr_conf") is not None:
            scores.append(float(block["ocr_conf"]))
    score = min(scores) if scores else None
    if score is not None and score < settings.ocr_review_threshold:
        reasons.add("LOW_OCR_CONFIDENCE")
    return {"block_ids": ids, "page": selected[0]["page"] if selected else None,
            "bboxes": [{"page": b["page"], "bbox": b["bbox"]} for b in selected if b.get("bbox")],
            "engines": sorted({b.get("engine", "unknown") for b in selected}),
            "alternatives": [a for b in selected for a in b.get("alternatives", [])]}, sorted(reasons), score
