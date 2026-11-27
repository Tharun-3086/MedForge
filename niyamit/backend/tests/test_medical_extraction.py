"""Synthetic contract/workflow checks, not a clinical OCR benchmark."""
import io
from datetime import date
import pytest
from PIL import Image
from app.ai import pipeline
from app.ai.medical_contracts import MedicalMeasurement
from app.ai.medical_validation import validate_measurements, reconcile_measurements
from app.ai.contracts import DOC_JSON_SCHEMA, sarvam_extract_schema
from app.ai.providers import local_docs
from app.ai.providers.sarvam import SarvamVisionExtract
from app.config import settings
from tests.conftest import new_patient, patient_session, login

TODAY=date(2026,11,27)

def blocks(text='Fasting plasma glucose 75 mg/dL (74-110)'):
    return [{'id':'row','page':1,'bbox':[.1,.2,.9,.25],'text':text,'ocr_conf':.99},
            {'id':'date','page':1,'bbox':[.1,.1,.9,.15],'text':'Report date: 12-Nov-2026','ocr_conf':.99}]

def candidate(**updates):
    return MedicalMeasurement.model_validate(dict(parameter='fasting_glucose',value='75',unit='mg/dL',reference_range='74-110',test_date='12-Nov-2026',quote='Fasting plasma glucose 75 mg/dL (74-110)',block_ids=['row'],confidence=.99,**{})|updates)

def configured(monkeypatch,rows=None,measurements=None):
    monkeypatch.setattr(settings,'doc_provider','sarvam')
    monkeypatch.setattr(settings,'ocr_provider','local')
    monkeypatch.setattr(type(settings),'sarvam_ready',lambda self:True)
    monkeypatch.setattr(local_docs,'read_blocks',lambda *a:(rows or blocks(),[],'fixture'))
    payload={'document_type':'LAB_REPORT','document_type__source_text':'glucose', 'document_date':'2026-11-12','document_date__source_text':'12-Nov-2026','measurements':measurements if measurements is not None else [candidate().model_dump()]}
    monkeypatch.setattr(SarvamVisionExtract,'extract',lambda *a,**kw:{'result':payload,'job_id':'synthetic-offline'})


def test_medical_schema_reaches_both_providers():
    assert 'measurements' in sarvam_extract_schema()['properties']
    assert 'measurements' in DOC_JSON_SCHEMA['required']
    assert 'fasting_glucose' in DOC_JSON_SCHEMA['properties']['measurements']['items']['properties']['parameter']['enum']


def test_ai_handles_synonym_not_regex_and_preserves_metadata(monkeypatch):
    configured(monkeypatch)
    assert not pipeline.measurement_fields(blocks())  # proves this is not a regex-only success
    result=pipeline.extract_document(b'synthetic','image/png','fixture.png',today=TODAY)
    field=next(f for f in result.fields if f.name=='fasting_glucose')
    assert field.value=='75 mg/dL' and field.status=='NEEDS_REVIEW'
    assert field.evidence['reference_range']=='74-110'
    assert field.evidence['test_date']=='2026-11-12'
    assert field.evidence['extraction_provider']=='sarvam-vision-extract'
    assert field.evidence['page']==1 and field.evidence['bboxes']
    assert not {'MEDICAL_SOURCE_NOT_GROUNDED','MEDICAL_VALUE_UNIT_NOT_GROUNDED'} & set(field.review_reasons)


@pytest.mark.parametrize('updates,reason',[
    ({'value':'175'},'MEDICAL_VALUE_UNIT_NOT_GROUNDED'),
    ({'unit':'mmol/L'},'MEDICAL_VALUE_UNIT_NOT_GROUNDED'),
    ({'quote':'Invented glucose 75 mg/dL'},'MEDICAL_SOURCE_NOT_GROUNDED'),
    ({'reference_range':'1-2'},'REFERENCE_RANGE_NOT_GROUNDED'),
    ({'test_date':'2026-01-01'},'MEASUREMENT_DATE_NOT_GROUNDED'),
    ({'unit':''},'UNSUPPORTED_MEASUREMENT_UNIT'),
])
def test_model_guess_is_never_silently_accepted(updates,reason):
    f=validate_measurements([candidate(**updates)],blocks(),TODAY,'fixture')[0]
    assert reason in f.review_reasons and f.status=='NEEDS_REVIEW'


def test_reference_limit_cannot_become_result():
    f=validate_measurements([candidate(value='74',quote='Reference: 74 mg/dL',reference_range='')],blocks('Reference: 74 mg/dL'),TODAY,'fixture')[0]
    assert 'POSSIBLE_REFERENCE_VALUE' in f.review_reasons


def test_rule_model_disagreement_keeps_both():
    rows=blocks('FBS 75 mg/dL; alternative 85 mg/dL')
    local=pipeline.measurement_fields(rows)
    ai=validate_measurements([candidate(value='85',quote=rows[0]['text'],reference_range='')],rows,TODAY,'fixture')
    fields=reconcile_measurements(local,ai)
    assert {f.value for f in fields}=={'75 mg/dL','85 mg/dL'}
    assert all('CONFLICTING_MEASUREMENTS' in f.review_reasons and f.status=='NEEDS_REVIEW' for f in fields)


def test_agreement_deduplicates_without_approval():
    rows=blocks('FBS 75 mg/dL')
    fields=reconcile_measurements(pipeline.measurement_fields(rows),validate_measurements([candidate(quote=rows[0]['text'],reference_range='')],rows,TODAY,'fixture'))
    assert len(fields)==1 and fields[0].status=='NEEDS_REVIEW'
    assert fields[0].evidence['extraction_sources']


def test_local_only_never_calls_medical_ai(monkeypatch):
    configured(monkeypatch)
    monkeypatch.setattr(SarvamVisionExtract,'extract',lambda *a,**kw:pytest.fail('Consent bypass'))
    result=pipeline.extract_document(b'synthetic','image/png','fixture.png',today=TODAY,local_only=True)
    assert not any(f.name=='fasting_glucose' for f in result.fields)


def test_openai_document_provider_receives_image_and_measurement_schema(monkeypatch):
    configured(monkeypatch)
    monkeypatch.setattr(settings,'doc_provider','openai')
    calls=[]
    class FakeOpenAI:
        name='openai';model='synthetic'
        def json_completion(self,*args,**kwargs):
            calls.append((args,kwargs))
            return {'fields':[],'measurements':[candidate().model_dump()]}
    monkeypatch.setattr(pipeline,'get_llm',lambda name=None:FakeOpenAI() if name=='openai' else pytest.fail('Wrong provider'))
    result=pipeline.extract_document(b'synthetic','image/png','fixture.png',today=TODAY)
    assert calls[0][1]['images']==[(b'synthetic','image/png')]
    assert result.extractor=='llm:openai'
    assert any(f.name=='fasting_glucose' for f in result.fields)


def test_structured_measurement_upload_review_patient_and_clinic(nurse,monkeypatch):
    configured(monkeypatch)
    pid=new_patient(nurse,'Structured Medical QA','+919000470050',plan_days=None)
    image=io.BytesIO();Image.new('RGB',(200,200),'white').save(image,format='PNG')
    r=nurse.post('/v1/intake-artifacts',data={'patient_id':pid,'source_type':'LAB_REPORT'},files={'file':('synthetic.png',image.getvalue(),'image/png')})
    assert r.status_code==201,r.text
    data=r.json();field=next(f for f in data['fields'] if f['name']=='fasting_glucose')
    assert nurse.get(f'/v1/priorities/{pid}/health-readings').json()['readings']==[]
    url=f"/v1/intake-proposals/{data['id']}/fields/{field['id']}"
    assert nurse.patch(url,json={'action':'APPROVE','reason':''}).status_code==422
    assert nurse.patch(url,json={'action':'APPROVE','reason':'Verified against fictional source row'}).status_code==200
    clinic=nurse.get(f'/v1/priorities/{pid}/health-readings').json()
    assert clinic['readings'][0]['value']=='75 mg/dL'
    assert clinic['readings'][0]['clinic_reviewed']
    patient_session(nurse,'nurse@sunrise.demo',pid)
    assert nurse.get('/v1/p/health-readings').json()==clinic
    assert nurse.get('/v1/intake-proposals/'+data['id']).status_code==401


def test_actual_provider_label_and_table_separator_are_retained(monkeypatch):
    source=blocks('Fasting plasma glucose 75 mg/dL 74-110')
    configured(monkeypatch,rows=source,measurements=[candidate(quote='Fasting plasma glucose | 75 | mg/dL | 74-110',block_ids=['L004']).model_dump()|{'parameter':'Fasting plasma glucose'}])
    result=pipeline.extract_document(b'synthetic','image/png','fixture.png',today=TODAY)
    field=next(f for f in result.fields if f.name=='fasting_glucose')
    assert field.value=='75 mg/dL'
    assert field.evidence['parameter_as_written']=='Fasting plasma glucose'
    assert field.evidence['block_ids']==['row']
    assert 'MEDICAL_SOURCE_NOT_GROUNDED' not in field.review_reasons
    assert field.status=='NEEDS_REVIEW'


def test_explicit_local_document_provider_never_uses_external_llm(monkeypatch):
    configured(monkeypatch)
    monkeypatch.setattr(settings,'doc_provider','local')
    monkeypatch.setattr(pipeline,'get_llm',lambda *a:pytest.fail('Local provider sent data externally'))
    result=pipeline.extract_document(b'synthetic','image/png','fixture.png',today=TODAY)
    assert result.extractor=='rules'


def test_generic_provider_glucose_is_refined_only_from_explicit_source():
    assert candidate(parameter='GLUCOSE').parameter=='fasting_glucose'
    assert candidate(parameter='GLUCOSE',quote='Glucose 75 mg/dL').parameter=='blood_glucose'
    assert candidate(parameter='GLUCOSE',quote='Fasting glucose 75 mg/dL and random glucose 80 mg/dL').parameter=='blood_glucose'


def test_unknown_provider_parameter_is_visible_but_not_a_supported_reading():
    field=validate_measurements([candidate(parameter='new unsupported analyte')],blocks(),TODAY,'fixture')[0]
    assert field.name=='unmapped_measurement' and field.status=='NEEDS_REVIEW'
    assert 'UNSUPPORTED_MEDICAL_PARAMETER' in field.review_reasons
