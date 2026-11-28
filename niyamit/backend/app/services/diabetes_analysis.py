"""Source-linked diabetes monitoring summary. No diagnosis, dosing or inferred targets."""
import re
from decimal import Decimal
from collections import defaultdict
from sqlalchemy import select
from app.models import SourceArtifact, ExtractionProposal
from app.services.health_readings import latest, LABELS

RULE_VERSION='diabetes-summary-v1'
EXPLANATIONS={
 'hba1c':'A report measure of longer-term blood glucose exposure. Your clinician sets your personal target.',
 'fasting_glucose':'Blood glucose labelled fasting on this report.',
 'postmeal_glucose':'Blood glucose labelled after a meal. Timing after the meal matters.',
 'random_glucose':'Blood glucose measured without a specified fasting or meal schedule.',
 'blood_glucose':'The report does not establish whether this glucose result was fasting, post-meal or random.',
 'creatinine':'A blood marker used when assessing kidney function; it is interpreted with other information.',
 'egfr':'An estimate used to assess kidney filtration. A single result does not establish a diagnosis.',
 'uacr':'A urine albumin-to-creatinine measurement used in kidney assessment.',
 'total_cholesterol':'A total cholesterol measurement, considered alongside the rest of the lipid profile.',
 'ldl':'A lipid measurement considered when reviewing cardiovascular risk.',
 'hdl':'One part of the cholesterol profile.',
 'triglycerides':'A blood fat measurement; fasting status can affect interpretation.',
 'blood_pressure':'A recorded systolic/diastolic blood pressure pair. This is not continuous monitoring.',
 'weight':'A recorded weight. BMI needs a reliable height and cannot be inferred from weight alone.'}


def document_scope(blocks,fields):
    text=' '.join(b.get('text','') for b in blocks)
    if any(f.name in LABELS for f in fields) or re.search(r'(?i)diabet|hba1c|glucose|insulin|retin|fundus|foot exam|creatinine|lipid|cholesterol',text):
        return {'status':'DIABETES_RELATED','reason':'Contains measurements or follow-up information used in diabetes care; this does not establish a diabetes diagnosis.'}
    if re.search(r'(?i)invoice|dental|tooth|orthodont|passport|boarding pass|electricity bill',text):
        return {'status':'OUT_OF_SCOPE','reason':'No supported diabetes-related information was found; this document appears unrelated to diabetes monitoring.'}
    return {'status':'UNCERTAIN','reason':'Diabetes relevance could not be established. Ask the clinic to review the original.'}


def range_comparison(reading):
    metadata=reading.get('source_metadata',{})
    raw=metadata.get('reference_range') or ''
    match=re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*',raw)
    value=re.fullmatch(r'(\d+(?:\.\d+)?) (.+)',reading['value'])
    if not (match and value and metadata.get('unit')==value[2]):return None
    lo,hi,n=Decimal(match[1]),Decimal(match[2]),Decimal(value[1])
    if lo>hi:return None
    return {'status':'below_copied_range' if n<lo else 'above_copied_range' if n>hi else 'within_copied_range',
        'range_as_written':raw,'unit':value[2],
        'limitation':'Comparison uses the copied laboratory range, which is not separately clinic-verified and is not your individualized target.'}


def comparisons(history):
    groups=defaultdict(list)
    for row in history:
        if not(row['clinic_reviewed'] and row['date_reviewed'] and row['report_date']):continue
        m=re.fullmatch(r'(\d+(?:\.\d+)?) (.+)',row['value'])
        if m:groups[(row['key'],m[2])].append((row,Decimal(m[1])))
    output=[]
    for (key,unit),rows in groups.items():
        dates=defaultdict(list)
        for row,value in rows:dates[row['report_date']].append((row,value))
        usable=[entries[0] for _,entries in sorted(dates.items()) if len({v for _,v in entries})==1]
        if len(usable)<2:continue
        older,newer=usable[-2],usable[-1]
        delta=newer[1]-older[1]
        output.append({'parameter':key,'label':LABELS.get(key,newer[0].get('label',key)),'unit':unit,'direction':'increased' if delta>0 else 'decreased' if delta<0 else 'unchanged',
            'change':str(delta),'previous':older[0],'current':newer[0],
            'interpretation':'Numerical change only; whether this is clinically improving or worsening needs your clinician’s assessment.'})
    return output


def summary(db,patient):
    snapshot=latest(db,patient.id,patient.clinic_id)
    docs=db.execute(select(SourceArtifact,ExtractionProposal).join(ExtractionProposal,ExtractionProposal.artifact_id==SourceArtifact.id)
        .where(SourceArtifact.patient_id==patient.id,SourceArtifact.clinic_id==patient.clinic_id,
               ExtractionProposal.patient_id==patient.id,ExtractionProposal.clinic_id==patient.clinic_id,
               SourceArtifact.deleted_at.is_(None)).order_by(SourceArtifact.created_at.desc())).all()
    findings=[]
    for row in snapshot['readings']:
        findings.append({**row,'explanation':EXPLANATIONS.get(row['key'],''),
            'range_comparison':range_comparison(row) if row['clinic_reviewed'] else None})
    present={r['key'] for r in snapshot['history'] if r['clinic_reviewed']}
    return {'schema_version':RULE_VERSION,'patient':{'id':str(patient.id),'name':patient.display_name},
        'findings':findings,'historical_comparisons':comparisons(snapshot['history']),
        'documents':[{'artifact_id':str(a.id),'proposal_id':str(p.id),'filename':a.filename,'uploaded_at':a.created_at.isoformat(),
                      'status':p.status,'scope':document_scope(p.blocks or [],p.fields)} for a,p in docs],
        'missing_from_verified_records':[LABELS[k] for k in LABELS if k not in present],
        'medication_history':{'status':'NOT_STRUCTURED','message':'Medication history has not been validated for structured extraction. Consult the original prescriptions and your clinician.'},
        'screening_information':{'status':'NOT_STRUCTURED','message':'A due date is not evidence that an eye or foot examination was performed.'},
        'questions':['Are the extracted values, units and report dates correct?','Which personal targets and screening schedule apply to me?'],
        'pending_verification_count':snapshot['pending_verification_count'],'processing':snapshot['processing'],
        'limitations':['No diagnosis or medication/insulin dose changes are generated.',
            'Missing from these records does not mean a test was not performed or that it is clinically required.',
            'Laboratory reference ranges are not individualized treatment targets.',
            'Only clinic-reviewed values and dates are compared; units remain separate and same-day conflicts are excluded.',
            'This summary uses versioned rules and explanatory copy, not a clinically validated AI opinion.']}
