import io
from datetime import date
import httpx
import pytest
from PIL import Image, ImageDraw
from app.ai import pipeline
from app.ai.providers import unlimited_ocr
from app.ai.providers.base import ProviderError
from app.config import settings


def png():
    b = io.BytesIO()
    im = Image.new('RGB', (100, 100), 'white')
    ImageDraw.Draw(im).text((10,10),'TEST',fill='black')
    im.save(b, format='PNG')
    return b.getvalue()


def test_unlimited_text_has_no_invented_evidence_boxes(monkeypatch):
    monkeypatch.setattr(settings, 'unlimited_ocr_runtime', 'vllm')
    def handler(request):
        import json
        body = json.loads(request.content)
        assert body['skip_special_tokens'] is False
        assert body['messages'][0]['content'][0]['text'] == '<image>document parsing.'
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': '<|ref|>Review after 7 days<|/ref|><|det|>[[1,2,3,4]]<|/det|>'}}]})
    monkeypatch.setattr(unlimited_ocr, '_client', lambda: httpx.Client(base_url='http://ocr/v1/', transport=httpx.MockTransport(handler)))
    blocks, pages, provider = unlimited_ocr.read_blocks(png(), 'image/png')
    assert blocks[0]['text'] == 'Review after 7 days' and blocks[0]['bbox'] is None
    assert pages[0]['width'] == 100 and provider == 'baidu-unlimited-ocr'


def test_quantized_runtime_request(monkeypatch):
    import json
    monkeypatch.setattr(settings, 'unlimited_ocr_runtime', 'llamacpp')
    def handler(request):
        body = json.loads(request.content)
        assert request.url.path == '/completion'
        assert body['prompt']['prompt_string'] == '<image>document parsing.'
        assert len(body['prompt']['multimodal_data']) == 1
        assert body['n_predict'] == 2048 and body['cache_prompt'] is False
        assert body['grammar'] == 'root ::= "<|det|>" .*'
        return httpx.Response(200, json={'stop_type':'eos','content':'<|det|>text [1,2,3,4]<|/det|>Review 2026-12-11<｜end▁of▁sentence｜>'})
    monkeypatch.setattr(unlimited_ocr, '_client', lambda: httpx.Client(base_url='http://ocr/', transport=httpx.MockTransport(handler)))
    blocks, _, provider = unlimited_ocr.read_blocks(png(), 'image/png')
    assert blocks[0]['text'] == 'Review 2026-12-11'
    assert provider == 'baidu-unlimited-ocr-q4'


@pytest.mark.parametrize('body,code', [({}, 'INVALID_RESPONSE'), ({'choices':[{'message':{'content':''}}]}, 'EMPTY_RESPONSE'), ({'choices':[{'finish_reason':'length','message':{'content':'partial'}}]}, 'TRUNCATED_OUTPUT')])
def test_unlimited_rejects_unusable_output(monkeypatch, body, code):
    monkeypatch.setattr(settings, 'unlimited_ocr_runtime', 'vllm')
    monkeypatch.setattr(unlimited_ocr, '_client', lambda: httpx.Client(base_url='http://ocr/v1/', transport=httpx.MockTransport(lambda r: httpx.Response(200,json=body))))
    with pytest.raises(ProviderError) as e:
        unlimited_ocr.read_blocks(png(), 'image/png')
    assert e.value.code == code


def test_rejects_invented_preamble_instead_of_hiding_it():
    with pytest.raises(ProviderError, match='UNSTRUCTURED_OUTPUT'):
        unlimited_ocr.parse_text('[No text detected]\n<|det|>text [1,2,3,4]<|/det|>Review tomorrow', strict=True)


def test_incomplete_layout_is_rejected():
    with pytest.raises(ProviderError, match='INVALID_LAYOUT'):
        unlimited_ocr.parse_text('<|det|>text [1,2,3,4]Review tomorrow', strict=True)


def test_layout_markup_does_not_change_doses_or_comparisons():
    text = '<|det|>text [1,2,3,4]<|/det|>TestMed 5 mg; value <5\n<|det|>text [1,2,3,4]<|/det|>2026-12-15<｜end▁of▁sentence｜>'
    assert unlimited_ocr.parse_text(text, strict=True) == 'TestMed 5 mg; value <5\n2026-12-15'


def test_blank_image_does_not_call_model(monkeypatch):
    data=io.BytesIO();Image.new('RGB',(100,100),'white').save(data,format='PNG')
    monkeypatch.setattr(unlimited_ocr, '_client', lambda: httpx.Client(base_url='http://ocr/',transport=httpx.MockTransport(lambda r:pytest.fail('Blank image sent to model'))))
    with pytest.raises(ProviderError, match='EMPTY_IMAGE'):
        unlimited_ocr.read_blocks(data.getvalue(),'image/png')


def test_blank_document_does_not_reach_another_ai_provider(monkeypatch):
    monkeypatch.setattr(settings, 'ocr_provider', 'unlimited')
    monkeypatch.setattr(pipeline, 'get_llm', lambda:pytest.fail('Blank image sent to another AI'))
    data=io.BytesIO();Image.new('RGB',(100,100),'white').save(data,format='PNG')
    with pytest.raises(ProviderError, match='NO_TEXT_FOUND'):
        pipeline.extract_document(data.getvalue(),'image/png','blank.png',today=date(2026,11,5))


@pytest.mark.parametrize('result', [{'stop_type':'limit','content':'partial'}, {'stop_type':'eos','truncated':True,'content':'partial'}])
def test_native_truncation_is_not_shown_as_complete(monkeypatch, result):
    monkeypatch.setattr(settings, 'unlimited_ocr_runtime', 'llamacpp')
    monkeypatch.setattr(unlimited_ocr, '_client', lambda: httpx.Client(base_url='http://ocr/', transport=httpx.MockTransport(lambda r:httpx.Response(200,json=result))))
    with pytest.raises(ProviderError, match='TRUNCATED_OUTPUT'):
        unlimited_ocr.read_blocks(png(),'image/png')


def test_no_ai_consent_never_calls_unlimited(monkeypatch):
    from app.ai.providers import local_docs
    monkeypatch.setattr(settings, 'ocr_provider', 'unlimited')
    monkeypatch.setattr(unlimited_ocr, 'read_blocks', lambda *a: pytest.fail('AI invoked without consent'))
    monkeypatch.setattr(local_docs, 'read_blocks', lambda *a: ([{'id':'p1-l1','page':1,'text':'Review after 7 days','bbox':None}], [], 'local'))
    result = pipeline.extract_document(png(), 'image/png', 'test.png', today=date(2026,11,4), local_only=True)
    assert result.ocr_provider == 'local'


@pytest.mark.parametrize('failure', ['NETWORK_ERROR', 'UNSTRUCTURED_OUTPUT', 'TRUNCATED_OUTPUT'])
def test_unlimited_failure_falls_back_to_local(monkeypatch, failure):
    from app.ai.providers import local_docs
    monkeypatch.setattr(settings, 'ocr_provider', 'unlimited')
    monkeypatch.setattr(settings, 'doc_provider', 'local')
    monkeypatch.setattr(pipeline, 'get_llm', lambda: None)
    def unavailable(*args): raise ProviderError('unlimited-ocr', failure)
    monkeypatch.setattr(unlimited_ocr, 'read_blocks', unavailable)
    monkeypatch.setattr(local_docs, 'read_blocks', lambda *a: ([{'id':'p1-l1','page':1,'text':'Review after 7 days','bbox':None}], [], 'local'))
    result = pipeline.extract_document(png(), 'image/png', 'test.png', today=date(2026,11,4))
    assert result.ocr_provider == 'local' and any(failure in n for n in result.notes)
