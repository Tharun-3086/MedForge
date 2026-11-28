"use client";

import { useState } from "react";
import { api, clientKey } from "@/lib/api";
import { useAction } from "@/components/ui";
import type { Lang } from "@/lib/i18n";
import { fmtDateTime } from "@/lib/format";

export type ClinicConversationData = {
  clinician_replies?: { id: string; text: string; from: string; question: string | null; at: string }[];
  clinical_questions?: { id: string; question: string; status: string; urgent: boolean }[];
};

export function ClinicConversation({ data, lang, onChanged }: { data: ClinicConversationData; lang: Lang; onChanged: () => unknown }) {
  const [text, setText] = useState("");
  const [key, setKey] = useState(clientKey);
  const { busy, run } = useAction();
  const title = lang === "hi" ? "क्लिनिक से पूछें" : lang === "te" ? "క్లినిక్‌ను అడగండి" : "Ask your clinic";
  return <section id="clinic-conversation" className="card stack">
    <h2>{title}</h2>
    <p>{lang === "hi" ? "अपनी भाषा में लिखें। डॉक्टर या नर्स जवाब देंगे। यह आपातकालीन सेवा नहीं है।" : lang === "te" ? "మీ భాషలో రాయండి. డాక్టర్ లేదా నర్సు సమాధానం ఇస్తారు. ఇది అత్యవసర సేవ కాదు." : "Write in your own language. A doctor or nurse will review and reply here. This is not an emergency service."}</p>
    <form className="stack" onSubmit={async e => {
      e.preventDefault();
      const result = await run(() => api("/v1/p/questions", { body: { text, client_key: key } }), lang === "en" ? "Sent to the clinical team." : lang === "hi" ? "क्लिनिक को भेज दिया गया।" : "క్లినిక్‌కు పంపబడింది.");
      if (result) { setText(""); setKey(clientKey()); onChanged(); }
    }}>
      <label className="field"><span>{title}</span><textarea id="clinic-question" required maxLength={1000} value={text} onChange={e => setText(e.target.value)} /></label>
      <button className="btn" disabled={busy || !text.trim()}>{lang === "hi" ? "सवाल भेजें" : lang === "te" ? "ప్రశ్న పంపండి" : "Send question"}</button>
    </form>
    <button className="pt-link" onClick={() => onChanged()}>{lang === "hi" ? "जवाब रीफ्रेश करें" : lang === "te" ? "సమాధానాలను రిఫ్రెష్ చేయండి" : "Refresh replies"}</button>
    {data.clinical_questions?.filter(q => ["OPEN", "ASSIGNED", "IN_PROGRESS"].includes(q.status)).map(q => <p key={q.id} className="notice" style={{ whiteSpace: "pre-wrap" }}>{q.question}<br />{lang === "hi" ? "क्लिनिक की समीक्षा जारी है" : lang === "te" ? "క్లినిక్ సమీక్షలో ఉంది" : "With the clinical team"}</p>)}
    {data.clinician_replies?.map(reply => <article key={reply.id} className="notice notice--ok">
      <b>{reply.from}</b><p className="small muted">{fmtDateTime(reply.at, lang)}</p>
      {reply.question ? <blockquote>{reply.question}</blockquote> : null}
      <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{reply.text}</p>
    </article>)}
  </section>;
}
