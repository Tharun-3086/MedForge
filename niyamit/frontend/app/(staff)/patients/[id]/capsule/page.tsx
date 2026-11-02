"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { BARRIER_LABELS, CATEGORY_LABELS, INTENT_LABELS, templateName } from "@/components/outcomes";
import { TimelineList } from "@/components/records";
import { ErrorNote, Loading, MessageStatus, Pill, Provenance, TaskStatus } from "@/components/ui";
import { useApi } from "@/lib/api";
import { fmtDate, fmtDateTime, fmtShortDate, LANGUAGE_NAME } from "@/lib/format";
import type { Appointment, AppointmentRequest, Artifact, Field, Message, PatientBrief, Plan, Task, TimelineEvent } from "@/lib/types";

type Capsule = {
  patient: PatientBrief;
  generated_note: string;
  reason_for_contact: { patient_words: string | null; ai_gloss: string | null; ai_intents: string[] | null; at: string | null; reply_id: string | null };
  plan: Plan | null;
  timeline_since_last_visit: TimelineEvent[];
  documents: Artifact[];
  extracted_fields: (Field & { proposal_id: string; proposal_status: string })[];
  patient_reported: Task[];
  requests: AppointmentRequest[];
  appointments: Appointment[];
  open_tasks: Task[];
  recent_messages: Message[];
};

export default function CapsulePage() {
  const { id } = useParams<{ id: string }>();
  const { data, error, loading } = useApi<Capsule>(`/v1/patients/${id}/capsule`);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorNote error={error} />;
  if (!data) return null;
  const { patient, reason_for_contact: reason, plan } = data;
  const age = patient.birth_year ? new Date().getFullYear() - patient.birth_year : null;

  return (
    <article className="stack-l" style={{ maxWidth: 980 }}>
      <header className="stack" style={{ gap: 6 }}>
        <div className="spread">
          <h1>{patient.name}</h1>
          <div className="row no-print">
            <Link className="btn btn--quiet" href={`/patients/${id}`}>Full record</Link>
            <button className="btn btn--quiet" onClick={() => window.print()}>Print</button>
          </div>
        </div>
        <p className="row" style={{ gap: 14 }}>
          <span>{age ? `${age} years` : null}</span>
          <span>{patient.external_ref}</span>
          <span>{LANGUAGE_NAME[patient.language]}</span>
          <span>Last visit {patient.last_visit_at ? fmtDate(patient.last_visit_at) : "not recorded"}</span>
        </p>
        <p className="small muted">{data.generated_note}</p>
      </header>

      <section className="panel stack">
        <h2 style={{ fontSize: 19 }}>Why they are coming</h2>
        {reason.patient_words ? (
          <>
            <div className="row" style={{ alignItems: "flex-start" }}>
              <Provenance kind="PATIENT_REPORTED" />
              <p className="quote" style={{ fontSize: 17 }}>{reason.patient_words}</p>
            </div>
            <span className="small muted">{fmtDateTime(reason.at)}</span>
            {reason.ai_gloss || reason.ai_intents?.length ? (
              <div className="row">
                <Provenance kind="AI_PROPOSED" label="AI reading, not a finding" />
                {reason.ai_gloss ? <span>{reason.ai_gloss}</span> : null}
                {(reason.ai_intents ?? []).map((i) => <Pill key={i}>{INTENT_LABELS[i] ?? i}</Pill>)}
              </div>
            ) : null}
          </>
        ) : <p className="muted">The patient has not sent a message.</p>}
      </section>

      <div className="cols-2">
        <section className="panel stack">
          <h2 style={{ fontSize: 19 }}>Approved plan</h2>
          {plan ? (
            <>
              <span className="row small"><Provenance kind="CLINICIAN_APPROVED" label={`Approved by ${plan.approved_by ?? "staff"}`} /> v{plan.version}, {fmtDate(plan.approved_at)}</span>
              <ul className="stack" style={{ listStyle: "none", padding: 0, margin: 0, gap: 6 }}>
                {plan.items.map((i) => (
                  <li key={i.id} className="spread">
                    <span><b>{i.label}</b> by {fmtShortDate(i.due_date)}</span>
                    <span className="small">{i.status === "CONFIRMED_BY_PATIENT" ? "Patient confirmed" : i.status === "BOOKED" ? "Booked" : i.status === "COMPLETED" ? "Done" : i.days_overdue > 0 ? `${i.days_overdue} days late` : "Due"}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : <p className="muted">No active plan.</p>}
          {data.appointments.length ? (
            <div className="stack" style={{ gap: 4 }}>
              <h3 style={{ fontSize: 15 }}>Appointments</h3>
              {data.appointments.map((a) => <span key={a.id} className="small">{a.slot_label}, ref {a.reference} ({a.status.toLowerCase()})</span>)}
            </div>
          ) : null}
          {data.requests.length ? (
            <div className="stack" style={{ gap: 4 }}>
              <h3 style={{ fontSize: 15 }}>Requests</h3>
              {data.requests.map((r) => <span key={r.id} className="small">{r.status_label}{r.requested_day_text ? `, asked for “${r.requested_day_text}”` : ""}, {fmtShortDate(r.created_at)}</span>)}
            </div>
          ) : null}
        </section>

        <section className="panel stack">
          <h2 style={{ fontSize: 19 }}>Reported by the patient</h2>
          {data.patient_reported.length === 0 ? <p className="muted">No barriers or questions reported.</p> : data.patient_reported.map((t) => (
            <div key={t.id} className="stack" style={{ gap: 4 }}>
              <span className="row"><b>{CATEGORY_LABELS[t.category]}</b>{t.barrier_category ? <Pill>{BARRIER_LABELS[t.barrier_category]}</Pill> : null}<TaskStatus status={t.status} /></span>
              <span className="quote small">{t.patient_statement}</span>
            </div>
          ))}
          <h3 style={{ fontSize: 15 }}>Open tasks</h3>
          {data.open_tasks.length === 0 ? <p className="small muted">None.</p> : data.open_tasks.map((t) => (
            <span key={t.id} className="small"><Link href={`/tasks?task=${t.id}`}>{t.title}</Link>, {t.assignee ?? "no owner yet"}</span>
          ))}
        </section>
      </div>

      <section className="panel stack">
        <h2 style={{ fontSize: 19 }}>Documents</h2>
        {data.documents.length === 0 ? <p className="muted">No documents.</p> : data.documents.map((d) => (
          <span key={d.id}>
            <a href={`/api${d.content_url}`} target="_blank" rel="noreferrer">{d.filename}</a>{" "}
            <span className="small muted">{d.source_type.toLowerCase().replace("_", " ")}, {fmtShortDate(d.created_at)}{d.uploaded_by_patient ? ", shared by the patient" : ""}</span>
          </span>
        ))}
        {data.extracted_fields.length ? (
          <table className="table">
            <thead><tr><th>Field</th><th>Value</th><th>Status</th><th /></tr></thead>
            <tbody>
              {data.extracted_fields.filter((f) => f.name !== "document_type").map((f) => (
                <tr key={f.id}>
                  <td>{f.label}</td>
                  <td>{f.value && /^\d{4}-/.test(f.value) ? fmtDate(f.value) : f.value ?? "No exact value"}</td>
                  <td><Provenance kind={f.status === "APPROVED" ? "STAFF_CONFIRMED" : "AI_PROPOSED"} label={f.status === "APPROVED" ? "Staff confirmed" : f.status === "REJECTED" ? "Rejected" : undefined} /></td>
                  <td><Link className="small" href={`/reports/${f.proposal_id}`}>Source</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </section>

      <div className="cols-2">
        <section className="panel">
          <h2 style={{ fontSize: 19, marginBottom: 6 }}>Since the last visit</h2>
          <TimelineList events={data.timeline_since_last_visit} />
        </section>
        <section className="panel stack">
          <h2 style={{ fontSize: 19 }}>Recent messages</h2>
          {data.recent_messages.length === 0 ? <p className="muted">None.</p> : data.recent_messages.map((m) => (
            <div key={m.id} className="spread small">
              <span>{templateName(m.template_key)}, {fmtDateTime(m.sent_at ?? m.created_at)}</span>
              <MessageStatus status={m.status} label={m.status_label} />
            </div>
          ))}
        </section>
      </div>
    </article>
  );
}
