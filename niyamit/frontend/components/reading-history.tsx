"use client";
import {measurement,verifiedPoints} from "@/lib/reading-trends";
import {useState} from "react";
import type {Lang} from "@/lib/i18n";
import type {Reading} from "@/components/patient/health-readings";

const copy={en:{title:"History & trends",metric:"Measurement",unit:"Unit",empty:"Upload reports to build your history.",policy:"Charts use clinic-confirmed values and report dates only. Different units stay separate. Conflicting results on the same date are excluded from the chart. A change is not a diagnosis.",need:"At least two confirmed report dates with the same unit are needed for a trend.",reviewed:"Clinic-reviewed",unverified:"Unverified",undated:"Report date unavailable",dateUnverified:"Date unverified",source:"Source report"},hi:{title:"इतिहास और रुझान",metric:"माप",unit:"इकाई",empty:"इतिहास देखने के लिए रिपोर्ट अपलोड करें।",policy:"चार्ट में केवल क्लिनिक द्वारा जाँचे गए मान और तारीखें हैं। अलग इकाइयाँ अलग रहती हैं। एक तारीख के विरोधी परिणाम चार्ट में नहीं दिखते। बदलाव निदान नहीं है।",need:"रुझान के लिए समान इकाई में कम से कम दो पुष्ट रिपोर्ट तारीखें चाहिए।",reviewed:"क्लिनिक द्वारा जाँचा गया",unverified:"अपुष्ट",undated:"रिपोर्ट की तारीख उपलब्ध नहीं",dateUnverified:"तारीख अपुष्ट",source:"मूल रिपोर्ट"},te:{title:"చరిత్ర & మార్పులు",metric:"కొలత",unit:"యూనిట్",empty:"చరిత్ర కోసం నివేదికలు అప్లోడ్ చేయండి.",policy:"చార్ట్‌లో క్లినిక్ నిర్ధారించిన విలువలు, తేదీలు మాత్రమే ఉంటాయి. వేర్వేరు యూనిట్లు వేరుగా ఉంటాయి. ఒకే తేదీలో విరుద్ధ ఫలితాలు చార్ట్‌లో చూపబడవు. మార్పు రోగ నిర్ధారణ కాదు.",need:"మార్పు చూపడానికి ఒకే యూనిట్‌తో కనీసం రెండు నిర్ధారించిన నివేదిక తేదీలు అవసరం.",reviewed:"క్లినిక్ నిర్ధారించింది",unverified:"నిర్ధారించలేదు",undated:"నివేదిక తేదీ లేదు",dateUnverified:"తేదీ నిర్ధారించలేదు",source:"అసలు నివేదిక"}};

export function ReadingHistory({history,lang,staff}:{history:Reading[];lang:Lang;staff:boolean}){
 const c=copy[lang];
 const [selected,setSelected]=useState("");
 const [chosenUnit,setChosenUnit]=useState("");
 const keys=Array.from(new Set(history.map(r=>r.key)));
 const key=keys.includes(selected)?selected:keys.includes("creatinine")?"creatinine":keys[0];
 const rows=history.filter(r=>r.key===key);
 const units=Array.from(new Set(rows.flatMap(r=>{const m=measurement(r.value);return m?[m.unit]:[]})));
 const unit=units.includes(chosenUnit)?chosenUnit:units[0];
 const points=verifiedPoints(history,key,unit);
 const values=points.flatMap(p=>p.values),low=Math.min(...values),high=Math.max(...values);
 const x=(i:number)=>40+280*(Date.parse(points[i].date)-Date.parse(points[0].date))/(Date.parse(points[points.length-1].date)-Date.parse(points[0].date)||1);
 const y=(n:number)=>120-90*(n-low)/(high-low||1);
 return <section className="reading-history stack" aria-label={c.title}>
  <h3>{c.title}</h3><p className="small muted">{c.policy}</p>
  {!history.length?<p>{c.empty}</p>:<>
   <label className="field"><span>{c.metric}</span><select value={key} onChange={e=>{setSelected(e.target.value);setChosenUnit("");}}>{keys.map(k=><option value={k} key={k}>{history.find(r=>r.key===k)!.label}</option>)}</select></label>
   {units.length>0?<label className="field"><span>{c.unit}</span><select value={unit} onChange={e=>setChosenUnit(e.target.value)}>{units.map(u=><option key={u}>{u}</option>)}</select></label>:null}
   {points.length>=2?<figure className="reading-trend"><figcaption>{rows[0]?.label} · {unit}{key==="blood_pressure"?" · Systolic / diastolic":""}</figcaption>
    <svg viewBox="0 0 360 160" role="img" aria-label={`${rows[0]?.label}: ${points.map(p=>p.date+': '+p.values.join('/')).join('; ')} ${unit}`}>
     <text x="2" y="25" fontSize="10">{high}</text><text x="2" y="125" fontSize="10">{low}</text>
     <path d="M35 20V125H330" fill="none" stroke="#afbdc5" />
     {points[0].values.map((_,series)=><g key={series} stroke={series?"#8b529b":"#1d7080"} fill={series?"#8b529b":"#1d7080"}>
      <polyline points={points.map((p,i)=>`${x(i)},${y(p.values[series])}`).join(' ')} fill="none" strokeWidth="2" />
      {points.map((p,i)=><circle key={p.date} cx={x(i)} cy={y(p.values[series])} r="3"><title>{p.date}: {p.values[series]} {unit}</title></circle>)}
     </g>)}
     <text x="35" y="149" fontSize="10">{points[0].date}</text><text x="330" y="149" textAnchor="end" fontSize="10">{points[points.length-1].date}</text>
    </svg>
   </figure>:<p className="notice">{c.need}</p>}
   <ol className="reading-history-list">{rows.map(r=><li className="health-reading stack" key={r.artifact_id+':'+r.key}>
    <strong>{r.value}</strong><span>{r.report_date??c.undated}{r.report_time?' · '+r.report_time:''}{r.report_date&&!r.date_reviewed?' · '+c.dateUnverified:''}</span>
    <span className="small">{r.clinic_reviewed?c.reviewed:c.unverified}</span>
    <span className="small muted">{r.filename}</span>
    <a href={staff?`/reports/${r.proposal_id}`:`/api/v1/p/documents/${r.artifact_id}/file`} target="_blank" rel="noreferrer">{c.source}</a>
   </li>)}</ol>
  </>}
 </section>;
}
