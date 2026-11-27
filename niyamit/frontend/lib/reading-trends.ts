export type TrendReading={key:string;value:string;clinic_reviewed:boolean;date_reviewed:boolean;report_date:string|null};

export function measurement(value:string){
 const m=value.match(/^(\d+(?:\.\d+)?)(?:\/(\d+(?:\.\d+)?))? (.+)$/);
 return m?{values:m[2]?[Number(m[1]),Number(m[2])]:[Number(m[1])],unit:m[3]}:null;
}

export function verifiedPoints(history:TrendReading[],key:string,unit:string){
 const rows=history.filter(r=>r.key===key&&r.clinic_reviewed&&r.date_reviewed&&r.report_date&&measurement(r.value)?.unit===unit);
 const dates=Array.from(new Set(rows.map(r=>r.report_date!))).sort();
 return dates.flatMap(date=>{
  const same=rows.filter(r=>r.report_date===date);
  return new Set(same.map(r=>r.value)).size===1?[{date,...measurement(same[0].value)!}]:[];
 });
}
