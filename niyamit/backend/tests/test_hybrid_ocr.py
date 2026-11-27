import io
from datetime import date
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from app.ai import pipeline
from app.ai.providers import hybrid_ocr, local_docs
from app.ai.providers.base import ProviderError
from app.config import settings
from tests.conftest import new_patient, patient_session, login


def png():
    out = io.BytesIO()
    Image.new("RGB", (800, 600), "white").save(out, format="PNG")
    return out.getvalue()


def line(text="FBS: 110 mg/dL", score=0.4):
    return {"text": text, "ocr_conf": score, "pixels": [10, 10, 500, 50],
            "polygon": [[10, 10], [500, 10], [500, 50], [10, 50]]}


def test_handwriting_disagreement_preserves_both_candidates(monkeypatch):
    monkeypatch.setattr(hybrid_ocr, "printed_lines", lambda *a: [line()])
    monkeypatch.setattr(hybrid_ocr, "handwritten_line", lambda *a: "FBS: 170 mg/dL")
    blocks, pages = hybrid_ocr.read_image(png(), page=2, style="handwritten")
    assert blocks[0]["text"] == "FBS: 110 mg/dL"
    assert blocks[0]["alternatives"][0]["text"] == "FBS: 170 mg/dL"
    assert {"OCR_DISAGREEMENT", "HANDWRITING_REQUIRES_REVIEW", "LOW_OCR_CONFIDENCE"} <= set(blocks[0]["review_reasons"])
    assert blocks[0]["bbox"][2] == 500/800 and pages[0]["page"] == 2


@pytest.mark.parametrize("language", ["hi", "te"])
def test_english_handwriting_model_never_runs_for_regional_languages(monkeypatch, language):
    monkeypatch.setattr(hybrid_ocr, "printed_lines", lambda *a: [line(score=.99)])
    monkeypatch.setattr(hybrid_ocr, "handwritten_line", lambda *a: pytest.fail("English model used for regional handwriting"))
    blocks, _ = hybrid_ocr.read_image(png(), page=1, style="mixed", language=language)
    assert "UNSUPPORTED_HANDWRITING_LANGUAGE" in blocks[0]["review_reasons"]


def test_missing_paddle_falls_back_to_tesseract_and_requires_review(monkeypatch):
    def fail(*args): raise ImportError("optional model not installed")
    monkeypatch.setattr(hybrid_ocr, "printed_lines", fail)
    monkeypatch.setattr(local_docs, "_ocr_image", lambda *a, **k: ([{"id":"x","page":1,"text":"FBS: 110 mg/dL","engine":"tesseract"}], [{"page":1,"width":800,"height":600}]))
    blocks, pages = hybrid_ocr.read_image(png(), page=1)
    assert blocks[0]["engine"] == "tesseract" and "OCR_FALLBACK" in blocks[0]["review_reasons"]
    assert "OCR_FALLBACK" in pages[0]["review_reasons"]


def test_handwriting_work_is_bounded(monkeypatch):
    monkeypatch.setattr(settings, "ocr_max_handwritten_lines", 1)
    monkeypatch.setattr(hybrid_ocr, "printed_lines", lambda *a: [line(), line()])
    calls=[]
    monkeypatch.setattr(hybrid_ocr, "handwritten_line", lambda *a: calls.append(1) or "FBS: 110 mg/dL")
    blocks, _ = hybrid_ocr.read_image(png(), page=1, style="handwritten")
    assert len(calls)==1 and "OCR_INCOMPLETE" in blocks[1]["review_reasons"]


def test_mixed_pdf_routes_each_page_independently(monkeypatch):
    writer=PdfWriter()
    source=PdfReader(Path(__file__).parents[1]/"samples/lab_report_hba1c.pdf")
    writer.add_page(source.pages[0]);writer.add_blank_page(width=600,height=800)
    out=io.BytesIO();writer.write(out)
    calls=[]
    monkeypatch.setattr(local_docs,"render_pdf_page",lambda data,page: calls.append(page) or png())
    monkeypatch.setattr(local_docs,"_ocr_image",lambda data,page: ([{"id":"scan","page":page,"text":"FBS: 110 mg/dL","bbox":[.1,.1,.8,.2]}],[]))
    blocks,pages,engine=local_docs.read_blocks(out.getvalue(),"application/pdf")
    assert calls==[2] and len(pages)==2
    assert any(b["page"]==1 for b in blocks) and any(b["page"]==2 for b in blocks)
    assert engine=="pdf-text+tesseract"


def test_pdf_conflicting_overlay_is_not_silently_discarded():
    rows=local_docs.merge_blocks([{"text":"FBS: 110 mg/dL","page":1,"bbox":[.1,.1,.9,.2]}],
                                [{"text":"FBS: 170 mg/dL","page":1,"bbox":[.1,.1,.9,.2]}])
    assert len(rows)==2 and all("OCR_DISAGREEMENT" in r["review_reasons"] for r in rows)


def test_table_cells_join_without_losing_uncertain_alternatives():
    cells=[{"id":"a","page":1,"text":"FBS:","bbox":[.1,.1,.3,.2],"ocr_conf":.99,"engine":"paddleocr"},
           {"id":"b","page":1,"text":"110 mg/dL","bbox":[.4,.1,.8,.2],"ocr_conf":.3,"engine":"paddleocr",
            "review_reasons":["OCR_DISAGREEMENT"],"alternatives":[{"text":"170 mg/dL","engine":"trocr"}]}]
    rows=hybrid_ocr.join_rows(cells)
    assert len(rows)==1 and rows[0]["text"]=="FBS: 110 mg/dL"
    assert rows[0]["alternatives"][0]["text"]=="FBS: 170 mg/dL"
    assert rows[0]["ocr_conf"]==.3 and rows[0]["bbox"]==[.1,.1,.8,.2]


def test_pdf_native_text_still_checks_scanned_regions_in_hybrid_mode(monkeypatch):
    source=(Path(__file__).parents[1]/"samples/lab_report_hba1c.pdf").read_bytes()
    calls=[]
    monkeypatch.setattr(local_docs,"render_pdf_page",lambda data,page: png())
    def reader(data,*,page):
        calls.append(page)
        return [{"id":"hand","page":page,"text":"FBS: 170 mg/dL","bbox":[.1,.95,.8,.99],"review_reasons":["HANDWRITING_REQUIRES_REVIEW"]}],[]
    blocks,_,_=local_docs.read_blocks(source,"application/pdf",image_reader=reader,scan_all_pages=True)
    assert calls==[1] and any(b["text"]=="FBS: 170 mg/dL" for b in blocks)


def test_local_consent_path_does_not_call_external_document_ai(monkeypatch):
    monkeypatch.setattr(settings,"ocr_provider","hybrid")
    monkeypatch.setattr(hybrid_ocr,"printed_lines",lambda *a:[line(score=.99)])
    monkeypatch.setattr(pipeline,"get_llm",lambda *a:pytest.fail("External AI used without consent"))
    result=pipeline.extract_document(png(),"image/png","x.png",today=date(2026,11,22),local_only=True)
    assert result.ocr_provider=="hybrid" and result.fields


def test_uncertain_patient_upload_clinic_review_and_dashboard_e2e(nurse,monkeypatch):
    monkeypatch.setattr(settings,"ocr_provider","hybrid")
    monkeypatch.setattr(hybrid_ocr,"printed_lines",lambda *a:[line()])
    monkeypatch.setattr(hybrid_ocr,"handwritten_line",lambda *a:"FBS: 170 mg/dL")
    pid=new_patient(nurse,"Hybrid OCR QA","+919000588811",plan_days=None)
    patient_session(nurse,"nurse@sunrise.demo",pid)
    response=nurse.post("/v1/p/documents",data={"document_style":"handwritten","document_language":"en"},
                        files={"file":("handwritten.png",png(),"image/png")})
    assert response.status_code==201,response.text
    doc=nurse.get("/v1/p/documents").json()["documents"][0]
    assert doc["verification_required"] and "170 mg/dL" in doc["automatic_text"]
    health=nurse.get("/v1/p/health-readings").json()
    assert health["readings"]==[] and health["pending_verification_count"]==1
    login(nurse,"nurse@sunrise.demo")
    summary=next(p for p in nurse.get("/v1/intake-proposals").json()["proposals"] if p["artifact"]["id"]==doc["id"])
    proposal=nurse.get("/v1/intake-proposals/"+summary["id"]).json()
    assert proposal["artifact"]["document_style"]=="handwritten"
    readings=[f for f in proposal["fields"] if f["name"]=="fasting_glucose"]
    assert {f["value"] for f in readings}=={"110 mg/dL","170 mg/dL"}
    assert all(f["status"]=="NEEDS_REVIEW" and f["evidence"]["bboxes"] for f in readings)
    for f in readings:
        endpoint=f"/v1/intake-proposals/{proposal['id']}/fields/{f['id']}"
        assert nurse.patch(endpoint,json={"action":"APPROVE"}).status_code==422
        action={"action":"APPROVE","reason":"Compared the original source image and confirmed the reading"} if f["value"]=="110 mg/dL" else {"action":"REJECT","reason":"Alternative does not match source"}
        assert nurse.patch(endpoint,json=action).status_code==200
    patient_session(nurse,"nurse@sunrise.demo",pid)
    health=nurse.get("/v1/p/health-readings").json()
    assert health["pending_verification_count"]==0
    assert health["readings"][0]["value"]=="110 mg/dL" and health["readings"][0]["clinic_reviewed"]
    assert nurse.get("/v1/p/documents").json()["documents"][0]["clinic_reviewed_fields"][0]["value"]=="110 mg/dL"


def test_reception_cannot_confirm_health_readings(nurse,monkeypatch):
    monkeypatch.setattr(settings,"ocr_provider","hybrid")
    monkeypatch.setattr(hybrid_ocr,"printed_lines",lambda *a:[line(score=.99)])
    pid=new_patient(nurse,"Review role QA","+919000588812",plan_days=None)
    r=nurse.post('/v1/intake-artifacts',data={'patient_id':pid},files={'file':('printed.png',png(),'image/png')})
    assert r.status_code==201,r.text
    proposal=r.json();field=next(f for f in proposal['fields'] if f['name']=='fasting_glucose')
    # Use an actual seeded reception membership, not an invented role/session.
    from app.seed import STAFF_A
    reception=next(row[0] for row in STAFF_A if row[2]=='RECEPTION')
    login(nurse,reception)
    r=nurse.patch(f"/v1/intake-proposals/{proposal['id']}/fields/{field['id']}",json={'action':'APPROVE'})
    assert r.status_code==403,r.text
