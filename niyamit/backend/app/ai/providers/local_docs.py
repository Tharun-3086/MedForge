"""Local, key-free document reading: PDF text layers, Tesseract OCR with word boxes, spreadsheets.

Produces 'blocks' (one per text line or spreadsheet row) with page numbers and normalised bounding
boxes [x0, y0, x1, y1] in 0..1, so every extracted field can point to where it came from.
"""
from __future__ import annotations

import csv
import io
import shutil
from typing import Any

from app.ai.providers.base import ProviderError


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def read_blocks(data: bytes, mime: str, *, image_reader=None, scan_all_pages: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """Returns (blocks, page_sizes, method)."""
    if mime == "application/pdf":
        blocks, pages = _pdf_text_blocks(data)
        from app.config import settings
        if len(pages) > settings.max_pdf_pages:
            raise ProviderError("local", "PAGE_LIMIT")
        all_blocks: list[dict[str, Any]] = []
        scanned = False
        for idx in range(1, len(pages) + 1):
            text = [dict(b, engine="pdf-text-layer") for b in blocks if b["page"] == idx]
            if not scan_all_pages and sum(len(b["text"]) for b in text) >= 40:
                all_blocks += text
                continue
            png = render_pdf_page(data, idx)
            try:
                b, _ = (image_reader or _ocr_image)(png, page=idx)
            except ProviderError:
                if not text:
                    raise
                b = [dict(x, review_reasons=["OCR_INCOMPLETE"]) for x in text]
                text = []
            scanned = True
            all_blocks += merge_blocks(text, b)
        for i, block in enumerate(all_blocks):
            block["id"] = f"p{block['page']}-l{i+1}"
        return all_blocks, pages, "hybrid" if image_reader else "pdf-text+tesseract" if scanned and blocks else "tesseract" if scanned else "pdf-text-layer"
    if mime.startswith("image/"):
        blocks, pages = (image_reader or _ocr_image)(data, page=1)
        return blocks, pages, "hybrid" if image_reader else "tesseract"
    if mime == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        return _xlsx_blocks(data), [{"page": 1, "width": 0, "height": 0}], "spreadsheet"
    if mime == "text/csv":
        return _csv_blocks(data), [{"page": 1, "width": 0, "height": 0}], "spreadsheet"
    raise ProviderError("local", "UNSUPPORTED_TYPE")


def _pdf_text_blocks(data: bytes) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    import pdfplumber

    blocks: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            w, h = float(page.width), float(page.height)
            pages.append({"page": pno, "width": w, "height": h})
            words = page.extract_words(keep_blank_chars=False, use_text_flow=True)
            lines: list[list[dict[str, Any]]] = []
            for word in sorted(words, key=lambda x: (round(x["top"]), x["x0"])):
                if lines and abs(lines[-1][0]["top"] - word["top"]) < 3:
                    lines[-1].append(word)
                else:
                    lines.append([word])
            for lno, line in enumerate(lines, start=1):
                line.sort(key=lambda x: x["x0"])
                text = " ".join(x["text"] for x in line)
                bbox = [min(x["x0"] for x in line) / w, min(x["top"] for x in line) / h,
                        max(x["x1"] for x in line) / w, max(x["bottom"] for x in line) / h]
                blocks.append({"id": f"p{pno}-l{lno}", "page": pno, "text": text, "bbox": [round(v, 4) for v in bbox]})
    return blocks, pages


def _ocr_image(data: bytes, page: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not tesseract_available():
        raise ProviderError("tesseract", "NOT_INSTALLED")
    import pytesseract
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(data)) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        w, h = im.size
        if max(w, h) < 1400:  # upscale small photos for better OCR
            scale = 1400 / max(w, h)
            im = im.resize((int(w * scale), int(h * scale)))
        sw, sh = im.size
        from app.config import settings
        try:
            d = pytesseract.image_to_data(im, output_type=pytesseract.Output.DICT, config="--psm 4", timeout=settings.ocr_tesseract_timeout_seconds)
        except (RuntimeError, pytesseract.TesseractError) as exc:
            raise ProviderError("tesseract", "OCR_FAILED") from exc
    lines: dict[tuple[int, int, int], list[int]] = {}
    for i, word in enumerate(d["text"]):
        if word.strip() and float(d["conf"][i]) >= 0:
            lines.setdefault((d["block_num"][i], d["par_num"][i], d["line_num"][i]), []).append(i)
    blocks: list[dict[str, Any]] = []
    ordered = sorted(lines.values(), key=lambda idx: (min(d["top"][i] for i in idx), min(d["left"][i] for i in idx)))
    for lno, idx in enumerate(ordered, start=1):
        text = " ".join(d["text"][i] for i in idx)
        x0 = min(d["left"][i] for i in idx) / sw
        y0 = min(d["top"][i] for i in idx) / sh
        x1 = max(d["left"][i] + d["width"][i] for i in idx) / sw
        y1 = max(d["top"][i] + d["height"][i] for i in idx) / sh
        # A weak digit must not disappear behind a high average line score.
        conf = min(float(d["conf"][i]) for i in idx) / 100
        blocks.append({"id": f"p{page}-l{lno}", "page": page, "text": text,
                       "bbox": [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)], "ocr_conf": round(conf, 2), "engine": "tesseract"})
    return blocks, [{"page": page, "width": w, "height": h}]


def merge_blocks(text_blocks: list[dict], ocr_blocks: list[dict]) -> list[dict]:
    """Keep native PDF text and non-overlapping scan regions. Surface disagreements."""
    import re
    result = list(text_blocks)
    squash = lambda s: re.sub(r"\s+", "", s).casefold()
    for block in ocr_blocks:
        box = block.get("bbox")
        match = None
        for native in text_blocks:
            other = native.get("bbox")
            if not box or not other:
                continue
            intersection = max(0, min(box[2], other[2])-max(box[0], other[0])) * max(0, min(box[3], other[3])-max(box[1], other[1]))
            area = min((box[2]-box[0])*(box[3]-box[1]), (other[2]-other[0])*(other[3]-other[1]))
            if area > 0 and intersection / area >= 0.7:
                match = native
                break
        if match and squash(block["text"]) == squash(match["text"]):
            continue
        if match:
            for item in (match, block):
                item["review_reasons"] = sorted(set(item.get("review_reasons", [])) | {"OCR_DISAGREEMENT"})
        result.append(block)
    return sorted(result, key=lambda b: (b.get("page", 1), (b.get("bbox") or [0, 0])[1], (b.get("bbox") or [0])[0]))


def render_pdf_page(data: bytes, page: int, scale: float = 2.0) -> bytes:
    import pypdfium2 as pdfium
    from app.config import settings
    with pdfium.PdfDocument(data) as pdf:
        source = pdf[page-1]
        w, h = source.get_size()
        scale = min(scale, (settings.max_image_pixels / max(1, w*h)) ** 0.5)
        bitmap = source.render(scale=scale)
        try:
            image = bitmap.to_pil()
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            return buf.getvalue()
        finally:
            bitmap.close()
            source.close()


def _xlsx_blocks(data: bytes) -> list[dict[str, Any]]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    blocks: list[dict[str, Any]] = []
    for ws in wb.worksheets[:3]:
        rows = list(ws.iter_rows(values_only=True, max_row=500))
        if not rows:
            continue
        header = [str(c).strip() if c is not None else "" for c in rows[0]]
        for rno, row in enumerate(rows[1:], start=2):
            cells = [f"{header[i] or f'Col{i+1}'}: {v}" for i, v in enumerate(row) if v not in (None, "")]
            if cells:
                blocks.append({"id": f"{ws.title}!R{rno}", "page": 1, "text": " | ".join(cells), "bbox": None})
    return blocks


def _csv_blocks(data: bytes) -> list[dict[str, Any]]:
    reader = csv.reader(io.StringIO(data.decode("utf-8", errors="replace")))
    rows = list(reader)[:500]
    if not rows:
        return []
    header = rows[0]
    out = []
    for rno, row in enumerate(rows[1:], start=2):
        cells = [f"{header[i] if i < len(header) else f'Col{i+1}'}: {v}" for i, v in enumerate(row) if v]
        if cells:
            out.append({"id": f"CSV!R{rno}", "page": 1, "text": " | ".join(cells), "bbox": None})
    return out


def render_pdf_pages(data: bytes, max_pages: int = 10, scale: float = 2.0) -> list[bytes]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    out = []
    for i in range(min(len(pdf), max_pages)):
        bitmap = pdf[i].render(scale=scale)
        img = bitmap.to_pil()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        out.append(buf.getvalue())
    return out
