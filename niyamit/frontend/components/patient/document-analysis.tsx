"use client";
import { useApi, usePoll } from "@/lib/api";
import { t, type Lang } from "@/lib/i18n";
import { fmtDateTime } from "@/lib/format";
type Document = {id:string;filename:string;uploaded_at:string;status:string;automatic_text:string;
  automatic_fields:{label:string;value:string|null;as_written:string|null;review_status:string}[];
  clinic_reviewed_fields:{label:string;value:string|null;reviewed_at:string|null}[];plan_approved:boolean};
const copy = {
  en:{title:"Your document analysis",refresh:"Refresh analysis",original:"View original",automatic:"AI / automatic analysis — unverified",warning:"This reading can contain mistakes. Do not change medicines or treatment based on it. Your clinic checks the information separately.",scope:"The automatic reading shows document text and extracted follow-up details. It does not diagnose conditions or check medicine safety.",text:"Text read from your document",none:"No details have been extracted yet.",clinic:"Clinic-reviewed information",waiting:"Your clinic has not confirmed any fields yet.",approved:"A follow-up plan has been approved. See your care record for the plan.",rejected:"The clinic did not use this document for your plan. Contact them for details.",notconfirmed:"Not confirmed by the clinic",written:"As read",empty:"Upload a report or prescription to see its analysis here.",retry:"Could not load analysis. Try Refresh analysis."},
  hi:{title:"आपके दस्तावेज़ का विश्लेषण",refresh:"विश्लेषण फिर से देखें",original:"मूल दस्तावेज़ देखें",automatic:"AI / स्वचालित विश्लेषण — अपुष्ट",warning:"इस पढ़ने में गलतियाँ हो सकती हैं। इसके आधार पर दवाएँ या इलाज न बदलें। क्लिनिक अलग से जानकारी की जाँच करता है।",scope:"यह दस्तावेज़ का पाठ और फ़ॉलो-अप विवरण दिखाता है। यह निदान या दवाओं की सुरक्षा की जाँच नहीं करता।",text:"दस्तावेज़ से पढ़ा गया पाठ",none:"अभी कोई विवरण नहीं निकाला गया है।",clinic:"क्लिनिक द्वारा जाँची गई जानकारी",waiting:"क्लिनिक ने अभी किसी विवरण की पुष्टि नहीं की है।",approved:"फ़ॉलो-अप योजना स्वीकृत है। अपने देखभाल रिकॉर्ड में देखें।",rejected:"क्लिनिक ने इस दस्तावेज़ को योजना में शामिल नहीं किया। विवरण के लिए संपर्क करें।",notconfirmed:"क्लिनिक द्वारा पुष्टि नहीं हुई",written:"पढ़ा गया पाठ",empty:"विश्लेषण देखने के लिए रिपोर्ट या प्रिस्क्रिप्शन अपलोड करें।",retry:"विश्लेषण नहीं खुला। फिर से देखें।"},
  te:{title:"మీ పత్రం విశ్లేషణ",refresh:"విశ్లేషణ మళ్లీ చూడండి",original:"అసలు పత్రం చూడండి",automatic:"AI / స్వయంచాలక విశ్లేషణ — నిర్ధారించలేదు",warning:"ఈ పఠనంలో తప్పులు ఉండవచ్చు. దీని ఆధారంగా మందులు లేదా చికిత్స మార్చవద్దు. క్లినిక్ సమాచారాన్ని విడిగా తనిఖీ చేస్తుంది.",scope:"ఇది పత్రంలోని పాఠ్యం, ఫాలో-అప్ వివరాలను చూపిస్తుంది. ఇది వ్యాధి నిర్ధారణ లేదా మందుల భద్రత తనిఖీ కాదు.",text:"మీ పత్రం నుంచి చదివిన పాఠ్యం",none:"ఇంకా వివరాలు వెలికితీయలేదు.",clinic:"క్లినిక్ సమీక్షించిన సమాచారం",waiting:"క్లినిక్ ఇంకా వివరాలను నిర్ధారించలేదు.",approved:"ఫాలో-అప్ ప్రణాళిక ఆమోదించబడింది. మీ సంరక్షణ రికార్డులో చూడండి.",rejected:"క్లినిక్ ఈ పత్రాన్ని ప్రణాళికలో ఉపయోగించలేదు. వివరాల కోసం సంప్రదించండి.",notconfirmed:"క్లినిక్ నిర్ధారించలేదు",written:"చదివిన పాఠ్యం",empty:"విశ్లేషణ చూడటానికి నివేదిక లేదా ప్రిస్క్రిప్షన్ అప్లోడ్ చేయండి.",retry:"విశ్లేషణ తెరవలేదు. మళ్లీ ప్రయత్నించండి."}
};
export function DocumentAnalysis({lang,onRefresh}:{lang:Lang;onRefresh?:()=>Promise<unknown>}) {
  const {data,error,reload}=useApi<{documents:Document[]}>("/v1/p/documents"); const c=copy[lang];
  usePoll(Boolean(data?.documents.some(d=>d.status==='EXTRACTION_PENDING')),reload,3000);
  return <section className="card stack" aria-label={c.title}>
    <h2>{c.title}</h2><button className="btn btn--quiet btn--small" onClick={()=>{void reload(); void onRefresh?.().catch(()=>{});}}>{c.refresh}</button>
    {error?<p role="alert">{c.retry}</p>:!data?<p>{t(lang,"loading")}</p>:!data.documents.length?<p className="muted">{c.empty}</p>:data.documents.map((d,index)=><details key={d.id} className="document-analysis" open={index===0?true:undefined}>
      <summary><b>{d.filename}</b><span className="small muted" style={{display:"block"}}>{fmtDateTime(d.uploaded_at,lang)} · {t(lang,`document_${d.status}`)}</span></summary>
      <div className="stack" style={{marginTop:16}}>
        <a className="pt-link" href={`/api/v1/p/documents/${d.id}/file`} target="_blank" rel="noreferrer">{c.original}</a>
        <section className="notice" data-testid="automatic-analysis"><h3>{c.automatic}</h3><p>{c.warning}</p><p className="small">{c.scope}</p>
          {d.automatic_fields.length?d.automatic_fields.map((f,i)=><p key={i}><b>{f.label}</b>: {f.value??"—"}{f.as_written?<span className="small" style={{display:"block"}}>{c.written}: {f.as_written}</span>:null}{f.review_status==='REJECTED'?<span className="small" style={{display:"block"}}>{c.notconfirmed}</span>:null}</p>):<p>{c.none}</p>}
          {d.automatic_text?<details><summary>{c.text}</summary><pre style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere",fontFamily:"inherit",fontSize:14}}>{d.automatic_text}</pre></details>:null}
        </section>
        <section className="notice notice--ok" data-testid="clinic-analysis"><h3>{c.clinic}</h3>
          {d.status==='REJECTED'?<p>{c.rejected}</p>:d.clinic_reviewed_fields.length?d.clinic_reviewed_fields.map((f,i)=><p key={i}><b>{f.label}</b>: {f.value}{f.reviewed_at?<span className="small" style={{display:"block"}}>{fmtDateTime(f.reviewed_at,lang)}</span>:null}</p>):<p>{c.waiting}</p>}
          {d.plan_approved?<p>{c.approved}</p>:null}
        </section>
      </div>
    </details>)}
  </section>;
}
