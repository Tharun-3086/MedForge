"""One review policy shared by extraction, staff confirmation and patient readings."""
from app.config import settings

VERIFICATION_REASONS = frozenset({"LOW_OCR_CONFIDENCE", "HANDWRITING_REQUIRES_REVIEW", "OCR_DISAGREEMENT",
    "UNSUPPORTED_HANDWRITING_LANGUAGE", "HANDWRITING_UNAVAILABLE", "OCR_INCOMPLETE", "OCR_FALLBACK",
    "CONFLICTING_MEASUREMENTS"})


def evidence_for(blocks: list[dict], ids: list[str]) -> tuple[dict, list[str], float | None]:
    selected = [b for b in blocks if b["id"] in ids]
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
