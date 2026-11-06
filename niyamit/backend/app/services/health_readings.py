"""Conservative, source-linked readings. No diagnosis or inferred units."""
import re
import hashlib
from datetime import date
from sqlalchemy import select
from app.models import SourceArtifact,ExtractionProposal

LABELS={"blood_pressure":"Blood pressure","fasting_glucose":"Fasting glucose","postmeal_glucose":"Post-meal glucose","random_glucose":"Random glucose","blood_glucose":"Glucose (type unspecified)","hba1c":"HbA1c"}
NUM=r"(\d{1,3}(?:\.\d{1,2})?)"
UNIT=r"(mg\s*/\s*dl|mmol\s*/\s*l)"
PATTERNS={
 "blood_pressure":r"(?:blood pressure|b\.?p\.?)\s*[:=]?\s*(\d{2,3})\s*/\s*(\d{2,3})\s*(mm\s*hg)\b",
 "fasting_glucose":r"(?:fasting(?: blood)? (?:glucose|sugar)|fbs|fbg)\s*[:=]?\s*"+NUM+r"\s*"+UNIT+r"\b",
 "postmeal_glucose":r"(?:post[- ]?(?:meal|prandial)(?: blood)? (?:glucose|sugar)|ppbs|ppbg)\s*[:=]?\s*"+NUM+r"\s*"+UNIT+r"\b",
 "random_glucose":r"(?:random(?: blood)? (?:glucose|sugar)|rbs|rbg)\s*[:=]?\s*"+NUM+r"\s*"+UNIT+r"\b",
 "blood_glucose":r"^(?:blood glucose|glucose|blood sugar)\s*[:=]?\s*"+NUM+r"\s*"+UNIT+r"\b",
 "hba1c":r"(?:hba1c|hb a1c|glycated h(?:ae|e)moglobin)\s*[:=]?\s*"+NUM+r"\s*(%)",
}

def extract(blocks):
    found={}
    for block in blocks:
        for line in str(block.get('text','')).splitlines():
            for key,pattern in PATTERNS.items():
                for m in re.finditer(pattern,line,re.I):
                    parts=m.groups()
                    if key=='blood_pressure':value=parts[0]+'/'+parts[1]+' mmHg'
                    else:
                        unit=parts[1].replace(' ','').lower();unit={'mg/dl':'mg/dL','mmol/l':'mmol/L','%':'%'}[unit]
                        value=parts[0]+' '+unit
                    found.setdefault(key,[]).append((value,line[:300],block.get('id')))
    # Conflicting measurements in one report are left for a human, never chosen arbitrarily.
    return {key:rows[0] for key,rows in found.items() if len({r[0] for r in rows})==1}

def report_date_from_text(blocks):
    values=set()
    for block in blocks:
        for match in re.finditer(r"(?:document|report) date\s*[:=]?\s*(\d{4}-\d{2}-\d{2})\b",str(block.get('text','')),re.I):
            try: values.add(date.fromisoformat(match.group(1)))
            except ValueError: pass
    return next(iter(values)) if len(values)==1 else None

def valid_value(key,value):
    if key not in LABELS or not value:return False
    return bool(extract([{'text':LABELS[key].replace(' (type unspecified)','')+': '+value}]).get(key))

def latest(db,patient_id,clinic_id):
    rows=db.execute(select(SourceArtifact,ExtractionProposal).join(ExtractionProposal,ExtractionProposal.artifact_id==SourceArtifact.id)
        .where(SourceArtifact.patient_id==patient_id,SourceArtifact.clinic_id==clinic_id,
               ExtractionProposal.patient_id==patient_id,ExtractionProposal.clinic_id==clinic_id,
               SourceArtifact.deleted_at.is_(None),SourceArtifact.source_type.in_(['LAB_REPORT','PRESCRIPTION','OTHER']))).all()
    readings={};ranks={};processing=False
    for artifact,proposal in rows:
        processing=processing or proposal.status=='EXTRACTION_PENDING'
        if proposal.status in ('REJECTED','EXTRACTION_PENDING','EXTRACTION_FAILED'):continue
        fields={f.name:f for f in proposal.fields}
        doc=fields.get('document_date');rawdate=(doc.value if doc and doc.status=='APPROVED' else doc.proposed_value if doc and doc.status!='REJECTED' else None)
        try: report_date=date.fromisoformat(rawdate) if rawdate else None
        except ValueError:report_date=None
        if report_date is None and not (doc and doc.status=="REJECTED"):
            report_date=report_date_from_text(proposal.blocks or [])
        # A future report date cannot establish the latest clinical measurement.
        if report_date and report_date>artifact.created_at.date():report_date=None
        rank=(report_date or date.min,artifact.created_at,str(artifact.id))
        parsed=extract(proposal.blocks or [])
        for key in LABELS:
            field=fields.get(key)
            if field and field.status=='REJECTED':continue
            value=field.value if field and field.status=='APPROVED' else field.proposed_value if field else parsed.get(key,(None,))[0]
            if not valid_value(key,value):continue
            if key not in ranks or rank>ranks[key]:
                ranks[key]=rank
                readings[key]={'key':key,'label':LABELS[key],'value':value,'report_date':str(report_date) if report_date else None,
                    'date_reviewed':bool(doc and doc.status=='APPROVED'),'uploaded_at':artifact.created_at.isoformat(),
                    'clinic_reviewed':bool(field and field.status=='APPROVED'),'filename':artifact.filename,
                    'artifact_id':str(artifact.id),'source_text':field.extracted_value if field else parsed[key][1]}
    revision=hashlib.sha256('|'.join(sorted(str(a.id)+':'+p.status for a,p in rows)).encode()).hexdigest()
    return {'readings':list(readings.values()),'processing':processing,'source_revision':revision}
