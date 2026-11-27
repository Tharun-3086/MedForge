from app.evaluation.medical import evaluate


def test_benchmark_counts_critical_unit_error_as_false_acceptance():
    truth=[{'id':'synthetic','text':'Glucose 75 mg/dL','fields':{'fasting_glucose':{'value':'75','unit':'mg/dL','date':'2026-11-12'}}}]
    predicted=[{'id':'synthetic','text':'Glucose 75 ng/dL','fields':{'fasting_glucose':{'value':'75.0','unit':'ng/dL','date':'2026-11-12','accepted':True,'needs_review':False}}}]
    r=evaluate(truth,predicted)
    assert r['metrics']['numerical_value_accuracy']==1
    assert r['metrics']['unit_accuracy']==0
    assert r['metrics']['false_acceptance_among_incorrect']==1
    assert r['metrics']['character_error_rate']>0
    assert r['metrics']['word_error_rate']>0
    assert evaluate([],[])['metrics']['unit_accuracy'] is None


def test_benchmark_missing_and_spurious_fields_are_counted():
    truth=[{'id':'synthetic','fields':{'hba1c':{'value':'7','unit':'%','date':'2026-11-12'}}}]
    pred=[{'id':'synthetic','fields':{'weight':{'value':'70','unit':'kg','date':'2026-11-12','needs_review':True}}}]
    r=evaluate(truth,pred)
    assert r['counts']['expected_fields']==1 and r['counts']['parameter_union']==2
    assert r['metrics']['parameter_accuracy_over_union']==0
    assert r['metrics']['manual_verification_fraction']==1
