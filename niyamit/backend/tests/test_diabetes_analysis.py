"""Source-linked summaries and isolation; synthetic data only."""
from app.services.diabetes_analysis import document_scope,range_comparison,comparisons
from tests.conftest import new_patient,patient_session,login


def reading(value='75 mg/dL',date='2026-11-12',**updates):
    return dict(key='fasting_glucose',value=value,clinic_reviewed=True,date_reviewed=True,report_date=date,
        artifact_id='synthetic',source_metadata={'unit':'mg/dL','reference_range':'74-110'})|updates


def test_scope_never_infers_diagnosis_or_every_document_relevant():
    assert document_scope([{'text':'Fasting glucose 75 mg/dL'}],[])['status']=='DIABETES_RELATED'
    assert document_scope([{'text':'Dental invoice tooth extraction'}],[])['status']=='OUT_OF_SCOPE'
    assert document_scope([{'text':'unreadable'}],[])['status']=='UNCERTAIN'


def test_copied_ranges_are_not_targets_and_units_cannot_cross():
    assert range_comparison(reading())['status']=='within_copied_range'
    assert range_comparison(reading('120 mg/dL'))['status']=='above_copied_range'
    assert range_comparison(reading('50 mg/dL'))['status']=='below_copied_range'
    assert range_comparison(reading('5 mmol/L')) is None
    assert range_comparison(reading(source_metadata={'unit':'mg/dL','reference_range':'<110'})) is None
    assert 'not your individualized target' in range_comparison(reading())['limitation']


def test_history_excludes_unreviewed_units_and_conflicting_same_day():
    rows=[reading('90 mg/dL','2026-10-01'),reading('75 mg/dL'),reading('900 mg/dL',clinic_reviewed=False),reading('5 mmol/L')]
    result=comparisons(rows)
    assert len(result)==1 and result[0]['change']=='-15' and result[0]['direction']=='decreased'
    rows.append(reading('95 mg/dL'))
    assert comparisons(rows)==[]


def test_summary_export_and_tenant_patient_isolation(nurse):
    pid=new_patient(nurse,'Summary QA','+919000470060',plan_days=None)
    other=new_patient(nurse,'Summary Other QA','+919000470061',plan_days=None)
    endpoint=f'/v1/patients/{pid}/diabetes-summary'
    r=nurse.get(endpoint)
    assert r.status_code==200 and r.json()['patient']['id']==pid
    assert r.json()['medication_history']['status']=='NOT_STRUCTURED'
    assert 'attachment' in nurse.get(endpoint+'?download=true').headers['content-disposition']
    patient_session(nurse,'nurse@sunrise.demo',pid)
    assert nurse.get('/v1/p/diabetes-summary').json()['patient']['id']==pid
    assert nurse.get(f'/v1/patients/{other}/diabetes-summary').status_code==401
    login(nurse,'doctor@sunrise.demo')
    # The demo doctor at the other clinic must not see this record.
    login(nurse,'doctor@lakeview.demo')
    assert nurse.get(endpoint).status_code==404


def test_duplicate_upload_reuses_only_same_patient(nurse):
    pid=new_patient(nurse,'Dedupe QA','+919000470062',plan_days=None)
    other=new_patient(nurse,'Dedupe Other QA','+919000470063',plan_days=None)
    def upload(patient):
        return nurse.post('/v1/intake-artifacts',data={'patient_id':patient,'source_type':'LAB_REPORT'},files={'file':('synthetic.csv',b'Report date,FBS\n2026-11-12,75 mg/dL\n','text/csv')})
    first,second=upload(pid),upload(pid)
    assert first.status_code==second.status_code==201
    assert first.json()['id']==second.json()['id']
    assert upload(other).json()['artifact']['id']!=first.json()['artifact']['id']
