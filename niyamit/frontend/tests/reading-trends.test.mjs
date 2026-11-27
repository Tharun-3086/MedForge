import test from 'node:test';
import assert from 'node:assert/strict';
import {measurement,verifiedPoints} from '../lib/reading-trends.ts';
const row=(date,value,extra={})=>({key:'creatinine',value,report_date:date,clinic_reviewed:true,date_reviewed:true,...extra});
test('trends exclude uncertainty, unknown dates, inequalities and incompatible units',()=>{
 const points=verifiedPoints([
  row('2026-02-01','1.2 mg/dL'),row('2026-01-01','1.1 mg/dL'),
  row('2026-03-01','90 µmol/L'),row('2026-04-01','9 mg/dL',{clinic_reviewed:false}),
  row('2026-05-01','8 mg/dL',{date_reviewed:false}),row(null,'7 mg/dL'),row('2026-06-01','>6 mg/dL')
 ],'creatinine','mg/dL');
 assert.deepEqual(points.map(p=>p.values[0]),[1.1,1.2]);
 assert.equal(measurement('>90 mL/min/1.73m²'),null);
});
test('same-day conflicts are not silently averaged or selected',()=>{
 const rows=[row('2026-01-01','1.1 mg/dL'),row('2026-01-01','1.2 mg/dL'),row('2026-02-01','1.3 mg/dL'),row('2026-02-01','1.3 mg/dL')];
 assert.deepEqual(verifiedPoints(rows,'creatinine','mg/dL').map(p=>p.date),['2026-02-01']);
 assert.deepEqual(measurement('120/80 mmHg'),{values:[120,80],unit:'mmHg'});
});
