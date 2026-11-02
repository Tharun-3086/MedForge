"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { CATEGORY_LABELS, reminderOutcome, templateName } from "@/components/outcomes";
import { PlanEditor } from "@/components/plan-editor";
import { ReplyCard, TimelineList } from "@/components/records";
import { PageHead } from "@/components/staff-shell";
import { Empty, ErrorNote, Loading, MessageStatus, Modal, Pill, Provenance, TaskStatus, useAction, useToast } from "@/components/ui";
import { api, clientKey, useApi } from "@/lib/api";
import { fmtDate, fmtDateTime, LANGUAGE_NAME } from "@/lib/format";
import { useStaff } from "@/lib/staff-context";
import type { Appointment, Message, PatientBrief, Plan, Reply, Task, TimelineEvent } from "@/lib/types";

type Detail = {
  patient: PatientBrief; consents: Record<string, string>; plans: Plan[]; replies: Reply[]; messages: Message[];
  tasks: Task[]; appointments: Appointment[]; today: string;
};

const ITEM_STATUS: Record<string, [string, "wait" | "done" | "info" | "neutral"]> = {
  PENDING: ["Due", "wait"], CONFIRMED_BY_PATIENT: ["Patient confirmed", "info"], BOOKED: ["Booked", "done"],
  COMPLETED: ["Completed (staff verified)", "done"], CANCELLED: ["Cancelled", "neutral"],
};
const CONSENT_LABEL: Record<string, string> = {
  REMINDERS: "Reminder messages", AI_PROCESSING: "AI reading of messages and reports", REPORT_SHARING: "Report sharing",
  CAREGIVER_ACCESS: "Caregiver access",
};

export default function PatientPage() {
  const { id } = useParams<{ id: string }>();
  const { can, refreshCounts } = useStaff();
  const toast = useToast();
  const { data, error, loading, reload } = useApi<Detail>(`/v1/patients/${id}`);
  const timeline = useApi<{ events: TimelineEvent[] }>(`/v1/patients/${id}/timeline`);
  const { busy, run } = useAction();
  const [planOpen, setPlanOpen] = useState(false);
  const [link, setLink] = useState<string | null>(null);

  if (loading && !data) return <Loading />;
  if (error) return <ErrorNote error={error} />;
  if (!data) return null;
  const { patient } = data;
  const active = data.plans.find((p) => p.status === "ACTIVE");
  const pending = data.plans.filter((p) => p.status === "NEEDS_REVIEW");
  const history = data.plans.filter((p) => !["ACTIVE", "NEEDS_REVIEW"].includes(p.status));
  const openTasks = data.tasks.filter((t) => ["OPEN", "ASSIGNED", "IN_PROGRESS"].includes(t.status));

  async function refresh() {
    await Promise.all([reload(), timeline.reload()]);
    refreshCounts();
  }

  async function remind() {
    try {
      const m = await api<Message>(`/v1/patients/${id}/reminders`, { body: { client_key: clientKey() } });
      const outcome = reminderOutcome(m);
      toast(outcome.text, outcome.fail);
      await refresh();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Could not send the reminder.", true);
    }
  }

  async function post(path: string, body: unknown, success: string) {
    const ok = await run(() => api(path, { body }), success);
    if (ok) await refresh();
  }

  return (
    <>
      <PageHead
        title={patient.name}
        lede={<span className="row" style={{ gap: 14 }}>
          <span>{patient.external_ref}</span>
          <span>{patient.phone}</span>
          <span>{LANGUAGE_NAME[patient.language] ?? patient.language}</span>
          {patient.birth_year ? <span>Born {patient.birth_year}</span> : null}
          <span>{patient.channel === "SIMULATED" ? "Messages to the simulated phone" : "Messages by WhatsApp"}</span>
          {patient.opted_out ? <Pill tone="fail">Opted out of reminders</Pill> : null}
        </span>}
        actions={<>
          <Link className="btn btn--quiet" href={`/patients/${id}/capsule`}>Visit capsule</Link>
          {!patient.opted_out ? <button className="btn btn--quiet" onClick={remind}>Send reminder</button> : null}
          <button className="btn btn--quiet" disabled={busy} onClick={async () => {
            const r = await run(() => api<{ link: string }>(`/v1/patients/${id}/access-link`, { method: "POST" }));
            if (r) setLink(r.link);
          }}>Patient app link</button>
          <a className="btn" href={`tel:${patient.phone}`}>Call</a>
        </>}
      />

      <div className="cols-2">
        <div className="stack-l">
          <section className="panel">
            <div className="panel-head">
              <h2 style={{ fontSize: 19 }}>Follow-up plan</h2>
              <button className="btn btn--quiet btn--small" onClick={() => setPlanOpen(true)}>New plan</button>
            </div>
            {pending.map((p) => (
              <div key={p.id} className="notice notice--warn stack" style={{ marginBottom: 12 }}>
                <span>Draft plan v{p.version} is waiting for approval: {p.items.map((i) => `${i.label} by ${fmtDate(i.due_date)}`).join("; ")}.</span>
                {can("plans.approve") ? (
                  <button className="btn btn--approve btn--small" style={{ justifySelf: "start" }} disabled={busy}
                    onClick={() => post(`/v1/follow-up-plans/${p.id}/approve`, {}, "Plan approved. Reminders are scheduled.")}>Approve this plan</button>
                ) : <span className="small">A doctor or nurse approves plans.</span>}
              </div>
            ))}
            {active ? (
              <div className="stack">
                <div className="row small muted">
                  <Provenance kind={active.approved_by ? "CLINICIAN_APPROVED" : "STAFF_CONFIRMED"} label={`Approved by ${active.approved_by ?? "staff"}`} />
                  <span>Version {active.version}, {fmtDateTime(active.approved_at)}</span>
                  {active.proposal_id ? <Link href={`/reports/${active.proposal_id}`}>From an uploaded document</Link> : <span>Entered by hand</span>}
                </div>
                <table className="table">
                  <tbody>
                    {active.items.map((i) => {
                      const [label, tone] = ITEM_STATUS[i.status] ?? [i.status, "neutral"];
                      return (
                        <tr key={i.id}>
                          <td><b>{i.label}</b>{i.days_overdue > 0 ? <span className="small" style={{ color: "var(--amber)", display: "block" }}>{i.days_overdue} days late</span> : null}</td>
                          <td className="nowrap">{fmtDate(i.due_date)}</td>
                          <td><Pill tone={tone}>{label}</Pill></td>
                          <td style={{ textAlign: "right" }}>
                            {!["COMPLETED", "CANCELLED"].includes(i.status) ? (
                              <button className="btn btn--quiet btn--small" disabled={busy}
                                onClick={() => post(`/v1/follow-up-items/${i.id}/complete`, { note: "" }, `${i.label} marked completed.`)}>
                                Mark done
                              </button>
                            ) : null}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <p className="small muted">“Patient confirmed” is what the patient told us; only staff can mark a follow-up done.</p>
              </div>
            ) : pending.length === 0 ? (
              <Empty title="No active plan" action={<button className="btn btn--small" onClick={() => setPlanOpen(true)}>Enter a plan</button>}>
                Enter one by hand, or upload the prescription in the Report inbox.
              </Empty>
            ) : null}
            {history.length > 0 ? (
              <details style={{ marginTop: 12 }}>
                <summary className="small" style={{ cursor: "pointer" }}>Earlier versions ({history.length})</summary>
                <ul className="small">
                  {history.map((p) => <li key={p.id}>v{p.version} {p.status.toLowerCase()}: {p.items.map((i) => `${i.label} ${fmtDate(i.due_date)}`).join(", ")}</li>)}
                </ul>
              </details>
            ) : null}
          </section>

          <section className="panel">
            <h2 style={{ fontSize: 19, marginBottom: 12 }}>What the patient said</h2>
            {data.replies.length === 0 ? <p className="muted">No replies yet.</p> : (
              <div className="stack">
                {data.replies.map((r) => <ReplyCard key={r.id} reply={r} />)}
              </div>
            )}
          </section>

          <section className="panel">
            <h2 style={{ fontSize: 19, marginBottom: 6 }}>Timeline</h2>
            <TimelineList events={timeline.data?.events ?? []} />
          </section>
        </div>

        <div className="stack-l">
          <section className="panel">
            <h2 style={{ fontSize: 19, marginBottom: 10 }}>Open tasks</h2>
            {openTasks.length === 0 ? <p className="muted">Nothing open.</p> : (
              <div className="stack" style={{ gap: 10 }}>
                {openTasks.map((t) => (
                  <div key={t.id} className="stack" style={{ gap: 4 }}>
                    <div className="spread"><Link href={`/tasks?task=${t.id}`}>{t.title}</Link><TaskStatus status={t.status} /></div>
                    <span className="small muted">{CATEGORY_LABELS[t.category]}, {t.queue.toLowerCase()} queue, {t.assignee ? `owner ${t.assignee}` : "no owner yet"}</span>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="panel">
            <h2 style={{ fontSize: 19, marginBottom: 10 }}>Appointments</h2>
            {data.appointments.length === 0 ? <p className="muted">None booked. <Link href="/schedule">Book from the schedule</Link></p> : (
              <div className="stack" style={{ gap: 10 }}>
                {data.appointments.map((a) => (
                  <div key={a.id} className="spread">
                    <span>{a.slot_label}<span className="small muted" style={{ display: "block" }}>Ref {a.reference}, booked by {a.created_by.toLowerCase()}</span></span>
                    {a.status === "CONFIRMED" ? (
                      <button className="btn btn--ghost btn--small" disabled={busy} onClick={() => {
                        const reason = window.prompt("Why is this appointment cancelled?");
                        if (reason) void post(`/v1/appointments/${a.id}/cancel`, { reason }, "Appointment cancelled; the slot is free again.");
                      }}>Cancel</button>
                    ) : <Pill>{a.status.toLowerCase()}</Pill>}
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="panel">
            <h2 style={{ fontSize: 19, marginBottom: 10 }}>Messages sent</h2>
            {data.messages.length === 0 ? <p className="muted">No messages.</p> : (
              <div className="stack" style={{ gap: 12 }}>
                {data.messages.slice(0, 12).map((m) => (
                  <div key={m.id} className="stack" style={{ gap: 4 }}>
                    <div className="spread">
                      <span className="small muted">{templateName(m.template_key)}, {m.status === "SCHEDULED" ? `for ${fmtDateTime(m.scheduled_for)}` : fmtDateTime(m.sent_at ?? m.created_at)}</span>
                      <MessageStatus status={m.status} label={m.status_label} />
                    </div>
                    <p className="small">{m.body}</p>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="panel">
            <h2 style={{ fontSize: 19, marginBottom: 10 }}>Consent</h2>
            <div className="stack" style={{ gap: 8 }}>
              {["REMINDERS", "AI_PROCESSING"].map((purpose) => {
                const granted = data.consents[purpose] === "GRANTED";
                return (
                  <div key={purpose} className="spread">
                    <span>{CONSENT_LABEL[purpose]}<span className="small muted" style={{ display: "block" }}>{granted ? "Given" : data.consents[purpose] ? "Withdrawn" : "Not recorded"}</span></span>
                    <button className="btn btn--quiet btn--small" disabled={busy}
                      onClick={() => post(`/v1/patients/${id}/consents`, { purpose, granted: !granted }, granted ? "Consent withdrawn." : "Consent recorded.")}>
                      {granted ? "Record withdrawal" : "Record consent"}
                    </button>
                  </div>
                );
              })}
              <div className="spread">
                <span>Reminder opt-out</span>
                {patient.opted_out ? (
                  <button className="btn btn--quiet btn--small" disabled={busy} onClick={() => post(`/v1/patients/${id}/opt-in`, {}, "Reminders restarted.")}>Restart reminders</button>
                ) : (
                  <button className="btn btn--danger btn--small" disabled={busy} onClick={() => post(`/v1/patients/${id}/opt-out`, {}, "Opted out. Pending reminders were suppressed.")}>Opt out for the patient</button>
                )}
              </div>
            </div>
          </section>
        </div>
      </div>

      <PlanEditor open={planOpen} patientId={id} canApprove={can("plans.approve")} onClose={() => setPlanOpen(false)}
        onSaved={() => { setPlanOpen(false); void refresh(); }} />
      <Modal open={Boolean(link)} title="Patient app link" onClose={() => setLink(null)}
        footer={<button className="btn" onClick={() => setLink(null)}>Done</button>}>
        <p>Give this link only to the patient. It works for 24 hours and asks for their year of birth.</p>
        <input type="text" readOnly value={link ?? ""} onFocus={(e) => e.currentTarget.select()} aria-label="Patient link" />
        <div className="row">
          <button className="btn btn--quiet btn--small" onClick={() => link && navigator.clipboard?.writeText(link).then(() => toast("Link copied."))}>Copy link</button>
          {link ? <a className="btn btn--quiet btn--small" href={link.replace(/^https?:\/\/[^/]+/, "")} target="_blank" rel="noreferrer">Open as the patient (demo)</a> : null}
        </div>
      </Modal>
    </>
  );
}
