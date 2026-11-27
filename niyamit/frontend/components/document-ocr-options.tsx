"use client";
import type { Lang } from "@/lib/i18n";

export function DocumentOcrOptions({style,language,onStyle,onLanguage,disabled=false,lang="en"}:{
  style:string;language:string;onStyle:(v:string)=>void;onLanguage:(v:string)=>void;disabled?:boolean;lang?:Lang;
}) {
  const labels={en:["Document writing","Automatic / unsure","Printed","Handwritten","Printed and handwritten","Document language","Handwriting may be unreadable. Your clinic must check uncertain text, medicines and doses against the original. English handwriting recognition is experimental; Hindi and Telugu handwriting require manual verification."],
    hi:["दस्तावेज़ की लिखावट","स्वचालित / पता नहीं","छपा हुआ","हस्तलिखित","छपा और हस्तलिखित","दस्तावेज़ की भाषा","लिखावट पढ़ने में गलती हो सकती है। क्लिनिक मूल दस्तावेज़ से दवा और खुराक जाँचेगा। हिंदी और तेलुगु हस्तलेखन की मैनुअल जाँच आवश्यक है।"],
    te:["పత్రం రాత","స్వయంచాలక / తెలియదు","ముద్రించినది","చేతిరాత","ముద్రణ మరియు చేతిరాత","పత్రం భాష","చేతిరాత పఠనంలో తప్పులు ఉండవచ్చు. మందులు, మోతాదులను క్లినిక్ అసలు పత్రంతో తనిఖీ చేయాలి. తెలుగు మరియు హిందీ చేతిరాతకు మానవ నిర్ధారణ అవసరం."]}[lang];
  return <div className="stack"><label className="field"><span>{labels[0]}</span><select aria-label={labels[0]} value={style} disabled={disabled} onChange={e=>onStyle(e.target.value)}>{["auto","printed","handwritten","mixed"].map((v,i)=><option key={v} value={v}>{labels[i+1]}</option>)}</select></label><label className="field"><span>{labels[5]}</span><select aria-label={labels[5]} value={language} disabled={disabled} onChange={e=>onLanguage(e.target.value)}><option value="en">English</option><option value="hi">हिन्दी</option><option value="te">తెలుగు</option></select></label><p className="small muted">{labels[6]}</p></div>;
}
