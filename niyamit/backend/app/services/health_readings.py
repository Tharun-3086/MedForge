"""Source-linked report measurements, shared by patients and authorised clinic staff."""
import re
import hashlib
from datetime import date, time
from sqlalchemy import select
from app.config import settings
from app.models import SourceArtifact, ExtractionProposal

LABELS={"blood_pressure":"Blood pressure","fasting_glucose":"Fasting glucose","postmeal_glucose":"Post-meal glucose","random_glucose":"Random glucose","blood_glucose":"Glucose (type unspecified)","hba1c":"HbA1c","creatinine":"Serum creatinine","egfr":"eGFR","uacr":"Urine albumin/creatinine ratio","total_cholesterol":"Total cholesterol","ldl":"LDL cholesterol","hdl":"HDL cholesterol","triglycerides":"Triglycerides","weight":"Weight"}
NUM=r"(\d{1,4}(?:\.\d{1,3})?)"
UNIT=r"(mg\s*/\s*dl|mmol\s*/\s*l)"
PATTERNS={
 "blood_pressure":r"(?:blood pressure|b\.?p\.?)\s*[:=]?\s*(\d{2,3})\s*/\s*(\d{2,3})\s*(mm\s*hg)\b",
 "fasting_glucose":r"(?:fasting(?:\s+blood)?\s+(?:glucose|sugar)|fbs|fbg)\s*[:=]?\s*"+NUM+r"\s*"+r"(mg\s*/\s*dl|ng\s*/\s*dl|mmol\s*/\s*l)(?![a-zA-Z])",
 "postmeal_glucose":r"(?:post[- ]?(?:meal|prandial)(?: blood)? (?:glucose|sugar)|ppbs|ppbg)\s*[:=]?\s*"+NUM+r"\s*"+UNIT+r"\b",
 "random_glucose":r"(?:random(?: blood)? (?:glucose|sugar)|rbs|rbg)\s*[:=]?\s*"+NUM+r"\s*"+UNIT+r"\b",
 "blood_glucose":r"^(?:blood glucose|glucose|blood sugar)\s*[:=]?\s*"+NUM+r"\s*"+UNIT+r"\b",
 "hba1c":r"(?:hba1c|hb a1c|glycated h(?:ae|e)moglobin)\s*[:=]?\s*"+NUM+r"\s*(%)",
 "creatinine":r"^(?:(?:serum|blood|plasma)\s+|s\.\s*)creatinine\s*[:=]?\s*"+NUM+r"\s*(mg\s*/\s*dl|[uµμ]mol\s*/\s*l)\b",
 "egfr":r"^(?:egfr|estimated glomerular filtration rate)\s*[:=]?\s*([<>]=?\s*\d{1,4}(?:\.\d+)?|\d{1,4}(?:\.\d+)?)\s*(ml\s*/\s*min\s*/\s*1\.73\s*m(?:2|²|\^2))",
 "uacr":r"^(?:uacr|urine albumin\s*[/\-]\s*(?:to[\- ]*)?creatinine(?: ratio)?|urine albumin.to.creatinine ratio)\s*[:=]?\s*"+NUM+r"\s*(mg\s*/\s*g|mg\s*/\s*mmol)\b",
 "total_cholesterol":r"^(?:total cholesterol|cholesterol total)\s*[:=]?\s*"+NUM+r"\s*"+UNIT+r"\b",
 "ldl":r"^(?:ldl(?:[ -]cholesterol)?|cholesterol ldl)\s*[:=]?\s*"+NUM+r"\s*"+UNIT+r"\b",
 "hdl":r"^(?:hdl(?:[ -]cholesterol)?|cholesterol hdl)\s*[:=]?\s*"+NUM+r"\s*"+UNIT+r"\b",
 "triglycerides":r"^(?:triglycerides|triglyceride|tg)\s*[:=]?\s*"+NUM+r"\s*"+UNIT+r"\b",
 "weight":r"^(?:body weight|weight)\s*[:=]?\s*"+NUM+r"\s*(kg|lbs?|kilograms?)\b",
}
UNITS={'ng/dl':'ng/dL','mg/dl':'mg/dL','mmol/l':'mmol/L','%':'%','umol/l':'µmol/L','µmol/l':'µmol/L','μmol/l':'µmol/L','mg/g':'mg/g','mg/mmol':'mg/mmol','kg':'kg','kilogram':'kg','kilograms':'kg','lb':'lb','lbs':'lb','ml/min/1.73m2':'mL/min/1.73m²','ml/min/1.73m²':'mL/min/1.73m²','ml/min/1.73m^2':'mL/min/1.73m²'}

def measurement_blocks(blocks):
    """Reassemble a narrowly recognised wrapped table label using page geometry.

    Keep the original blocks and their uncertainty. Never join arbitrary rows,
    borrow a unit from a reference range, or infer a missing numeric result.
    """
    result=list(blocks)
    ids={b.get('id') for b in blocks}
    for block in blocks:
        text=str(block.get('text',''))
        if not re.match(r'^\s*FASTING\s+BLOOD\s*\d',text,re.I):continue
        box=block.get('bbox')
        if not box or not block.get('id'):continue
        height=box[3]-box[1]
        tails=[b for b in blocks if b.get('page')==block.get('page')
               and re.fullmatch(r'\s*(?:SUGAR|GLUCOSE)\s*',str(b.get('text','')),re.I)
               and b.get('bbox') and height>0
               and abs(b['bbox'][0]-box[0])<=height
               and box[1]+.4*height<=b['bbox'][1]<=box[3]+.75*height
               and b['bbox'][2]<=box[0]+.55*(box[2]-box[0])]
        if len(tails)!=1:continue
        tail=tails[0]; derived_id=block['id']+'-wrapped-label'
        if derived_id in ids:continue
        joined=re.sub(r'^(\s*FASTING\s+BLOOD)\s*',lambda m:m[1]+' '+tail['text'].strip()+' ',text,flags=re.I)
        scores=[b.get('ocr_conf') for b in (block,tail) if b.get('ocr_conf') is not None]
        result.append(dict(block,id=derived_id,text=joined,
            bbox=[min(box[0],tail['bbox'][0]),box[1],max(box[2],tail['bbox'][2]),max(box[3],tail['bbox'][3])],
            source_block_ids=[block['id'],tail['id']],
            source_texts=[text,tail['text']], reconstruction='wrapped table label',
            ocr_conf=min(scores) if scores else None,
            review_reasons=sorted(set(block.get('review_reasons',[]))|set(tail.get('review_reasons',[])))))
    return result


def candidates(blocks):
    found={}
    for block in measurement_blocks(blocks):
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


def normalise_report_time(value):
    match=re.fullmatch(r'\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)?\s*',value,re.I)
    if not match:return None
    hour,minute,second=int(match[1]),int(match[2]),int(match[3] or 0)
    if match[4]:
        if not 1<=hour<=12:return None
        hour=hour%12+(12 if match[4].upper()=='PM' else 0)
    try:return time(hour,minute,second).isoformat()
    except ValueError:return None


def report_time_candidates(blocks):
    """Only labelled collection/report clocks; never upload or approval times."""
    groups=[r'\b(?:sample\s+)?collection\s+time\b|\b(?:sample\s+)?collected\s+(?:on|at)\b',
            r'\breport\s+time\b']
    for label in groups:
        rows=[]
        for block in blocks:
            for line in str(block.get('text','')).splitlines():
                start=re.search(label,line,re.I)
                if not start:continue
                tail=line[start.end():]
                # A merged row may also contain received/approved timestamps.
                tail=re.split(r'\b(?:received|approved|uploaded|reported)\b',tail,flags=re.I)[0]
                for m in re.finditer(r'(?<![\d:])\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?(?![\d:])',tail,re.I):
                    value=normalise_report_time(m[0])
                    if value:rows.append((value,line[:300],block.get('id')))
        if rows:return rows
    return []

def valid_value(key,value):
    if key not in LABELS or not value or re.search(r"\bng\s*/\s*dl\b",value,re.I):return False
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
        times=[f for f in proposal.fields if f.name=='document_time' and f.status!='REJECTED']
        approved_times={normalise_report_time(f.value or '') for f in times if f.status=='APPROVED'}-{None}
        report_time=next(iter(approved_times)) if len(approved_times)==1 and not any(f.status=='NEEDS_REVIEW' for f in times) else None
        rank=(report_date or date.min,report_time or '',artifact.created_at,str(artifact.id))
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
                    'date_reviewed':bool(doc and doc.status=='APPROVED'),'report_time':report_time,'uploaded_at':artifact.created_at.isoformat(),
                    'clinic_reviewed':bool(field and field.status=='APPROVED'),'filename':artifact.filename,
                    'artifact_id':str(artifact.id),'source_text':field.extracted_value if field else parsed[key][1], 'proposal_id':str(proposal.id),
                    'source_metadata':{k:v for k,v in (field.evidence or {}).items() if k in ('page','bboxes','engines','extraction_method','extraction_provider','extraction_schema','unit','reference_range','test_date')} if field else {}}
            history.append(record)
            if key not in ranks or rank>ranks[key]:ranks[key]=rank;readings[key]=record
    history.sort(key=lambda r:(r['report_date'] or '',r['report_time'] or '',r['uploaded_at'],r['artifact_id']),reverse=True)
    revision=hashlib.sha256(repr((sorted((str(a.id),p.status) for a,p in rows),history,sorted(pending))).encode()).hexdigest()
    return {'readings':list(readings.values()),'processing':processing,'pending_verification_count':len(pending),'source_revision':revision,'history':history}
