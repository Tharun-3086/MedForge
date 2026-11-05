"use client";

import { useEffect, useRef, useState } from "react";

import { PageHead } from "@/components/staff-shell";
import { ErrorNote, Loading, useAction } from "@/components/ui";
import { api, usePoll, useApi } from "@/lib/api";
import { fmtTime, LANGUAGE_NAME } from "@/lib/format";
import type { PatientBrief } from "@/lib/types";

type Bubble = {
  direction: "in" | "out"; id: string; body: string; status: string; status_label?: string; kind?: string;
  event_id?: string | null; duplicates_ignored?: number; at: string;
  english_gloss?: string | null;
  patient_preferred_language?: string | null;
  detected_language?: string | null;
  understanding_source?: string | null;
};
type Thread = { patient: PatientBrief; simulated: boolean; messages: Bubble[]; note: string };

const SAMPLES = [
  "దయచేసి నాకు ఫోన్ చేయండి.",
  "कृपया मुझे फोन करें।",
  "Doctor, Monday nahi aa sakta. Saturday slot unda?",
  "Avunu, vastanu",
  "Paise nahi hain abhi, test baad mein karwaunga",
  "Bus ledu, raavadaniki kastam",
  "Sugar 300 undi, tablet maarchala?",
  "Please call me back",
  "hmm ok maybe",
];

function languageName(code: string): string {
  return LANGUAGE_NAME[code.toLowerCase().split(/[-_]/)[0]] ?? code;
}

function PatientMessage({ message }: { message: Bubble }) {
  const gloss = message.english_gloss?.trim();
  const language = message.detected_language || message.patient_preferred_language;
  return (
    <div className="stack" style={{ gap: 8, minWidth: 0, overflowWrap: "anywhere" }}>
      <div lang={language || undefined} dir="auto" style={{ whiteSpace: "pre-wrap" }}>{message.body}</div>
      <div className="small muted">
        {message.patient_preferred_language ? <div>Preferred language: {languageName(message.patient_preferred_language)}</div> : null}
        {message.detected_language ? <div>Detected language: {languageName(message.detected_language)} ({message.detected_language})</div> : null}
      </div>
      <details open>
        <summary style={{ cursor: "pointer", paddingBlock: 8 }}>Translate / English meaning</summary>
        <div className="stack" style={{ gap: 6, borderTop: "1px solid currentColor", paddingTop: 8 }}>
          {gloss ? (
            <>
              <strong className="small">ENGLISH MEANING · AI-GENERATED</strong>
              <div lang="en" style={{ whiteSpace: "pre-wrap" }}>{gloss}</div>
              <span className="small muted">AI interpretation. Check the original message before acting.</span>
            </>
          ) : (
            <p className="small muted">English meaning unavailable. This view only displays meanings provided by the backend.</p>
          )}
          {message.understanding_source ? <span className="small muted">Understanding source: {message.understanding_source}</span> : null}
        </div>
      </details>
    </div>
  );
}
const REPLY_STATUS: Record<string, string> = {
  RECEIVED: "received", VALIDATED: "processing", CLASSIFIED: "understood", NEEDS_CLARIFICATION: "asked to clarify",
  NEEDS_CONFIRMATION: "waiting for a choice", ROUTED: "sent to staff", ACTION_SUCCEEDED: "done",
  ACTION_FAILED: "failed", HUMAN_HANDOFF: "handed to a person", TRANSCRIPTION_FAILED: "voice not understood",
};

export default function PhonePage() {
  const { data: list, error: listError } = useApi<{ patients: PatientBrief[] }>("/v1/demo/phone/patients");
  const [patientId, setPatientId] = useState<string | null>(null);
  const thread = useApi<Thread>(patientId ? `/v1/demo/phone/${patientId}` : null);
  const { busy, run } = useAction();
  const [text, setText] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  const followLatest = useRef(true);
  const openedPatient = useRef<string | null>(null);
  const [awayFromBottom, setAwayFromBottom] = useState(false);

  function scrollToLatest(smooth = true) {
    const el = scroller.current;
    if (!el) return;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollTo({ top: el.scrollHeight, behavior: smooth && !reduceMotion ? "smooth" : "instant" });
    followLatest.current = true;
    setAwayFromBottom(false);
  }

  useEffect(() => {
    if (!patientId && list?.patients.length) setPatientId(list.patients[0].id);
  }, [list, patientId]);
  useEffect(() => {
    if (!thread.data || thread.data.patient.id !== patientId) return;
    const firstLoad = openedPatient.current !== patientId;
    openedPatient.current = patientId;
    if (firstLoad || followLatest.current) scrollToLatest(!firstLoad);
  }, [thread.data, patientId]);

  const settling = Boolean(thread.data?.messages.some((m) => m.direction === "in" && ["RECEIVED", "VALIDATED"].includes(m.status)));
  usePoll(Boolean(patientId), thread.reload, settling ? 1200 : 4000);

  async function send(body: string, button = false) {
    if (!patientId || !body.trim()) return;
    const r = await run(() => api<Thread & { result: { status: string } }>(`/v1/demo/phone/${patientId}/reply`, { body: { text: body, button } }));
    if (r) {
      followLatest.current = true;
      thread.setData(r);
      setText("");
    }
  }

  async function replay() {
    const last = [...(thread.data?.messages ?? [])].reverse().find((m) => m.direction === "in" && m.event_id);
    if (!last?.event_id || !patientId) return;
    const r = await run(() => api<Thread & { result: { status: string } }>(`/v1/demo/phone/${patientId}/replay`, { body: { event_id: last.event_id } }),
      (res) => res.result.status === "duplicate" ? "Same event delivered again: recorded as a duplicate, no new action." : `Result: ${res.result.status}`);
    if (r) thread.setData(r);
  }

  const patient = thread.data?.patient;
  return (
    <>
      <PageHead title="Patient phone (simulated)"
        lede="A stand-in for the patient's WhatsApp. Messages from the clinic appear here only after the system actually sends them, and replies go back through the same signed webhook a real provider would use." />
      <ErrorNote error={listError} />
      <ErrorNote error={thread.error} />
      <div className="phone-wrap">
        <div className="stack">
          <label className="field"><span>Whose phone</span>
            <select value={patientId ?? ""} disabled={busy || !list?.patients.length} onChange={(e) => {
              thread.setData(null);
              setText("");
              followLatest.current = true;
              setAwayFromBottom(false);
              setPatientId(e.target.value);
            }}>
              {!list?.patients.length ? <option value="">{list ? "No simulated patients" : "Loading patients…"}</option> : null}
              {list?.patients.map((p) => <option key={p.id} value={p.id}>{p.name} ({LANGUAGE_NAME[p.language]})</option>)}
            </select>
          </label>
          <div className="panel stack" style={{ gap: 8 }}>
            <h3 style={{ fontSize: 15 }}>Try a reply</h3>
            {SAMPLES.map((s) => (
              <button key={s} className="btn btn--quiet btn--small" style={{ justifyContent: "flex-start", whiteSpace: "normal", textAlign: "left", height: "auto" }}
                disabled={busy || !patientId} onClick={() => send(s)}>{s}</button>
            ))}
          </div>
          <div className="panel stack" style={{ gap: 8 }}>
            <h3 style={{ fontSize: 15 }}>Voice replies</h3>
            <p className="small muted">This simulated phone sends text and button replies. For voice recording, open the patient's record and use Patient app link. Recording requires voice service availability, patient AI consent, microphone permission, and a secure browser connection (HTTPS or localhost).</p>
          </div>
          <div className="panel stack" style={{ gap: 8 }}>
            <h3 style={{ fontSize: 15 }}>Reliability check</h3>
            <p className="small muted">Deliver the last reply again with the same provider event id, as a provider retry would. It must not create a second task or message.</p>
            <button className="btn btn--quiet btn--small" disabled={busy || !thread.data?.messages.some((m) => m.direction === "in")} onClick={replay}>Deliver last reply again</button>
          </div>
        </div>

        <div className="phone" aria-label="Simulated phone">
          <div className="phone-top">
            <span className="sim">SIMULATED</span>
            <b>{patient ? patient.name : "…"}</b>
            <span className="small" style={{ color: "#9fb3c6" }}>{patient?.phone}</span>
          </div>
          <div className="thread" ref={scroller} aria-label="Patient conversation" tabIndex={0} onScroll={() => {
            const el = scroller.current;
            if (!el) return;
            const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
            followLatest.current = nearBottom;
            setAwayFromBottom(!nearBottom);
          }}>
            {!thread.data && !thread.error && !listError ? <div role="status"><Loading /></div> : null}
            {thread.data?.messages.length === 0 ? <p className="small muted">No messages yet. Send a reminder from the patient record, or reply below.</p> : null}
            {thread.data?.messages.map((m) => (
              <div key={`${m.direction}-${m.id}`} className={`bubble ${m.direction === "out" ? "bubble--clinic" : "bubble--patient"}`}>
                {m.direction === "in" ? <PatientMessage message={m} /> : <div dir="auto" style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{m.body}</div>}
                <span className="meta">
                  {fmtTime(m.at)}
                  {m.direction === "out" ? `, ${m.status === "DELIVERED" ? "delivered" : (m.status_label ?? m.status).toLowerCase()}` : `, ${REPLY_STATUS[m.status] ?? m.status.toLowerCase()}`}
                  {m.duplicates_ignored ? `, ${m.duplicates_ignored} duplicate${m.duplicates_ignored === 1 ? "" : "s"} ignored` : ""}
                </span>
              </div>
            ))}
          </div>
          <form className="composer" onSubmit={(e) => { e.preventDefault(); void send(text); }}>
            {awayFromBottom ? <button className="btn btn--quiet btn--small" type="button" onClick={() => scrollToLatest()}>Jump to latest</button> : null}
            <span className="small muted" role="status">{busy ? "Sending…" : settling ? "Processing reply…" : ""}</span>
            <div className="quick">
              {[["1", "1 Confirm"], ["2", "2 Change date"], ["3", "3 Call me"], ["STOP", "STOP"]].map(([v, label]) => (
                <button key={v} type="button" className="btn btn--quiet btn--small" disabled={busy || !patientId} onClick={() => send(v, true)}>{label}</button>
              ))}
            </div>
            <div className="row" style={{ flexWrap: "nowrap" }}>
              <input type="text" placeholder="Type as the patient" value={text} onChange={(e) => setText(e.target.value)} aria-label="Reply as the patient" />
              <button className="btn" type="submit" disabled={busy || !patientId || !text.trim()}>{busy ? "Sending…" : "Send"}</button>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}
