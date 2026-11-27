"""Optional local PaddleOCR and English TrOCR. Never infer medical instructions.

Models are loaded lazily, once per worker. Scores are routing hints, not calibrated
probabilities. Both OCR alternatives and their image coordinates stay in evidence.
"""
from __future__ import annotations

import io
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from threading import RLock

from app.ai.providers.base import ProviderError
from app.config import settings

_lock = RLock()
log = logging.getLogger("niyamit.ocr")


def _cache() -> Path:
    root = Path(settings.ocr_model_cache).resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(root / "paddle"))
    os.environ.setdefault("HF_HOME", str(root / "huggingface"))
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    return root


@lru_cache(maxsize=3)
def _paddle(language: str):
    _cache()
    from paddleocr import PaddleOCR
    models = {"en": "en_PP-OCRv5_mobile_rec", "hi": "devanagari_PP-OCRv5_mobile_rec", "te": "te_PP-OCRv5_mobile_rec"}
    cache = _cache() / "paddle" / "official_models"
    ready = all(all((cache / name / file).is_file() for file in ("inference.json", "inference.pdiparams", "inference.yml"))
                for name in ("PP-OCRv5_mobile_det", models[language]))
    if not settings.ocr_allow_model_downloads:
        # PaddleX normally downloads missing models on construction. Fail closed.
        if not ready:
            raise ProviderError("paddleocr", "MODEL_NOT_CACHED")
    directories = {"text_detection_model_dir": str(cache / "PP-OCRv5_mobile_det"),
                   "text_recognition_model_dir": str(cache / models[language])} if ready else {}
    return PaddleOCR(text_detection_model_name="PP-OCRv5_mobile_det", text_recognition_model_name=models[language],
                     use_doc_orientation_classify=False, use_doc_unwarping=False,
                     use_textline_orientation=False, device="cpu", enable_mkldnn=False, cpu_threads=2, **directories)


@lru_cache(maxsize=1)
def _trocr():
    root = _cache()
    import torch
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel
    torch.set_num_threads(1)
    args = {"cache_dir": str(root / "trocr"), "local_files_only": not settings.ocr_allow_model_downloads}
    processor = TrOCRProcessor.from_pretrained(settings.handwriting_model, **args)
    model = VisionEncoderDecoderModel.from_pretrained(settings.handwriting_model, **args).eval()
    return processor, model


def printed_lines(image, language: str) -> list[dict]:
    import numpy as np
    output = []
    with _lock:
        for prediction in _paddle(language).predict(np.asarray(image)):
            result = prediction.json.get("res", prediction.json)
            texts, scores, polygons = result["rec_texts"], result["rec_scores"], result["rec_polys"]
            if not len(texts) == len(scores) == len(polygons):
                raise ProviderError("paddleocr", "INVALID_OUTPUT")
            for text, score, polygon in zip(texts, scores, polygons):
                points = [[float(x), float(y)] for x, y in polygon]
                if not points or not str(text).strip():
                    continue
                xs, ys = zip(*points)
                output.append({"text": str(text).strip()[:2000], "ocr_conf": float(score),
                               "pixels": [min(xs), min(ys), max(xs), max(ys)], "polygon": points})
    return output


def handwritten_line(image, polygon: list[list[float]]) -> str:
    import cv2
    import numpy as np
    import torch
    from PIL import Image
    points = np.asarray(polygon, dtype="float32")
    if points.shape != (4, 2):
        raise ProviderError("trocr", "INVALID_CROP")
    width = int(max(np.linalg.norm(points[1]-points[0]), np.linalg.norm(points[2]-points[3])))
    height = int(max(np.linalg.norm(points[3]-points[0]), np.linalg.norm(points[2]-points[1])))
    if min(width, height) < 2:
        raise ProviderError("trocr", "INVALID_CROP")
    transform = cv2.getPerspectiveTransform(points, np.array([[0, 0], [width-1, 0], [width-1, height-1], [0, height-1]], dtype="float32"))
    crop = Image.fromarray(cv2.warpPerspective(np.asarray(image), transform, (width, height)))
    with _lock, torch.inference_mode():
        processor, model = _trocr()
        pixels = processor(images=crop, return_tensors="pt").pixel_values
        generated = model.generate(pixels, max_new_tokens=128, num_beams=1)
        if generated.shape[-1] >= 128:
            raise ProviderError("trocr", "TRUNCATED_OUTPUT")
        return processor.batch_decode(generated, skip_special_tokens=True)[0].strip()[:2000]


def join_rows(blocks: list[dict]) -> list[dict]:
    """Group by baseline before ordering cells left-to-right.

    OCR boxes have slightly different tops: a unit can arrive before the
    label to its left. Require pairwise alignment so tall boxes cannot bridge
    neighbouring rows, and keep overlapping alternatives separate.
    """
    rows = []
    def aligned(a, b):
        x, y = a["bbox"], b["bbox"]
        height = min(x[3] - x[1], y[3] - y[1])
        overlap = min(x[3], y[3]) - max(x[1], y[1])
        return (a.get("page") == b.get("page") and height > 0
                and (x[2] <= y[0] or y[2] <= x[0])
                and overlap >= .65 * height
                and abs((x[1] + x[3]) - (y[1] + y[3])) <= height)

    for block in sorted(blocks, key=lambda b: (b.get("page", 1),
                                              (b["bbox"][1] + b["bbox"][3]) / 2,
                                              b["bbox"][0])):
        matches = [r for r in rows if all(aligned(block, cell) for cell in r)]
        # Ambiguous geometry must not attach a unit/value to a guessed row.
        row = matches[0] if len(matches) == 1 else None
        if row is None: rows.append([block])
        else: row.append(block)
    result = []
    for row in rows:
        row.sort(key=lambda b: b["bbox"][0])
        texts = [b["text"] for b in row]
        combined = dict(row[0], text=" ".join(texts),
                        bbox=[min(b["bbox"][0] for b in row), min(b["bbox"][1] for b in row),
                              max(b["bbox"][2] for b in row), max(b["bbox"][3] for b in row)],
                        ocr_conf=min(b["ocr_conf"] for b in row),
                        review_reasons=sorted({reason for b in row for reason in b.get("review_reasons", [])}),
                        source_block_ids=[b["id"] for b in row], alternatives=[])
        for i, block in enumerate(row):
            for alternative in block.get("alternatives", []):
                combined["alternatives"].append({**alternative, "text": " ".join(texts[:i]+[alternative["text"]]+texts[i+1:])})
        result.append(combined)
    return result


def read_image(data: bytes, *, page: int, style: str = "auto", language: str = "en", line_budget: int | None = None):
    from PIL import Image, ImageOps
    from app.ai.providers.local_docs import _ocr_image
    with Image.open(io.BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    width, height = image.size
    if width * height > settings.max_image_pixels:
        raise ProviderError("hybrid", "IMAGE_LIMIT")
    try:
        lines = printed_lines(image, language)
        if not lines:
            raise ProviderError("paddleocr", "NO_LINES")
    except Exception as exc:
        code = exc.code if isinstance(exc, ProviderError) else type(exc).__name__
        log.warning("PaddleOCR unavailable; falling back to Tesseract (%s)", code)
        # Missing optional dependency/model or engine failure never stops printed OCR.
        blocks, pages = _ocr_image(data, page)
        for block in blocks:
            block["review_reasons"] = ["OCR_FALLBACK"]
            if style in ("handwritten", "mixed"):
                block["review_reasons"].append("HANDWRITING_REQUIRES_REVIEW")
        return blocks, [dict(p, review_reasons=["OCR_FALLBACK"], engine_error=code) for p in pages]
    blocks, attempts, page_reasons = [], 0, set()
    for index, line in enumerate(lines, 1):
        text, score = line["text"], line["ocr_conf"]
        if not 0 <= score <= 1:
            score = 0.0
        reasons = set()
        if score < settings.ocr_review_threshold:
            reasons.add("LOW_OCR_CONFIDENCE")
        block = {"id": f"p{page}-h{index}", "page": page, "text": text,
                 "engine": "paddleocr", "model": "PP-OCRv5-mobile", "language": language,
                 "ocr_conf": score, "bbox": [max(0, min(1, v / (width if i%2 == 0 else height))) for i, v in enumerate(line["pixels"])]}
        needs_handwriting = style in ("handwritten", "mixed") or (style == "auto" and score < settings.ocr_review_threshold)
        if needs_handwriting:
            reasons.add("HANDWRITING_REQUIRES_REVIEW")
            if language != "en":
                reasons.add("UNSUPPORTED_HANDWRITING_LANGUAGE")
            elif attempts >= (settings.ocr_max_handwritten_lines if line_budget is None else line_budget):
                reasons.add("OCR_INCOMPLETE")
            else:
                attempts += 1
                try:
                    alternative = handwritten_line(image, line["polygon"])
                    if not alternative:
                        raise ProviderError("trocr", "EMPTY_RESPONSE")
                    block["alternatives"] = [{"text": alternative, "engine": "trocr", "model": settings.handwriting_model}]
                    same = re.sub(r"\s+", "", text).casefold() == re.sub(r"\s+", "", alternative).casefold()
                    if not same:
                        reasons.add("OCR_DISAGREEMENT")
                    # TrOCR is only a candidate, never an automatic replacement.
                except Exception as exc:
                    code = exc.code if isinstance(exc, ProviderError) else type(exc).__name__
                    log.warning("Handwriting recognition unavailable (%s)", code)
                    reasons.add("HANDWRITING_UNAVAILABLE")
        block["review_reasons"] = sorted(reasons)
        page_reasons.update(reasons)
        blocks.append(block)
    if style in ("printed", "auto"):
        blocks = join_rows(blocks)
    return blocks, [{"page": page, "width": width, "height": height, "review_reasons": sorted(page_reasons), "handwriting_attempts": attempts}]


def read_blocks(data: bytes, mime: str, *, style: str = "auto", language: str = "en"):
    from app.ai.providers.local_docs import read_blocks as local_read
    if style not in ("auto", "printed", "handwritten", "mixed") or language not in ("en", "hi", "te"):
        raise ProviderError("hybrid", "INVALID_OPTIONS")
    if mime == "application/pdf" and style in ("auto", "printed"):
        from app.ai.providers.local_docs import _pdf_text_blocks
        native, metadata = _pdf_text_blocks(data)
        if len(metadata) > settings.max_pdf_pages:
            raise ProviderError("hybrid", "PAGE_LIMIT")
        if metadata and all(p.get("text_only") and sum(len(b["text"]) for b in native if b["page"] == p["page"]) >= 40
                            for p in metadata):
            return [dict(b, engine="pdf-text-layer") for b in native], metadata, "pdf-text-layer"
    pages_meta = {}
    remaining = settings.ocr_max_handwritten_lines
    def reader(png, *, page):
        nonlocal remaining
        blocks, pages = read_image(png, page=page, style=style, language=language, line_budget=remaining)
        remaining -= pages[0].get("handwriting_attempts", 0)
        pages_meta[page] = pages[0]
        return blocks, pages
    blocks, pages, engine = local_read(data, mime, image_reader=reader, scan_all_pages=True)
    return blocks, [dict(p, **{k: v for k, v in pages_meta.get(p["page"], {}).items() if k not in ("width", "height", "page")}) for p in pages], engine
