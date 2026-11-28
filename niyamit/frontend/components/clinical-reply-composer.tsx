"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useAction } from "@/components/ui";
import Link from "next/link";
import type { Slot } from "@/lib/types";

export function ClinicalReplyComposer({ taskId, onSent, showAssistant=true }: { taskId: string; onSent: () => void; showAssistant?: boolean }) {
  const [text, setText] = useState("");
  const [suggestion, setSuggestion] = useState<{patient_id:string;provider:string;proposed_date:string|null;clarification:string|null;urgent_cues:boolean;slots:Slot[];boundary:string}|null>(null);
  const { busy, run } = useAction();
  return <form className="panel stack" onSubmit={async e => {
    e.preventDefault();
    const result = await run(() => api(`/v1/tasks/${taskId}/reply`, { body: { text } }), "Reply saved in the patient app. Task remains open until you record an outcome.");
    if (result) { setText(""); onSent(); }
  }}>
    <h3>Reply to the patient</h3>
    <p className="small muted">Write in a language the patient understands. Your words appear exactly as entered in their app; no automatic clinical translation. This does not send SMS or replace urgent telephone contact.</p>
    <label className="field"><span>Patient-visible reply</span><textarea required maxLength={2000} value={text} onChange={e => setText(e.target.value)} /></label>
    {showAssistant?<button type="button" className="btn btn--quiet" disabled={busy} onClick={async()=>{
      const result=await run(()=>api<NonNullable<typeof suggestion>>(`/v1/tasks/${taskId}/assist`,{body:{draft:text}}));
      if(result)setSuggestion(result);
    }}>Suggest appointment options from this conversation</button>:null}
    {suggestion?<div className="notice stack"><p className="small">{suggestion.boundary} · {suggestion.provider}</p>
      {suggestion.urgent_cues?<p>Urgent concern cues: contact the patient and assess first. No automatic scheduling.</p>:<>
        {suggestion.clarification?<p>{suggestion.clarification}</p>:null}
        {suggestion.proposed_date?<p>Proposed date: {suggestion.proposed_date}</p>:<p>No clear date. Ask the patient before choosing a time.</p>}
        {suggestion.slots.map(slot=><span className="small" key={slot.id}>{slot.label} · {slot.provider}</span>)}
        <Link className="btn btn--quiet" href={`/schedule?patient=${suggestion.patient_id}${suggestion.proposed_date?`&date=${suggestion.proposed_date}`:""}`}>Review schedule and confirm booking</Link>
      </>}
    </div>:null}
    <button className="btn" disabled={busy || !text.trim()}>Send reply to patient app</button>
  </form>;
}
