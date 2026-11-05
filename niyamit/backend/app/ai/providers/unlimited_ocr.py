"""Optional Baidu OCR via a privately hosted OpenAI-compatible vLLM server.

Text is untrusted source evidence, never a verified clinical value. The model's
grounding coordinates are not promoted to evidence boxes without validation.
"""
from __future__ import annotations

import base64
import io
import re
import httpx
from PIL import Image, ImageOps, ImageStat
from app.config import settings
from app.ai.providers.base import ProviderError, request_with_retry


def _client() -> httpx.Client:
    base = settings.unlimited_ocr_base_url.rstrip('/')
    if settings.unlimited_ocr_runtime == 'llamacpp':
        base = base.removesuffix('/v1')
    return httpx.Client(base_url=base + '/',
                        timeout=settings.unlimited_ocr_timeout_seconds, trust_env=False)


def parse_text(text: str, *, strict: bool = False) -> str:
    """Remove layout markup, never silently discard an invented prose prefix."""
    if len(text) > 100000:
        raise ProviderError('unlimited-ocr', 'OUTPUT_TOO_LARGE')
    text = text.replace('<｜end▁of▁sentence｜>', '').strip()
    if strict and text and not text.startswith('<|det|>'):
        raise ProviderError('unlimited-ocr', 'UNSTRUCTURED_OUTPUT')
    if strict and text and (not re.match(r'<\|det\|>[^\n]*?<\|/det\|>', text)
                           or text.count('<|det|>') != text.count('<|/det|>')):
        raise ProviderError('unlimited-ocr', 'INVALID_LAYOUT')
    text = re.sub(r'<\|det\|>.*?<\|/det\|>', '', text, flags=re.S)
    text = re.sub(r'<\|[^|]+\|>', '', text).strip()
    if not text:
        raise ProviderError('unlimited-ocr', 'EMPTY_RESPONSE')
    return text


def read_blocks(data: bytes, mime: str) -> tuple[list[dict], list[dict], str]:
    if mime == 'application/pdf':
        from app.ai.providers.local_docs import render_pdf_pages
        from pypdf import PdfReader
        try:
            if len(PdfReader(io.BytesIO(data)).pages) > 10:
                raise ProviderError('unlimited-ocr', 'PAGE_LIMIT')
            images = render_pdf_pages(data, max_pages=10)
        except ProviderError:
            raise
        except Exception:
            raise ProviderError('unlimited-ocr', 'INVALID_DOCUMENT') from None
    elif mime in ('image/png', 'image/jpeg'):
        images = [data]
    else:
        raise ProviderError('unlimited-ocr', 'UNSUPPORTED_TYPE')
    blocks, pages = [], []
    with _client() as client:
        for page, image in enumerate(images, start=1):
            try:
                with Image.open(io.BytesIO(image)) as im:
                    im = ImageOps.exif_transpose(im).convert('RGB')
                    width, height = im.size
                    if ImageStat.Stat(im.convert('L')).var[0] < 0.5:
                        pages.append({'page': page, 'width': width, 'height': height})
                        continue
                    im.thumbnail((2048, 2048))
                    buf = io.BytesIO()
                    im.save(buf, format='PNG')
            except ProviderError:
                raise
            except Exception:
                raise ProviderError('unlimited-ocr', 'INVALID_IMAGE') from None
            payload = {
                'model': settings.unlimited_ocr_model,
                'messages': [{'role': 'user', 'content': [
                    {'type': 'text', 'text': '<image>document parsing.'},
                    {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()}}
                ]}],
                'temperature': 0, 'max_tokens': 8192, 'skip_special_tokens': False,
                'vllm_xargs': {'ngram_size': 35, 'window_size': 128},
            }
            native = settings.unlimited_ocr_runtime == 'llamacpp'
            if native:
                # Native endpoint preserves the exact reference prompt; legacy
                # chat formatting inserts a newline after the image marker.
                payload = {'prompt': {'prompt_string': '<image>document parsing.',
                    'multimodal_data': [base64.b64encode(buf.getvalue()).decode()]},
                    'temperature': 0, 'n_predict': 2048, 'repeat_penalty': 1.0,
                    'dry_multiplier': 0, 'cache_prompt': False,
                    # Constrain only the output format, never clinical content.
                    # Reject blank input before asking the model for layout.
                    'grammar': 'root ::= "<|det|>" .*'}
            response = request_with_retry(client, 'POST', 'completion' if native else 'chat/completions', 'unlimited-ocr', attempts=1, json=payload)
            try:
                if native:
                    result = response.json()
                    if not isinstance(result, dict):
                        raise ValueError()
                    if result.get('stop_type') != 'eos' or result.get('truncated'):
                        raise ProviderError('unlimited-ocr', 'TRUNCATED_OUTPUT')
                    text = result['content']
                else:
                    choice = response.json()['choices'][0]
                    if choice.get('finish_reason') == 'length':
                        raise ProviderError('unlimited-ocr', 'TRUNCATED_OUTPUT')
                    text = choice['message']['content']
                if not isinstance(text, str):
                    raise ValueError()
            except (ValueError, KeyError, IndexError, TypeError):
                raise ProviderError('unlimited-ocr', 'INVALID_RESPONSE') from None
            text = parse_text(text, strict=native)
            pages.append({'page': page, 'width': width, 'height': height})
            for line, value in enumerate(text.splitlines(), start=1):
                if value.strip():
                    blocks.append({'id': f'p{page}-u{line}', 'page': page, 'text': value.strip(), 'bbox': None})
    if not blocks:
        raise ProviderError('unlimited-ocr', 'EMPTY_IMAGE')
    return blocks, pages, 'baidu-unlimited-ocr-q4' if settings.unlimited_ocr_runtime == 'llamacpp' else 'baidu-unlimited-ocr'
