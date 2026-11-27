"""Validate and reconcile medical proposals, never silently repair clinical values."""
import re
from app.ai.medical_contracts import MEDICAL_SCHEMA_VERSION, MedicalMeasurement
from app.ai.dates import parse_explicit_date
from app.ai.providers.ocr_review import evidence_for
from app.services.health_readings import LABELS, UNITS, valid_value


def _text(value):
    return re.sub(r"\s+", " ", str(value).replace("|"," ")).strip().casefold()


def validate_measurements(candidates, blocks, today, provider):
    from app.ai.pipeline import FieldProposal
    result=[]
    known={b['id']:b for b in blocks}
    for candidate in candidates:
        unsupported=candidate.parameter not in LABELS
        ids=[i for i in candidate.block_ids if i in known]
        # Never accept a partial overlap of a short block as proof of a longer quote.
        if not ids:
            ids=[b['id'] for b in blocks if _text(candidate.quote) in _text(b.get('text',''))]
        if not ids and len({b.get('page') for b in blocks})==1:
            # The only page is known, but a missing exact quote stays flagged.
            ids=[b['id'] for b in blocks]
        selected=[known[i] for i in ids]
        source=_text(' '.join(b.get('text','') for b in selected))
        quote=_text(candidate.quote)
        evidence,reasons,score=evidence_for(blocks,ids)
        reasons.append('AI_MEASUREMENT_REQUIRES_REVIEW')
        if unsupported:reasons.append('UNSUPPORTED_MEDICAL_PARAMETER')
        if not quote or not selected or quote not in source:
            reasons.append('MEDICAL_SOURCE_NOT_GROUNDED')
        unit_key=re.sub(r"\s+", "",candidate.unit).lower()
        unit=UNITS.get(unit_key,candidate.unit.strip())
        if unit_key=='mmhg':unit='mmHg'
        value=candidate.value.strip()+' '+unit
        if not valid_value(candidate.parameter,value):
            reasons.append('UNSUPPORTED_MEASUREMENT_UNIT')
        # A number occurring somewhere on a page is insufficient. It must be
        # attached to its unit in the quoted result, not picked from a range.
        value_pattern=re.escape(candidate.value.strip()).replace(r'\ ',r'\s*')
        unit_pattern=re.escape(candidate.unit.strip()).replace(r'\ ',r'\s*')
        if not candidate.unit or not re.search(r'(?<![\d.])'+value_pattern+r'[\s|:=]*'+unit_pattern+r'(?![a-zA-Z])',candidate.quote,re.I):
            reasons.append('MEDICAL_VALUE_UNIT_NOT_GROUNDED')
        if re.search(r'(?i)\b(?:reference|normal range|target|goal)\s*[:=]?\s*$',candidate.quote.split(candidate.value,1)[0]):
            reasons.append('POSSIBLE_REFERENCE_VALUE')
        raw_range=candidate.reference_range.strip()
        reference=raw_range if raw_range and _text(raw_range) in source else None
        if raw_range and not reference:reasons.append('REFERENCE_RANGE_NOT_GROUNDED')
        raw_date=candidate.test_date.strip()
        page_ids={b.get('page') for b in selected}
        page_text=_text(' '.join(b.get('text','') for b in blocks if b.get('page') in page_ids))
        parsed_date=parse_explicit_date(raw_date,today,allow_missing_year=False) if raw_date and _text(raw_date) in page_text else None
        if raw_date and not parsed_date:reasons.append('MEASUREMENT_DATE_NOT_GROUNDED')
        if parsed_date and parsed_date>today:
            reasons.append('FUTURE_MEASUREMENT_DATE');parsed_date=None
        confidence=min(candidate.confidence,score) if candidate.confidence is not None and score is not None else score
        evidence.update(quote=candidate.quote,extraction_schema=MEDICAL_SCHEMA_VERSION,
            extraction_method='structured-ai',extraction_provider=provider,
            parameter=candidate.parameter,parameter_as_written=candidate.raw_parameter,raw_value=candidate.value,raw_unit=candidate.unit,unit=unit,
            reference_range=reference,reference_range_as_written=raw_range or None,
            test_date=parsed_date.isoformat() if parsed_date else None,test_date_as_written=raw_date or None,
            model_confidence=candidate.confidence)
        result.append(FieldProposal('unmapped_measurement' if unsupported else candidate.parameter,value,candidate.quote[:300],'NEEDS_REVIEW',confidence,evidence,sorted(set(reasons))))
    return result


def reconcile_measurements(local, model):
    """Keep disagreements as separate candidates; agreement is never approval."""
    result=list(local)
    for proposed in model:
        same=next((f for f in result if f.name==proposed.name and f.value==proposed.value),None)
        if same:
            sources=list(same.evidence.get('extraction_sources',[]))
            sources.append(proposed.evidence)
            same.evidence={**same.evidence,**{k:v for k,v in proposed.evidence.items() if k not in ('quote','bboxes','block_ids','engines','alternatives')},'extraction_sources':sources}
            same.review_reasons=sorted(set(same.review_reasons)|set(proposed.review_reasons))
            same.status='NEEDS_REVIEW'
        else:result.append(proposed)
    for name in {f.name for f in result}:
        group=[f for f in result if f.name==name]
        if len({f.value for f in group})>1:
            for f in group:
                f.status='NEEDS_REVIEW'
                f.review_reasons=sorted(set(f.review_reasons)|{'CONFLICTING_MEASUREMENTS'})
    return result
