"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ACTION_STATUS_LABELS, BARRIER_LABELS, CATEGORY_LABELS, INTENT_LABELS, OUTCOME_LABELS } from "@/components/outcomes";
import { ErrorNote, Loading, MessageStatus, Pill, Provenance, ReplyStatus, TaskStatus, useAction } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { dueIn, fmtDateTime } from "@/lib/format";
import { useStaff } from "@/lib/staff-context";
import type { AppointmentRequest, Message, Reply, StaffMember, Task } from "@/lib/types";

const OPEN = ["OPEN", "ASSIGNED", "IN_PROGRESS"];

export function TaskPanel({ taskId, onClose, onChanged }: { taskId: string; onClose: () => void; onChanged: () => void }) {
  const { me } = useStaff();
  const { data: task, error, reload, setData } = useApi<Task>(`/v1/tasks/${taskId}`);
  const { data: staffList } = useApi<{ staff: StaffMember[] }>("/v1/clinic/staff");
  const { busy, run } = useAction();
  const [mode, setMode] = useState<"" | "resolve" | "unable" | "cancel" | "assign" | "reopen">("");
  const [outcome, setOutcome] = useState("");
  const [note, setNote] = useState("");
  const [assignee, setAssignee] = useState("");

  useEffect(() => {
    setMode("");
    setNote("");
    setOutcome("");
  }, [taskId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function act(path: string, body: unknown, success: string) {
    const result = await run(() => api<Task>(`/v1/tasks/${taskId}/${path}`, { body }), success);
    if (result) {
      setData(result);
      setMode("");
      setNote("");
      onChanged();
    }
  }

  const clinical = task ? ["CLINICAL_QUESTION", "URGENT_CONCERN"].includes(task.category) : false;
  const isOpen = task ? OPEN.includes(task.status) : false;

  return (
    <>
      <div className="drawer-scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="task-title">
        <div className="spread">
          <div className="row">
            {task ? <TaskStatus status={task.status} /> : null}
            {task?.priority === "URGENT" ? <Pill tone="urgent">Urgent</Pill> : null}
            {task?.escalated_at && isOpen ? <Pill tone="wait">Escalated: past due, no owner</Pill> : null}
          </div>
          <button className="btn btn--ghost btn--small" onClick={onClose}>Close</button>
        </div>
        <ErrorNote error={error} />
        {!task ? <Loading /> : (
          <>
            <div className="stack" style={{ gap: 6 }}>
              <span className="small muted">{CATEGORY_LABELS[task.category] ?? task.category} for the {task.queue.toLowerCase()} queue</span>
              <h2 id="task-title" style={{ fontSize: 20 }}>{task.title}</h2>
              {task.patient ? (
                <div className="row">
                  <Link href={`/patients/${task.patient.id}`}>{task.patient.name}</Link>
                  <a className="btn btn--quiet btn--small" href={`tel:${task.patient.phone}`}>Call {task.patient.phone}</a>
                </div>
              ) : null}
            </div>

            {task.patient_statement ? (
              <div className="stack" style={{ gap: 6 }}>
                <Provenance kind="PATIENT_REPORTED" />
                <p className="quote">{task.patient_statement}</p>
                {task.barrier_category ? <span className="small muted">Barrier category chosen: {BARRIER_LABELS[task.barrier_category] ?? task.barrier_category}</span> : null}
              </div>
            ) : null}

            <dl className="kv">
              <dt>Owner</dt>
              <dd>{task.assignee ?? "No owner yet"}</dd>
              <dt>Due</dt>
              <dd>{fmtDateTime(task.due_at)}{isOpen ? ` (${dueIn(task.due_at)})` : ""}</dd>
              <dt>Created</dt>
              <dd>{fmtDateTime(task.created_at)}</dd>
              {task.outcome ? (<><dt>Outcome</dt><dd>{OUTCOME_LABELS[task.outcome] ?? task.outcome}{task.outcome_note ? `: ${task.outcome_note}` : ""}</dd></>) : null}
            </dl>

            <SourceDetails task={task} />

            {isOpen ? (
              <div className="stack">
                <div className="row">
                  {task.assignee_user_id !== me.user.id ? (
                    <button className="btn btn--quiet" disabled={busy} onClick={() => act("assign", { note: "Took ownership" }, "You own this task now.")}>
                      Assign to me
                    </button>
                  ) : null}
                  <button className="btn btn--quiet" disabled={busy} onClick={() => setMode(mode === "assign" ? "" : "assign")}>Reassign</button>
                  {task.status !== "IN_PROGRESS" ? (
                    <button className="btn btn--quiet" disabled={busy} onClick={() => act("start", {}, "Marked in progress.")}>Start</button>
                  ) : null}
                </div>
                <div className="row">
                  <button className="btn" disabled={busy || (clinical && !["DOCTOR", "NURSE"].includes(me.user.role))}
                    onClick={() => { setMode("resolve"); setOutcome(clinical ? "ANSWERED_BY_CLINICIAN" : ""); }}>
                    Resolve with outcome
                  </button>
                  <button className="btn btn--quiet" disabled={busy} onClick={() => { setMode("unable"); setOutcome("NO_ANSWER"); }}>Unable to resolve</button>
                  <button className="btn btn--ghost" disabled={busy} onClick={() => setMode("cancel")}>Cancel task</button>
                </div>
                {clinical && !["DOCTOR", "NURSE"].includes(me.user.role) ? (
                  <p className="small muted">A clinician must close clinical questions.</p>
                ) : null}
              </div>
            ) : (
              <button className="btn btn--quiet" style={{ justifySelf: "start" }} onClick={() => setMode("reopen")}>Reopen</button>
            )}

            {mode === "assign" ? (
              <form className="panel stack" onSubmit={(e) => { e.preventDefault(); void act("assign", { assignee_user_id: assignee, note }, "Task reassigned."); }}>
                <label className="field">
                  <span>Give this task to</span>
                  <select value={assignee} onChange={(e) => setAssignee(e.target.value)} required>
                    <option value="">Choose a person</option>
                    {staffList?.staff.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.role.toLowerCase()})</option>)}
                  </select>
                </label>
                <label className="field">
                  <span>Reason</span>
                  <input type="text" value={note} onChange={(e) => setNote(e.target.value)} required placeholder="For example: speaks Telugu, knows the family" />
                </label>
                <button className="btn" disabled={busy} type="submit">Reassign</button>
              </form>
            ) : null}

            {mode === "resolve" || mode === "unable" ? (
              <form className="panel stack" onSubmit={(e) => { e.preventDefault(); void act(mode, { outcome, note }, mode === "resolve" ? "Task resolved." : "Recorded as unable to resolve."); }}>
                <label className="field">
                  <span>Outcome</span>
                  <select value={outcome} onChange={(e) => setOutcome(e.target.value)} required>
                    <option value="">Choose what happened</option>
                    {Object.entries(OUTCOME_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span>Note</span>
                  <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="What was said or done. Required for 'Other'." />
                </label>
                <button className="btn" disabled={busy || !outcome} type="submit">{mode === "resolve" ? "Resolve task" : "Save as unable to resolve"}</button>
              </form>
            ) : null}

            {mode === "cancel" || mode === "reopen" ? (
              <form className="panel stack" onSubmit={(e) => { e.preventDefault(); void act(mode, { note }, mode === "cancel" ? "Task cancelled." : "Task reopened."); }}>
                <label className="field">
                  <span>Reason</span>
                  <input type="text" value={note} onChange={(e) => setNote(e.target.value)} required />
                </label>
                <button className="btn" disabled={busy || !note.trim()} type="submit">{mode === "cancel" ? "Cancel task" : "Reopen task"}</button>
              </form>
            ) : null}

            <section className="stack" style={{ gap: 8 }}>
              <h3 style={{ fontSize: 15 }}>History</h3>
              <ol className="events">
                {(task.events ?? []).map((e, i) => (
                  <li key={i}>
                    <span>{e.from && e.from !== e.to ? `${e.from.toLowerCase().replace(/_/g, " ")} to ` : ""}<b>{e.to.toLowerCase().replace(/_/g, " ")}</b></span>
                    <span className="muted small" style={{ display: "block" }}>{e.by}, {fmtDateTime(e.at)}{e.note ? `: ${e.note}` : ""}</span>
                  </li>
                ))}
              </ol>
            </section>
            <button className="btn btn--ghost btn--small" style={{ justifySelf: "start" }} onClick={() => void reload()}>Refresh</button>
          </>
        )}
      </aside>
    </>
  );
}

function SourceDetails({ task }: { task: Task }) {
  const src = task.source;
  if (!src) return null;
  if (task.source_type === "patient_reply") {
    const r = src as Reply;
    const ai = r.understanding_source.startsWith("LLM");
    return (
      <section className="panel stack" style={{ gap: 8 }}>
        <div className="spread">
          <h3 style={{ fontSize: 15 }}>The message behind this task</h3>
          <ReplyStatus status={r.status} />
        </div>
        <p className="small muted">{r.input_mode === "VOICE" ? "Voice note" : r.input_mode === "BUTTON" ? "Button tap" : "Text"} {r.channel === "PATIENT_APP" ? "in the patient app" : r.channel === "SIMULATED" ? "on the simulated phone" : `on ${r.channel.toLowerCase()}`}, {fmtDateTime(r.created_at)}</p>
        {r.input_mode === "BUTTON" && r.choice_label ? <p><span className="small muted">Chose: </span>{r.choice_label}</p> : null}
        {r.transcript ? <p><span className="small muted">Transcript: </span>{r.transcript}</p> : null}
        <div className="row">
          <Provenance kind={r.understanding_source === "BUTTON" ? "PATIENT_REPORTED" : "AI_PROPOSED"}
            label={r.understanding_source === "BUTTON" ? "Patient tapped a button" : ai ? `Understood by ${r.understanding_source.split(":")[1]}` : "Understood by offline rules"} />
          {(r.understanding.intents ?? []).map((i) => <Pill key={i}>{INTENT_LABELS[i] ?? i}</Pill>)}
          {typeof r.understanding.confidence === "number" && r.understanding_source !== "BUTTON" ? <span className="small muted">confidence {Math.round(r.understanding.confidence * 100)}%</span> : null}
        </div>
        {r.understanding.english_gloss ? <p className="small"><span className="muted">AI gloss: </span>{r.understanding.english_gloss}</p> : null}
        {r.actions.map((a, i) => (
          <p key={i} className="small">{INTENT_LABELS[a.intent] ?? a.intent}: {ACTION_STATUS_LABELS[a.status] ?? a.status}</p>
        ))}
        {r.provider_notes.map((n, i) => <p key={i} className="small muted">{n}</p>)}
      </section>
    );
  }
  if (task.source_type === "appointment_request") {
    const q = src as AppointmentRequest;
    return (
      <section className="panel stack" style={{ gap: 6 }}>
        <h3 style={{ fontSize: 15 }}>Appointment request</h3>
        <p>{q.status_label}{q.requested_day_text ? `. Asked for “${q.requested_day_text}”` : ""}{q.failure_reason ? `. Reason: ${q.failure_reason.toLowerCase().replace(/_/g, " ")}` : ""}</p>
        <Link href="/schedule">Book a time on the schedule</Link>
      </section>
    );
  }
  if (task.source_type === "outbound_message") {
    const m = src as Message;
    return (
      <section className="panel stack" style={{ gap: 6 }}>
        <div className="spread">
          <h3 style={{ fontSize: 15 }}>Message</h3>
          <MessageStatus status={m.status} label={m.status_label} />
        </div>
        <p className="small">{m.body}</p>
        {m.last_error_code ? <p className="small muted">Error: {m.last_error_code}</p> : null}
      </section>
    );
  }
  return null;
}
