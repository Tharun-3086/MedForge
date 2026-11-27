"""Source-linked report measurements, shared by patients and authorised clinic staff."""
import re
import hashlib
from datetime import date
from sqlalchemy import select
from app.config import settings
from app.models import SourceArtifact, ExtractionProposal

LABELS={"blood_pressure":"Blood pressure","fasting_glucose":"Fasting glucose","postmeal_glucose":"Post-meal glucose","random_glucose":"Random glucose","blood_glucose":"Glucose (type unspecified)","hba1c":"HbA1c","creatinine":"Serum creatinine","egfr":"eGFR","uacr":"Urine albumin/creatinine ratio","total_cholesterol":"Total cholesterol","ldl":"LDL cholesterol","hdl":"HDL cholesterol","triglycerides":"Triglycerides","weight":"Weight"}
NUM=r"(\d{1,4}(?:\.\d{1,3})?)"
UNIT=r"(mg\s*/\s*dl|mmol\s*/\s*l)"
PATTERNS={
 "blood_pressure":r"(?:blood pressure|b\.?p\.?)\s*[:=]?\s*(\d{2,3})\s*/\s*(\d{2,3})\s*(mm\s*hg)\b",
 "fasting_glucose":r"(?:fasting(?: blood)? (?:glucose|sugar)|fbs|fbg)\s*[:=]?\s*"+NUM+r"\s*"+UNIT+r"\b",
 "postmeal_glucose":r"(?:post[- ]?(?:meal|prandial)(?: blood)? (?:glucose|sugar)|ppbs|ppbg)\s*[:=]?\s*"+NUM+r"\s*"+UNIT+r"\b",
 "random_glucose":r"(?:random(?: blood)? (?:glucose|sugar)|rbs|rbg)\s*[:=]?\s*"+NUM+r"\s*"+UNIT+r"\b",
 "blood_glucose":r"^(?:blood glucose|glucose|blood sugar)\s*[:=]?\s*"+NUM+r"\s*"+UNIT+r"\b",
 "hba1c":r"(?:hba1c|hb a1c|glycated h(?:ae|e)moglobin)\s*[:=]?\s*"+NUM+r"\s*(%)",
 "creatinine":r"^(?:serum |blood |plasma )creatinine\s*[:=]?\s*"+NUM+r"\s*(mg\s*/\s*dl|[uµμ]mol\s*/\s*l)\b",
 "egfr":r"^(?:egfr|estimated glomerular filtration rate)\s*[:=]?\s*([<>]=?\s*\d{1,4}(?:\.\d+)?|\d{1,4}(?:\.\d+)?)\s*(ml\s*/\s*min\s*/\s*1\.73\s*m(?:2|²|\^2))",
 "uacr":r"^(?:uacr|urine albumin\s*[/\-]\s*(?:to[\- ]*)?creatinine(?: ratio)?|urine albumin.to.creatinine ratio)\s*[:=]?\s*"+NUM+r"\s*(mg\s*/\s*g|mg\s*/\s*mmol)\b",
 "total_cholesterol":r"^(?:total cholesterol|cholesterol total)\s*[:=]?\s*"+NUM+r"\s*"+UNIT+r"\b",
 "ldl":r"^(?:ldl(?:[ -]cholesterol)?|cholesterol ldl)\s*[:=]?\s*"+NUM+r"\s*"+UNIT+r"\b",
 "hdl":r"^(?:hdl(?:[ -]cholesterol)?|cholesterol hdl)\s*[:=]?\s*"+NUM+r"\s*"+UNIT+r"\b",
 "triglycerides":r"^(?:triglycerides|triglyceride|tg)\s*[:=]?\s*"+NUM+r"\s*"+UNIT+r"\b",
 "weight":r"^(?:body weight|weight)\s*[:=]?\s*"+NUM+r"\s*(kg|lbs?|kilograms?)\b",
}
UNITS={'mg/dl':'mg/dL','mmol/l':'mmol/L','%':'%','umol/l':'µmol/L','µmol/l':'µmol/L','μmol/l':'µmol/L','mg/g':'mg/g','mg/mmol':'mg/mmol','kg':'kg','kilogram':'kg','kilograms':'kg','lb':'lb','lbs':'lb','ml/min/1.73m2':'mL/min/1.73m²','ml/min/1.73m²':'mL/min/1.73m²','ml/min/1.73m^2':'mL/min/1.73m²'}

def candidates(blocks):
    found={}
    for block in blocks:
        for line in str(block.get('text','')).splitlines():
            line=line.strip()
            if re.search(r'(?i)reference|normal range|target|goal',line):continue
            for key,pattern in PATTERNS.items():
                for m in re.finditer(pattern,line,re.I):
                    parts=m.groups()
                    if key=='blood_pressure':value=parts[0]+'/'+parts[1]+' mmHg'
                    else:value=parts[0].replace(' ','')+' '+UNITS[parts[1].replace(' ','').lower()]
                    found.setdefault(key,[]).append((value,line[:300],block.get('id')))
    return found

def extract(blocks):
    return {key:rows[0] for key,rows in candidates(blocks).items() if len({r[0] for r in rows})==1}

def report_date_from_text(blocks):
    values=set()
    for block in blocks:
        for match in re.finditer(r"(?:document|report) date\s*[:=]?\s*(\d{4}-\d{2}-\d{2})\b",str(block.get('text','')),re.I):
            try:values.add(date.fromisoformat(match.group(1)))
            except ValueError:pass
    return next(iter(values)) if len(values)==1 else None

def valid_value(key,value):
    if key not in LABELS or not value:return False
    parsed=extract([{'text':LABELS[key].replace(' (type unspecified)','')+': '+value}]).get(key)
    return bool(parsed and parsed[0]==value)

def latest(db,patient_id,clinic_id):
    rows=db.execute(select(SourceArtifact,ExtractionProposal).join(ExtractionProposal,ExtractionProposal.artifact_id==SourceArtifact.id)
        .where(SourceArtifact.patient_id==patient_id,SourceArtifact.clinic_id==clinic_id,
               ExtractionProposal.patient_id==patient_id,ExtractionProposal.clinic_id==clinic_id,
               SourceArtifact.deleted_at.is_(None),SourceArtifact.source_type.in_(['LAB_REPORT','PRESCRIPTION','OTHER']))).all()
    from app.ai.providers.ocr_review import VERIFICATION_REASONS
    readings={};ranks={};processing=False;pending=set();history=[]
    for artifact,proposal in rows:
        processing=processing or proposal.status=='EXTRACTION_PENDING'
        if proposal.status in ('REJECTED','EXTRACTION_PENDING','EXTRACTION_FAILED'):continue
        fields={f.name:f for f in proposal.fields}
        dates=[f for f in proposal.fields if f.name=='document_date' and f.status!='REJECTED']
        approved_dates=[f for f in dates if f.status=='APPROVED']
        doc=approved_dates[0] if approved_dates else dates[0] if dates else fields.get('document_date')
        date_conflict=len({f.value for f in approved_dates})>1 or any(f.status=='NEEDS_REVIEW' for f in dates)
        rawdate=None if date_conflict else (doc.value if doc and doc.status=='APPROVED' else doc.proposed_value if doc and doc.status not in ('REJECTED','NEEDS_REVIEW') else None)
        try:report_date=date.fromisoformat(rawdate) if rawdate else None
        except ValueError:report_date=None
        if report_date is None and not date_conflict and not (doc and doc.status in ('REJECTED','NEEDS_REVIEW')):report_date=report_date_from_text(proposal.blocks or [])
        if report_date and report_date>artifact.created_at.date():report_date=None
        rank=(report_date or date.min,artifact.created_at,str(artifact.id))
        parsed=extract(proposal.blocks or [])
        for key in LABELS:
            matching=[f for f in proposal.fields if f.name==key and f.status!='REJECTED']
            if any(f.status!='APPROVED' and (f.status=='NEEDS_REVIEW' or VERIFICATION_REASONS.intersection(f.review_reasons or [])) for f in matching):
                pending.add((str(artifact.id),key));continue
            approved=[f for f in matching if f.status=='APPROVED']
            if len({f.value for f in approved})>1:
                pending.add((str(artifact.id),key));continue
            field=approved[0] if approved else fields.get(key)
            if field and field.status=='REJECTED':continue
            if not field:
                raw=parsed.get(key)
                source=next((b for b in proposal.blocks or [] if raw and b.get('id')==raw[2]),None)
                if source and (VERIFICATION_REASONS.intersection(source.get('review_reasons',[])) or (source.get('ocr_conf') is not None and source['ocr_conf']<settings.ocr_review_threshold)):
                    pending.add((str(artifact.id),key));continue
            value=field.value if field and field.status=='APPROVED' else field.proposed_value if field else parsed.get(key,(None,))[0]
            if not valid_value(key,value):continue
            record={'key':key,'label':LABELS[key],'value':value,'report_date':str(report_date) if report_date else None,
                    'date_reviewed':bool(doc and doc.status=='APPROVED'),'uploaded_at':artifact.created_at.isoformat(),
                    'clinic_reviewed':bool(field and field.status=='APPROVED'),'filename':artifact.filename,
                    'artifact_id':str(artifact.id),'source_text':field.extracted_value if field else parsed[key][1], 'proposal_id':str(proposal.id)}
            history.append(record)
            if key not in ranks or rank>ranks[key]:ranks[key]=rank;readings[key]=record
    history.sort(key=lambda r:(r['report_date'] or '',r['uploaded_at'],r['artifact_id']),reverse=True)
    revision=hashlib.sha256(repr((sorted((str(a.id),p.status) for a,p in rows),history,sorted(pending))).encode()).hexdigest()
    return {'readings':list(readings.values()),'processing':processing,'pending_verification_count':len(pending),'source_revision':revision,'history':history}
