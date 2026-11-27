"use client";
import {ReadingHistory} from "@/components/reading-history";
import {useApi,usePoll} from "@/lib/api";
import type {Lang} from "@/lib/i18n";
const copy={en:{title:"Latest health readings",empty:"Upload a report with clearly labelled readings and units to see your latest values.",warning:"OCR can misread numbers. Check the original and ask your clinic to confirm. Do not change treatment based on automatic readings.",reviewed:"Clinic-reviewed",unverified:"Unverified OCR",date:"Report date",uploaded:"Report date unavailable · uploaded",source:"View source report",refresh:"Refresh readings",processing:"Reading your new report… Previous readings remain visible."},hi:{title:"नवीनतम स्वास्थ्य रीडिंग",empty:"नई रीडिंग के लिए स्पष्ट नाम और इकाइयों वाली रिपोर्ट अपलोड करें।",warning:"OCR में अंकों की गलती हो सकती है। मूल रिपोर्ट जाँचें और क्लिनिक से पुष्टि कराएँ। स्वचालित रीडिंग से इलाज न बदलें।",reviewed:"क्लिनिक द्वारा जाँचा गया",unverified:"अपुष्ट OCR",date:"रिपोर्ट की तारीख",uploaded:"रिपोर्ट की तारीख उपलब्ध नहीं · अपलोड",source:"मूल रिपोर्ट देखें",refresh:"रीडिंग फिर देखें",processing:"नई रिपोर्ट पढ़ रहे हैं… पिछली रीडिंग दिखती रहेंगी।"},te:{title:"తాజా ఆరోగ్య రీడింగులు",empty:"తాజా విలువల కోసం స్పష్టమైన పేర్లు, యూనిట్లు ఉన్న నివేదికను అప్లోడ్ చేయండి.",warning:"OCR అంకెలను తప్పుగా చదవవచ్చు. అసలు నివేదికను చూసి క్లినిక్ నిర్ధారణ పొందండి. స్వయంచాలక రీడింగుల ఆధారంగా చికిత్స మార్చవద్దు.",reviewed:"క్లినిక్ నిర్ధారించింది",unverified:"నిర్ధారించని OCR",date:"నివేదిక తేదీ",uploaded:"నివేదిక తేదీ లేదు · అప్లోడ్",source:"అసలు నివేదిక చూడండి",refresh:"రీడింగులు మళ్లీ చూడండి",processing:"కొత్త నివేదిక చదువుతోంది… పాత రీడింగులు కనిపిస్తాయి."}};
export type Reading={key:string;label:string;value:string;report_date:string|null;date_reviewed:boolean;uploaded_at:string;clinic_reviewed:boolean;filename:string;artifact_id:string;source_text:string;proposal_id:string};
const summaryCopy={
 en:{title:"My health numbers",subtitle:"Latest values from your reports",empty:"No reading yet",upload:"Upload a health report",reportOnly:"Report-based readings; this is not a live glucose monitor.",pending:"Some new readings need clinic verification. Previous usable readings remain visible.",details:"Report details",hba1c:"HbA1c",glucose:"Blood glucose",bp:"Blood pressure",fasting_glucose:"Fasting",postmeal_glucose:"Post-meal",random_glucose:"Random",blood_glucose:"Type unspecified"},
 hi:{title:"मेरे स्वास्थ्य आँकड़े",subtitle:"आपकी रिपोर्ट की नवीनतम रीडिंग",empty:"अभी कोई रीडिंग नहीं",upload:"स्वास्थ्य रिपोर्ट अपलोड करें",reportOnly:"ये रिपोर्ट की रीडिंग हैं; लाइव ग्लूकोज़ निगरानी नहीं।",pending:"कुछ नई रीडिंग की क्लिनिक जाँच आवश्यक है। पिछली रीडिंग दिखती रहेंगी।",details:"रिपोर्ट का विवरण",hba1c:"HbA1c",glucose:"रक्त ग्लूकोज़",bp:"रक्तचाप",fasting_glucose:"खाली पेट",postmeal_glucose:"खाने के बाद",random_glucose:"रैंडम",blood_glucose:"प्रकार उपलब्ध नहीं"},
 te:{title:"నా ఆరోగ్య గణాంకాలు",subtitle:"మీ నివేదికల్లోని తాజా విలువలు",empty:"ఇంకా రీడింగ్ లేదు",upload:"ఆరోగ్య నివేదిక అప్లోడ్ చేయండి",reportOnly:"ఇవి నివేదికలోని రీడింగులు; ప్రత్యక్ష గ్లూకోజ్ మానిటర్ కాదు.",pending:"కొన్ని కొత్త రీడింగులకు క్లినిక్ నిర్ధారణ అవసరం. పాత రీడింగులు కనిపిస్తాయి.",details:"నివేదిక వివరాలు",hba1c:"HbA1c",glucose:"రక్తంలో గ్లూకోజ్",bp:"రక్తపోటు",fasting_glucose:"పరగడుపున",postmeal_glucose:"భోజనం తర్వాత",random_glucose:"రాండమ్",blood_glucose:"రకం తెలియదు"}
};
const extraCopy={en:{kidney:"Kidney results",lipids:"Cholesterol & triglycerides",weight:"Weight"},hi:{kidney:"किडनी की जाँच",lipids:"कोलेस्ट्रॉल और ट्राइग्लिसराइड्स",weight:"वज़न"},te:{kidney:"మూత్రపిండాల ఫలితాలు",lipids:"కొలెస్ట్రాల్ & ట్రైగ్లిసరైడ్లు",weight:"బరువు"}};
const groups=[{key:"hba1c",keys:["hba1c"]},{key:"glucose",keys:["fasting_glucose","postmeal_glucose","random_glucose","blood_glucose"]},{key:"bp",keys:["blood_pressure"]},{key:"kidney",keys:["creatinine","egfr","uacr"]},{key:"lipids",keys:["total_cholesterol","ldl","hdl","triglycerides"]},{key:"weight",keys:["weight"]}] as const;
export function HealthReadings({lang,onUpload,endpoint="/v1/p/health-readings",staff=false}:{lang:Lang;onUpload?:()=>void;endpoint?:string;staff?:boolean}) {
 const data=useApi<{readings:Reading[];processing:boolean;pending_verification_count?:number;history:Reading[]}>(endpoint);
 const c=copy[lang],s={...summaryCopy[lang],...extraCopy[lang]};
 usePoll(true,data.reload,15000);
 return <section className="card stack health-summary" aria-labelledby="latest-readings-title">
  <div className="spread"><div><h2 id="latest-readings-title">{s.title}</h2><p className="small muted">{s.subtitle}</p></div><button className="pt-link" onClick={()=>void data.reload()} disabled={data.loading}>{c.refresh}</button></div>
  {data.error?<p role="alert">{data.error.message}</p>:!data.data?<p role="status">…</p>:<>
   {(data.data.pending_verification_count??0)>0?<p role="status" className="notice">{s.pending}</p>:null}
   {data.data.processing?<p role="status">{c.processing}</p>:null}
   <div className="health-readings">{groups.map(group=>{
    const readings=group.keys.flatMap(key=>data.data!.readings.filter(r=>r.key===key));
    return <article className={`health-reading health-reading--${group.key} stack`} key={group.key} aria-label={s[group.key]}>
     <h3>{s[group.key]}</h3>
     {readings.length?readings.map(v=><div className="health-measurement stack" key={v.key}>
      {group.keys.length>1?<strong className="small">{group.key==="glucose"?s[v.key as "fasting_glucose"|"postmeal_glucose"|"random_glucose"|"blood_glucose"]:v.label}</strong>:null}
      <span className="health-reading-value">{v.value}</span>
      <span className={`health-verification ${v.clinic_reviewed?"health-verification--reviewed":""}`}>{v.clinic_reviewed?c.reviewed:c.unverified}</span>
      <span className="small muted">{v.report_date?`${c.date}: ${v.report_date}${v.date_reviewed?'':' · '+c.unverified}`:`${c.uploaded}: ${new Date(v.uploaded_at).toLocaleDateString(lang)}`}</span>
      <details><summary>{s.details}</summary><p className="small muted">{v.filename}</p><p className="small">{v.source_text}</p><a className="pt-link" href={staff?`/reports/${v.proposal_id}`:`/api/v1/p/documents/${v.artifact_id}/file`} target="_blank" rel="noreferrer">{staff?"Review source report":c.source}</a></details>
     </div>):<><span className="health-reading-value" aria-hidden="true">—</span><p className="small muted">{s.empty}</p></>}
    </article>;
   })}</div>
   {data.data.readings.length===0?<p className="small">{c.empty}</p>:null}
   <ReadingHistory history={data.data.history??[]} lang={lang} staff={staff} />
  </>}
  {onUpload?<button className="btn" onClick={onUpload}>{s.upload}</button>:null}
  <p className="small muted">{s.reportOnly} {c.warning}</p>
 </section>;
}
