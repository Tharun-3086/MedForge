import uuid
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Patient,SourceArtifact,ExtractionProposal,ExtractedField
from app.services.health_readings import extract,latest,report_date_from_text
from tests.conftest import new_patient,patient_session

def test_conservative_reading_parser():
    assert str(report_date_from_text([{'text':'Document date: 2026-10-02'}]))=='2026-10-02'
    assert report_date_from_text([{'text':'Report date: 2026-10-02 Document date: 2026-10-01'}]) is None
    result=extract([{'id':'x','text':'BP: 120/80 mmHg\nFBS: 110 mg/dL\nPPBS: 7.2 mmol/L\nHbA1c: 6.2 %'}])
    assert result['blood_pressure'][0]=='120/80 mmHg'
    assert result['fasting_glucose'][0]=='110 mg/dL'
    assert result['postmeal_glucose'][0]=='7.2 mmol/L'
    assert 'blood_glucose' not in result
    assert not extract([{'text':'FBS: 70-100 mg/dL\nHbA1c: <6 %\nBP: 120/80\nGlucose: 110'}])
    assert not extract([{'text':'FBS: 110 mg/dL\nFBS: 140 mg/dL'}])

def document(db,patient,filename,when,text):
    artifact=SourceArtifact(clinic_id=patient.clinic_id,patient_id=patient.id,source_type='LAB_REPORT',filename=filename,mime_type='image/png',size_bytes=1,sha256='0'*64,storage_key='test')
    db.add(artifact);db.flush()
    proposal=ExtractionProposal(clinic_id=patient.clinic_id,patient_id=patient.id,artifact_id=artifact.id,status='NEEDS_REVIEW',blocks=[{'id':'line','text':text}])
    db.add(proposal);db.flush()
    db.add(ExtractedField(clinic_id=patient.clinic_id,proposal_id=proposal.id,position=0,name='document_date',value=when,proposed_value=when,status='UNVERIFIED'))
    db.flush();return artifact,proposal

def test_latest_by_report_date_missing_values_and_clinic_correction(nurse):
    pid=new_patient(nurse,'Readings QA','+919000470001')
    with SessionLocal() as db:
        patient=db.get(Patient,uuid.UUID(pid))
        old,_=document(db,patient,'older.png','2026-10-01','BP: 120/80 mmHg\nFBS: 110 mg/dL')
        newer,proposal=document(db,patient,'newer.png','2026-10-02','FBS: 130 mg/dL')
        document(db,patient,'old-uploaded-last.png','2026-09-01','FBS: 90 mg/dL')
        document(db,patient,'undated.png',None,'FBS: 150 mg/dL')
        db.commit();db.expire_all();result={r['key']:r for r in latest(db,patient.id,patient.clinic_id)['readings']}
        assert result['fasting_glucose']['value']=='130 mg/dL'
        assert result['blood_pressure']['artifact_id']==str(old.id)
        db.add(ExtractedField(clinic_id=patient.clinic_id,proposal_id=proposal.id,position=1,name='fasting_glucose',value='125 mg/dL',proposed_value='130 mg/dL',extracted_value='FBS: 130 mg/dL',status='APPROVED'))
        db.commit();db.expire_all();result={r['key']:r for r in latest(db,patient.id,patient.clinic_id)['readings']}
        assert result['fasting_glucose']['value']=='125 mg/dL' and result['fasting_glucose']['clinic_reviewed']
    patient_session(nurse,'nurse@sunrise.demo',pid)
    assert len(nurse.get('/v1/p/health-readings').json()['readings'])==2

def test_patient_readings_are_scoped(nurse):
    pid=new_patient(nurse,'Readings Other','+919000470002')
    patient_session(nurse,'nurse@sunrise.demo',pid)
    assert nurse.get('/v1/p/health-readings').json()['readings']==[]


def test_report_time_labels_validation_and_precedence():
    from app.services.health_readings import normalise_report_time,report_time_candidates
    assert normalise_report_time('2:05 PM')=='14:05:00'
    assert normalise_report_time('12:05 AM')=='00:05:00'
    assert normalise_report_time('24:05') is None
    assert normalise_report_time('2:70') is None
    blocks=[{'id':'a','text':'Report time: 18:10'},
            {'id':'b','text':'Collected On: 21-Jan-25 09:15 Received On: 21-Jan-25 10:30 Approved On: 12:00'},
            {'id':'c','text':'Uploaded at: 23:59'}]
    assert [r[0] for r in report_time_candidates(blocks)]==['09:15:00']
    assert not report_time_candidates([{'text':'Approved on: 20:00\nUploaded at: 21:00'}])


def test_same_day_collection_time_beats_upload_order(nurse):
    pid=new_patient(nurse,'Timed reports QA','+919000470011',plan_days=None)
    with SessionLocal() as db:
        patient=db.get(Patient,uuid.UUID(pid))
        evening,p1=document(db,patient,'evening-first.png','2026-10-02','HbA1c: 7.1 %')
        morning,p2=document(db,patient,'morning-uploaded-last.png','2026-10-02','HbA1c: 6.2 %')
        for proposal,clock in [(p1,'18:45:00'),(p2,'08:30:00')]:
            db.add(ExtractedField(clinic_id=patient.clinic_id,proposal_id=proposal.id,position=1,name='document_time',value=clock,proposed_value=clock,status='APPROVED'))
        db.commit();db.expire_all()
        result=latest(db,patient.id,patient.clinic_id)
        assert result['readings'][0]['artifact_id']==str(evening.id)
        assert result['readings'][0]['report_time']=='18:45:00'
        assert len(result['history'])==2
        document(db,patient,'older-day-late-clock.png','2026-10-01','HbA1c: 5.9 %')
        newer,_=document(db,patient,'next-day.png','2026-10-03','HbA1c: 6.9 %')
        db.commit();db.expire_all()
        assert latest(db,patient.id,patient.clinic_id)['readings'][0]['artifact_id']==str(newer.id)


def test_time_extraction_review_and_patient_display(nurse):
    pid=new_patient(nurse,'Collection time flow QA','+919000470012',plan_days=None)
    data=b'Report date,HbA1c,Sample collection time\n2026-10-02,7.3 %,14:35\n'
    response=nurse.post('/v1/intake-artifacts',data={'patient_id':pid,'source_type':'LAB_REPORT'},files={'file':('timed.csv',data,'text/csv')})
    assert response.status_code==201,response.text
    proposal=response.json()
    proposal=nurse.get('/v1/intake-proposals/'+proposal['id']).json()
    clock=next(f for f in proposal['fields'] if f['name']=='document_time')
    url=f"/v1/intake-proposals/{proposal['id']}/fields/{clock['id']}"
    assert nurse.patch(url,json={'action':'CORRECT','value':'25:99','reason':'Bad time example'}).status_code==422
    assert nurse.patch(url,json={'action':'APPROVE','reason':'Compared source clock'}).status_code==200
    patient_session(nurse,'nurse@sunrise.demo',pid)
    rows=nurse.get('/v1/p/health-readings').json()['readings']
    assert rows[0]['report_time']=='14:35:00'


def test_rejected_date_alternative_does_not_hide_confirmed_date(nurse):
    pid=new_patient(nurse,'OCR date alternatives QA','+919000588814',plan_days=None)
    with SessionLocal() as db:
        patient=db.get(Patient,uuid.UUID(pid))
        document(db,patient,'older.png','2026-01-01','FBS: 100 mg/dL')
        artifact,proposal=document(db,patient,'newer.png','2026-02-01','FBS: 120 mg/dL')
        date_field=db.scalar(select(ExtractedField).where(ExtractedField.proposal_id==proposal.id))
        date_field.status='APPROVED'
        db.add(ExtractedField(clinic_id=patient.clinic_id,proposal_id=proposal.id,position=1,name='document_date',value='2027-12-01',proposed_value='2027-12-01',status='REJECTED'))
        db.commit();db.expire_all()
        result=latest(db,patient.id,patient.clinic_id)['readings'][0]
        assert result['value']=='120 mg/dL' and result['report_date']=='2026-02-01' and result['date_reviewed']


def test_extended_measurements_units_and_abstention():
    from app.services.health_readings import valid_value
    text="Serum creatinine: 1.2 mg/dL\neGFR: >90 mL/min/1.73m2\nUACR: 12 mg/g\nTotal cholesterol: 180 mg/dL\nLDL: 95 mg/dL\nHDL: 50 mg/dL\nTriglycerides: 130 mg/dL\nWeight: 72.5 kg"
    result=extract([{'text':text}])
    assert len(result)==8
    assert result['egfr'][0]=='>90 mL/min/1.73m²'
    for key,row in result.items():assert valid_value(key,row[0]),(key,row)
    assert not extract([{'text':'Weight: 70-80 kg\nLDL: <100 mg/dL\nUACR: 12\nReference total cholesterol: 150 mg/dL\nUrine creatinine: 100 mg/dL'}])
    assert not valid_value('weight','72 kg extra text')
    assert extract([{'text':'Serum creatinine: 90 umol/L'}])['creatinine'][0]=='90 µmol/L'
    assert extract([{'text':'UACR: 2 mg/mmol\nWeight: 150 lb'}])['uacr'][0]=='2 mg/mmol'


def test_extended_history_verification_roles_and_tenant_scope(nurse):
    from tests.conftest import login
    pid=new_patient(nurse,'Extended history QA','+919000588832',plan_days=None)
    with SessionLocal() as db:
        patient=db.get(Patient,uuid.UUID(pid))
        old,p1=document(db,patient,'kidney-old.png','2026-01-01','Serum creatinine: 1.1 mg/dL\nWeight: 73 kg')
        new,p2=document(db,patient,'kidney-new.png','2026-02-01','Serum creatinine: 1.2 mg/dL\nWeight: 72 kg')
        bad,p3=document(db,patient,'kidney-uncertain.png','2026-03-01','Serum creatinine: 9 mg/dL')
        db.add(ExtractedField(clinic_id=patient.clinic_id,proposal_id=p3.id,position=1,name='creatinine',value='9 mg/dL',proposed_value='9 mg/dL',status='NEEDS_REVIEW',review_reasons=['HANDWRITING_REQUIRES_REVIEW']))
        db.commit();db.expire_all()
        result=latest(db,patient.id,patient.clinic_id)
        assert next(r for r in result['readings'] if r['key']=='creatinine')['value']=='1.2 mg/dL'
        assert len([r for r in result['history'] if r['key']=='creatinine'])==2
        assert result['pending_verification_count']==1
        assert all(r['artifact_id']!=str(bad.id) for r in result['history'])
    staff=nurse.get(f'/v1/priorities/{pid}/health-readings')
    assert staff.status_code==200
    patient_session(nurse,'nurse@sunrise.demo',pid)
    patient_result=nurse.get('/v1/p/health-readings').json()
    assert patient_result['history']==staff.json()['history']
    assert nurse.get(f'/v1/priorities/{pid}/health-readings').status_code==401
    login(nurse,'reception@sunrise.demo')
    assert nurse.get(f'/v1/priorities/{pid}/health-readings').status_code==403
    login(nurse,'doctor@lakeview.demo')
    assert nurse.get(f'/v1/priorities/{pid}/health-readings').status_code==404


def wrapped_lab_blocks(unit='mg/dl'):
    return [
        {'id':'date','page':1,'text':'Report date: 2026-11-12','bbox':[.1,.2,.8,.22],'ocr_conf':.99},
        {'id':'creat','page':1,'text':'S. CREATININE 0.8 mg/dl Child: 0.3-0.7 Male: 0.7-1.2','bbox':[.16,.48,.76,.51],'ocr_conf':.93},
        {'id':'fast','page':1,'text':f'FASTING BLOOD 75 {unit}74-110','bbox':[.16,.719,.59,.741],'ocr_conf':.99},
        {'id':'tail','page':1,'text':'SUGAR','bbox':[.16,.734,.24,.748],'ocr_conf':.99}]


def test_wrapped_lab_alias_units_and_geometry():
    from app.services.health_readings import candidates,measurement_blocks,valid_value
    from app.ai.pipeline import measurement_fields
    blocks=measurement_blocks(wrapped_lab_blocks())
    parsed=extract(blocks)
    assert parsed['creatinine'][0]=='0.8 mg/dL'
    assert parsed['fasting_glucose'][0]=='75 mg/dL'
    assert len(measurement_blocks(blocks))==len(blocks)
    assert set(parsed)=={'creatinine','fasting_glucose'}
    assert not extract([{'text':'Urine creatinine 20 mg/dL'}])
    assert not extract([{'text':'FBS 74-110 mg/dL'}])
    for change in ('page','distance','ambiguous'):
        raw=wrapped_lab_blocks()
        if change=='page':raw[-1]['page']=2
        if change=='distance':raw[-1]['bbox']=[.16,.85,.24,.87]
        if change=='ambiguous':raw.append(dict(raw[-1],id='other'))
        assert 'fasting_glucose' not in candidates(raw)
    field=next(f for f in measurement_fields(measurement_blocks(wrapped_lab_blocks('ng/dl'))) if f.name=='fasting_glucose')
    assert field.value=='75 ng/dL' and field.status=='NEEDS_REVIEW'
    assert 'UNSUPPORTED_MEASUREMENT_UNIT' in field.review_reasons
    assert {'fast','tail'}<=set(field.evidence['block_ids'])
    assert not valid_value('fasting_glucose','75 ng/dL')
    assert valid_value('fasting_glucose','75 mg/dL')


def test_wrapped_report_patient_and_clinic_review(nurse,monkeypatch):
    import io
    from PIL import Image
    from app.ai.providers import local_docs
    from tests.conftest import login
    monkeypatch.setattr(local_docs,'read_blocks',lambda *a:(wrapped_lab_blocks('ng/dl'),[], 'paddleocr'))
    pid=new_patient(nurse,'Wrapped Lab QA','+919000470040',plan_days=None)
    image=io.BytesIO();Image.new('RGB',(200,200),'white').save(image,format='PNG')
    response=nurse.post('/v1/intake-artifacts',data={'patient_id':pid,'source_type':'LAB_REPORT','document_style':'printed'},files={'file':('wrapped-qa.png',image.getvalue(),'image/png')})
    assert response.status_code==201,response.text
    proposal_id=response.json()['id']
    fields={f['name']:f for f in nurse.get('/v1/intake-proposals/'+proposal_id).json()['fields']}
    assert fields['creatinine']['value']=='0.8 mg/dL'
    assert fields['fasting_glucose']['value']=='75 ng/dL'
    login(nurse,'doctor@sunrise.demo')
    base='/v1/intake-proposals/'+proposal_id+'/fields/'
    assert nurse.patch(base+fields['fasting_glucose']['id'],json={'action':'APPROVE','reason':'Compared original'}).status_code==422
    for key,value in [('creatinine',None),('fasting_glucose','75 mg/dL')]:
        response=nurse.patch(base+fields[key]['id'],json={'action':'CORRECT' if value else 'APPROVE','value':value,'reason':'Compared fictional original'})
        assert response.status_code==200,response.text
    clinic=nurse.get(f'/v1/priorities/{pid}/health-readings').json()
    patient_session(nurse,'nurse@sunrise.demo',pid)
    patient=nurse.get('/v1/p/health-readings').json()
    assert patient==clinic
    readings={r['key']:r for r in patient['readings']}
    assert readings['creatinine']['value']=='0.8 mg/dL'
    assert readings['fasting_glucose']['value']=='75 mg/dL'
    assert all(r['clinic_reviewed'] for r in readings.values())
