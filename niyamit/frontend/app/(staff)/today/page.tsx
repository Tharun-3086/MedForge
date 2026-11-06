"use client";

import { PriorityQueue } from "@/components/priority-queue";
import Link from "next/link";
import { useState } from "react";

import { CATEGORY_LABELS, reminderOutcome } from "@/components/outcomes";
import { PageHead } from "@/components/staff-shell";
import { Empty, ErrorNote, Loading, MessageStatus, Pill, Provenance, useToast } from "@/components/ui";
import { api, clientKey, useApi } from "@/lib/api";
import { fmtLongDay, fmtShortDate, LANGUAGE_NAME } from "@/lib/format";
import { useStaff } from "@/lib/staff-context";
import type { Message, WorklistRow } from "@/lib/types";

type View = "attention" | "overdue" | "upcoming" | "all";
const VIEWS: { key: View; label: string }[] = [
  { key: "attention", label: "Needs attention" },
  { key: "overdue", label: "Overdue" },
  { key: "upcoming", label: "Due in 7 days" },
  { key: "all", label: "All open follow-ups" },
];

function plural(n: number, one: string, many: string) {
  return `${n} ${n === 1 ? one : many}`;
}

export default function TodayPage() {
  const { me, counts, refreshCounts } = useStaff();
  const toast = useToast();
  const [view, setView] = useState<View>("attention");
  const [queue, setQueue] = useState("");
  const [failedOnly, setFailedOnly] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const params = new URLSearchParams({ days_ahead: view === "all" ? "60" : "7" });
  if (queue) params.set("queue", queue);
  if (failedOnly) params.set("channel_failures", "true");
  const { data, error, loading, reload } = useApi<{ today: string; rows: WorklistRow[]; sort: string }>(
    `/v1/worklists/${view}?${params}`,
  );

  async function remind(row: WorklistRow) {
    setBusyId(row.item.id);
    try {
      const m = await api<Message>(`/v1/patients/${row.patient.id}/reminders`, {
        body: { item_id: row.item.id, client_key: clientKey() },
      });
      const outcome = reminderOutcome(m);
      toast(`${row.patient.name}: ${outcome.text}`, outcome.fail);
      await reload();
      refreshCounts();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Could not send the reminder.", true);
    } finally {
      setBusyId(null);
    }
  }

  const rows = data?.rows ?? [];
  return (
    <>
      <PageHead
        title={counts ? fmtLongDay(counts.today) : "Today"}
        lede={counts ? (
          <>
            {plural(counts.overdue, "follow-up is", "follow-ups are")} overdue, {plural(counts.due_this_week, "is", "are")} due
            in the next 7 days and {plural(counts.open_tasks, "task is", "tasks are")} open.
          </>
        ) : null}
      />
      {["ADMIN","DOCTOR","NURSE"].includes(me.user.role) ? <PriorityQueue /> : null}
      {counts && counts.urgent_open > 0 ? (
        <p className="notice notice--fail" style={{ marginBottom: 14 }}>
          {plural(counts.urgent_open, "possible urgent concern is", "possible urgent concerns are")} waiting for a clinician.{" "}
          <Link href="/tasks?queue=DOCTOR">Open the doctor queue</Link>
        </p>
      ) : null}

      <div className="spread" style={{ marginBottom: 6 }}>
        <div className="filters" role="group" aria-label="Which follow-ups">
          {VIEWS.map((v) => (
            <button key={v.key} className="filter" aria-pressed={view === v.key} onClick={() => setView(v.key)}>
              {v.label}
              {v.key === "overdue" && counts ? <b> {counts.overdue}</b> : null}
            </button>
          ))}
        </div>
        <div className="row" style={{ marginBottom: 14 }}>
          <label className="row small">
            <span className="muted">Queue</span>
            <select value={queue} onChange={(e) => setQueue(e.target.value)} style={{ width: "auto", minHeight: 32 }}>
              <option value="">All queues</option>
              <option value="RECEPTION">Reception</option>
              <option value="NURSE">Nurse</option>
              <option value="DOCTOR">Doctor</option>
            </select>
          </label>
          <label className="check small">
            <input type="checkbox" checked={failedOnly} onChange={(e) => setFailedOnly(e.target.checked)} />
            <span>Only failed messages</span>
          </label>
        </div>
      </div>

      <ErrorNote error={error} />
      {loading && !data ? <Loading /> : null}
      {data && rows.length === 0 ? (
        <div className="register">
          <Empty title="Nothing needs attention here">
            Every follow-up in this view is confirmed, booked or not yet close. Try “All open follow-ups”.
          </Empty>
        </div>
      ) : null}
      {rows.length > 0 ? (
        <div className="register" aria-label="Follow-up worklist">
          {rows.map((row) => {
            const urgent = row.open_tasks.some((t) => t.category === "URGENT_CONCERN");
            const late = row.days_overdue > 0;
            return (
              <article key={row.item.id} className="reg-row">
                <div className={`gutter${urgent ? " gutter--urgent" : late ? " gutter--late" : ""}`}>
                  <b>{late ? row.days_overdue : row.due_in_days}</b>
                  <span>{late ? (row.days_overdue === 1 ? "day late" : "days late") : row.due_in_days === 0 ? "due today" : row.due_in_days === 1 ? "day to go" : "days to go"}</span>
                </div>
                <div className="reg-main">
                  <div className="reg-title">
                    <Link href={`/patients/${row.patient.id}`}>{row.patient.name}</Link>
                    <span className="small muted">{row.patient.external_ref}</span>
                    <span className="small muted">{LANGUAGE_NAME[row.patient.language] ?? row.patient.language}</span>
                    {row.patient.opted_out ? <Pill tone="fail">Opted out of messages</Pill> : null}
                  </div>
                  <div className="row">
                    <span>{row.item.label}, due {fmtShortDate(row.item.due_date)}</span>
                    <Pill tone={row.state.startsWith("Urgent") ? "urgent" : row.state.startsWith("New time") || row.state.startsWith("Patient confirmed") ? "done" : row.state === "No response yet" ? "neutral" : "wait"}>
                      {row.state}
                    </Pill>
                  </div>
                  {row.latest_statement ? (
                    <div className="row" style={{ alignItems: "flex-start" }}>
                      <Provenance kind="PATIENT_REPORTED" />
                      <span className="quote" style={{ borderLeft: 0, paddingLeft: 0 }}>{row.latest_statement}</span>
                    </div>
                  ) : row.latest_choice ? (
                    <div className="row">
                      <Provenance kind="PATIENT_REPORTED" label="Patient chose" />
                      <span>{row.latest_choice}</span>
                    </div>
                  ) : null}
                  <div className="reg-meta">
                    {row.open_tasks.filter((t) => t.category !== "OVERDUE_FOLLOWUP" || t.source_id === row.item.id).map((t) => (
                      <span key={t.id}>
                        <Link href={`/tasks?task=${t.id}`}>{CATEGORY_LABELS[t.category] ?? t.category}</Link>
                        {" "}for {t.queue.toLowerCase()}, {t.assignee ? `owner ${t.assignee}` : "no owner yet"}
                        {t.escalated ? ", escalated" : ""}
                      </span>
                    ))}
                    {row.last_message ? (
                      <span className="row" style={{ gap: 6 }}>
                        Last message <MessageStatus status={row.last_message.status} label={row.last_message.label} />
                      </span>
                    ) : null}
                  </div>
                </div>
                <div className="reg-actions">
                  <span className="next-action">{row.next_action}</span>
                  <div className="row">
                    {!row.patient.opted_out ? (
                      <button className="btn btn--quiet btn--small" disabled={busyId === row.item.id} onClick={() => remind(row)}>
                        {busyId === row.item.id ? "Sending…" : "Send reminder"}
                      </button>
                    ) : null}
                    <a className="btn btn--quiet btn--small" href={`tel:${row.patient.phone}`}>Call</a>
                    <Link className="btn btn--small" href={`/patients/${row.patient.id}`}>Open</Link>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      ) : null}
      {data ? <p className="small muted" style={{ marginTop: 10 }}>Sorted by {data.sort.charAt(0).toLowerCase() + data.sort.slice(1)}. No risk scores are used.</p> : null}
    </>
  );
}
