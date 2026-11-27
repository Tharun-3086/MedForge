"""Offline labelled-corpus metrics. This tool does not supply clinical ground truth."""
import json
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation


def distance(a,b):
    previous=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        current=[i]
        for j,y in enumerate(b,1):
            current.append(min(current[-1]+1,previous[j]+1,previous[j-1]+(x!=y)))
        previous=current
    return previous[-1]


def numeric_equal(a,b):
    try:return Decimal(str(a))==Decimal(str(b))
    except InvalidOperation:return str(a)==str(b)


def ratio(n,d):return n/d if d else None


def evaluate(expected,predicted):
    exp={r['id']:r for r in expected};pred={r['id']:r for r in predicted}
    if len(exp)!=len(expected) or len(pred)!=len(predicted):raise ValueError('Duplicate sample IDs')
    c=defaultdict(int)
    for sample_id in exp.keys()|pred.keys():
        e,p=exp.get(sample_id,{}),pred.get(sample_id,{})
        et,pt=' '.join(e.get('text','').split()),' '.join(p.get('text','').split())
        c['character_edits']+=distance(et,pt);c['reference_characters']+=len(et)
        c['word_edits']+=distance(et.split(),pt.split());c['reference_words']+=len(et.split())
        ef,pf=e.get('fields',{}),p.get('fields',{})
        c['expected_fields']+=len(ef);c['parameter_union']+=len(ef.keys()|pf.keys());c['parameter_matches']+=len(ef.keys()&pf.keys())
        for key,field in ef.items():
            actual=pf.get(key,{})
            c['value_matches']+=numeric_equal(field.get('value',''),actual.get('value','__missing__'))
            c['unit_matches']+=field.get('unit')==actual.get('unit','__missing__')
            c['date_matches']+=field.get('date')==actual.get('date','__missing__')
        for key,field in pf.items():
            truth=ef.get(key)
            correct=bool(truth and numeric_equal(truth.get('value',''),field.get('value','')) and truth.get('unit')==field.get('unit') and truth.get('date')==field.get('date'))
            c['predicted_fields']+=1;c['incorrect_predictions']+=not correct
            c['accepted']+=field.get('accepted') is True
            c['false_accepted']+=(not correct and field.get('accepted') is True)
            c['manual_review']+=field.get('needs_review') is True
    return {'samples':len(exp),'counts':dict(c),'metrics':{
        'character_error_rate':ratio(c['character_edits'],c['reference_characters']),
        'word_error_rate':ratio(c['word_edits'],c['reference_words']),
        'parameter_accuracy_over_union':ratio(c['parameter_matches'],c['parameter_union']),
        'numerical_value_accuracy':ratio(c['value_matches'],c['expected_fields']),
        'unit_accuracy':ratio(c['unit_matches'],c['expected_fields']),
        'date_accuracy':ratio(c['date_matches'],c['expected_fields']),
        'false_acceptance_among_incorrect':ratio(c['false_accepted'],c['incorrect_predictions']),
        'incorrect_fraction_of_accepted':ratio(c['false_accepted'],c['accepted']),
        'manual_verification_fraction':ratio(c['manual_review'],c['predicted_fields'])},
        'limitations':'Caller-supplied labels/predictions; no clinical validity is established. Run separately for printed/handwritten/mixed and language cohorts.'}


if __name__=='__main__':
    if len(sys.argv)!=3:raise SystemExit('Usage: python -m app.evaluation.medical expected.json predicted.json')
    from pathlib import Path
    print(json.dumps(evaluate(json.loads(Path(sys.argv[1]).read_text()),json.loads(Path(sys.argv[2]).read_text())),indent=2))
