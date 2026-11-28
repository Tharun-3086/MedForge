"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { BARRIER_KEYS, tBarrier, t, type Lang } from "@/lib/i18n";

export type BookedAppointment = { id: string; starts_at: string; reference: string; label: string; with: string; patient_response?: string | null };
export type AppointmentRequestStatus = {id:string;question:string;status:string;outcome:string|null;reply:{text:string;from:string;at:string}|null};
export type AppointmentUpdate = {id:string;text:string;from:string;at:string};
const APPOINTMENT_OUTCOMES:Record<string,string>={APPOINTMENT_CANCELLED:"Appointment cancelled",APPOINTMENT_POSTPONED:"Appointment postponed",APPOINTMENT_PREPONED:"Appointment moved earlier"};
export function BookedAppointments({ appointments, requests=[], updates=[], lang, onChanged }: { appointments: BookedAppointment[]; requests?:AppointmentRequestStatus[];updates?:AppointmentUpdate[];lang: Lang; onChanged: () => unknown }) {
  const [reasonFor, setReasonFor] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function respond(id: string, choice: string) {
    setBusy(true); setMessage("");
    try {
      await api(`/v1/p/appointments/${id}/response`, { body: { choice, reason: choice === "CANNOT_ATTEND" ? reason : "" } });
      setReasonFor(null); await onChanged();
      setMessage(lang === "hi" ? "क्लिनिक को बता दिया गया। बुकिंग अभी बनी हुई है।" : lang === "te" ? "క్లినిక్‌కు తెలియజేయబడింది. బుకింగ్ ఇంకా అలాగే ఉంది." : "Clinic notified. Your booking stays reserved until the clinic changes it.");
    } catch (e) { setMessage(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  if (!appointments.length&&!requests.length&&!updates.length) return null;
  return <section className="card"><h2>{t(lang, "appointments")}</h2>
    {appointments.map(a => <article key={a.id} className="appointment-card stack">
      <b>{fmtDate(a.starts_at, lang)} · {a.label.split(", ").slice(-1)[0]}</b>
      <span className="small muted">{a.with} · {t(lang, "ref", { ref: a.reference })}</span>
      {a.patient_response ? <p className="small" role="status">{a.patient_response}</p> : null}
      <div className="appointment-actions">
        <button className="btn" disabled={busy} onClick={() => void respond(a.id, "CONFIRM")}>{t(lang, "confirm")}</button>
        <button className="btn btn--quiet" disabled={busy} onClick={() => { setReasonFor(a.id); setReason(""); }}>{lang === "hi" ? "मैं नहीं आ सकता/सकती" : lang === "te" ? "నేను రాలేను" : "I can't come"}</button>
        <button className="btn btn--quiet" disabled={busy} onClick={() => void respond(a.id, "RESCHEDULE")}>{t(lang, "reschedule")}</button>
        <button className="btn btn--quiet" disabled={busy} onClick={() => void respond(a.id, "CALLBACK")}>{t(lang, "callMe")}</button>
      </div>
      {reasonFor === a.id ? <form className="row" onSubmit={e => { e.preventDefault(); void respond(a.id, "CANNOT_ATTEND"); }}>
        <select aria-label={lang === "en" ? "Reason you cannot attend" : t(lang, "problem")} value={reason} required onChange={e => setReason(e.target.value)}><option value="">{lang === "en" ? "Choose a reason" : t(lang, "problem")}</option>{BARRIER_KEYS.map(key => <option key={key} value={key}>{tBarrier(lang, key)}</option>)}</select>
        <button className="btn" disabled={busy || !reason}>{t(lang, "send")}</button>
      </form> : null}
    </article>)}
    {updates.length?<div className="stack"><h3>{lang==="hi"?"क्लिनिक द्वारा बदलाव":lang==="te"?"క్లినిక్ చేసిన మార్పులు":"Clinic appointment updates"}</h3>{updates.map(update=><div className="notice" key={update.id}><b>{update.from}</b><p style={{whiteSpace:"pre-wrap"}}>{update.text}</p></div>)}</div>:null}
    {requests.length?<details open={requests.some(request=>request.reply||request.status==="RESOLVED")}><summary>{lang==="hi"?"आपके अनुरोध और क्लिनिक के जवाब":lang==="te"?"మీ అభ్యర్థనలు & క్లినిక్ సమాధానాలు":"Your requests & clinic replies"}</summary><div className="stack">{requests.map(request=><article key={request.id} className="appointment-card"><p className="small">{request.question}</p><b className="small">{request.status==="RESOLVED"?(APPOINTMENT_OUTCOMES[request.outcome??""]??"Request completed"):request.status==="CANCELLED"?"Request closed":request.status==="UNABLE_TO_RESOLVE"?"Please contact the clinic; request could not be resolved":request.reply?"Clinic replied · request in progress":"Awaiting clinic response"}</b>{request.reply?<div className="notice notice--ok"><b>{request.reply.from}</b><p style={{whiteSpace:"pre-wrap"}}>{request.reply.text}</p></div>:null}</article>)}</div></details>:null}
    {message ? <p role="status" className="notice">{message}</p> : null}
  </section>;
}
