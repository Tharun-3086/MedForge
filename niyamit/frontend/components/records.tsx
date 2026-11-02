"use client";

import { ACTION_STATUS_LABELS, INTENT_LABELS } from "@/components/outcomes";
import { Pill, Provenance, ReplyStatus } from "@/components/ui";
import { fmtDateTime, fmtLongDay } from "@/lib/format";
import type { Reply, TimelineEvent } from "@/lib/types";

const WHERE: Record<string, string> = { SIMULATED: "on the simulated phone", WHATSAPP: "on WhatsApp", PATIENT_APP: "in the patient app" };

export function ReplyCard({ reply: r }: { reply: Reply }) {
  const tapped = r.input_mode === "BUTTON";
  const words = tapped ? null : r.corrected_text || r.text || r.transcript;
  const ai = r.understanding_source.startsWith("LLM");
  return (
    <div className="stack" style={{ gap: 6, paddingBottom: 12, borderBottom: "1px solid var(--rule)" }}>
      <div className="spread">
        <span className="small muted">
          {fmtDateTime(r.created_at)}, {r.input_mode === "VOICE" ? "voice note" : tapped ? "button" : "text"} {WHERE[r.channel] ?? r.channel.toLowerCase()}
          {r.via_caregiver ? ", sent by a caregiver" : ""}
        </span>
        <ReplyStatus status={r.status} />
      </div>
      {tapped ? (
        <div className="row">
          <Provenance kind="PATIENT_REPORTED" label="Patient chose" />
          <span>{r.choice_label ?? r.text}</span>
        </div>
      ) : null}
      {words ? (
        <div className="row" style={{ alignItems: "flex-start" }}>
          <Provenance kind="PATIENT_REPORTED" label={r.input_mode === "VOICE" && !r.corrected_text ? "Patient said (transcript)" : undefined} />
          <span>{words}</span>
        </div>
      ) : null}
      {r.status === "TRANSCRIPTION_FAILED" ? <p className="small" style={{ color: "var(--alarm)" }}>Voice note could not be transcribed ({r.error_code}). No transcript was invented.</p> : null}
      {(r.understanding.intents ?? []).length > 0 ? (
        <div className="row">
          <Provenance kind={r.understanding_source === "BUTTON" ? "PATIENT_REPORTED" : "AI_PROPOSED"}
            label={r.understanding_source === "BUTTON" ? "Tapped" : ai ? "AI understood" : "Rules understood"} />
          {(r.understanding.intents ?? []).map((i) => <Pill key={i}>{INTENT_LABELS[i] ?? i}</Pill>)}
          {typeof r.understanding.confidence === "number" && r.understanding_source !== "BUTTON" ? <span className="small muted">{Math.round(r.understanding.confidence * 100)}% confidence</span> : null}
        </div>
      ) : null}
      {r.actions.map((a, i) => (
        <div key={i} className="stack small" style={{ gap: 2 }}>
          <span>{INTENT_LABELS[a.intent] ?? a.intent}: {ACTION_STATUS_LABELS[a.status] ?? a.status}{a.booking_reference ? `, ref ${a.booking_reference}` : ""}</span>
          {a.intent === "RESCHEDULE_REQUEST" && (a.day_words || a.candidate_date || a.date_options?.length) ? (
            <span className="muted">
              {a.day_words ? `Asked for “${a.day_words}”` : "Asked for a new time"}
              {a.candidate_date ? `, read as ${fmtLongDay(a.candidate_date)}`
                : a.date_options?.length ? `, could mean ${a.date_options.map((d) => fmtLongDay(d)).join(" or ")}: the patient was asked`
                : ", no exact day: the patient was asked"}
            </span>
          ) : null}
          {a.slots?.length ? (
            <span className="muted">{a.slots.length} real time{a.slots.length === 1 ? "" : "s"} offered, from {a.slots[0].label}</span>
          ) : null}
        </div>
      ))}
    </div>
  );
}

export function TimelineList({ events }: { events: TimelineEvent[] }) {
  if (events.length === 0) return <p className="muted">Nothing recorded yet.</p>;
  return (
    <ol className="timeline">
      {events.map((e) => (
        <li key={e.id}>
          <time dateTime={e.at}>{fmtDateTime(e.at)}</time>
          <div className="stack" style={{ gap: 4 }}>
            <span>{e.summary}</span>
            {e.patient_words ? <span className="quote small">{e.patient_words}</span> : null}
            <span className="row"><Provenance kind={e.provenance} /><span className="small muted">{e.actor}</span></span>
          </div>
        </li>
      ))}
    </ol>
  );
}
