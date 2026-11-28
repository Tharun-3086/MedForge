"use client";

import Link from "next/link";
import { useApi, usePoll } from "@/lib/api";
import { useEffect, useRef, useState } from "react";
import { ErrorNote, useToast } from "@/components/ui";
import { TaskPanel } from "@/components/task-panel";
import { useStaff } from "@/lib/staff-context";
import type { Task } from "@/lib/types";

export function ClinicalInbox() {
  const questions = useApi<{ tasks: Task[] }>("/v1/tasks?category=CLINICAL_QUESTION&status=open");
  const urgent = useApi<{ tasks: Task[] }>("/v1/tasks?category=URGENT_CONCERN&status=open");
  const [selected, setSelected] = useState<string | null>(null);
  const { refreshCounts } = useStaff();
  const reload = () => { void questions.reload(); void urgent.reload(); refreshCounts(); };
  usePoll(true, () => { void questions.reload(); void urgent.reload(); }, 10000);
  const rows = [...(urgent.data?.tasks ?? []), ...(questions.data?.tasks ?? [])];
  const toast = useToast();
  const seen = useRef<Set<string>>(new Set());
  const notified = useRef(false);
  useEffect(() => {
    if (!questions.data || !urgent.data) return;
    const added = rows.filter(task => !seen.current.has(task.id));
    if (added.length) toast(notified.current ? `${added.length} new patient question${added.length === 1 ? "" : "s"} — open Read & reply below.` : `${rows.length} patient question${rows.length === 1 ? "" : "s"} awaiting clinical review.`, added.some(task => task.category === "URGENT_CONCERN"));
    seen.current = new Set(rows.map(task => task.id));
    notified.current = true;
  }, [questions.data, urgent.data, toast]);
  return <section className="panel stack" style={{ marginBottom: 20 }}>
    <div className="spread"><h2>Patient questions &amp; concerns ({rows.length})</h2><button className="btn btn--quiet" onClick={reload}>Refresh inbox</button></div>
    <p className="small muted">All clinical queues, including patients without an active follow-up. The original message is preserved. A clinician assesses urgency.</p>
    <ErrorNote error={questions.error ?? urgent.error} />
    {!rows.length ? <p>No open patient questions.</p> : rows.slice(0, 8).map(task => <div key={task.id} className="panel stack">
      <div className="spread"><b>{task.patient?.name} · {task.category === "URGENT_CONCERN" ? "Possible urgent concern" : "Awaiting clinical response"}</b><button className="btn btn--small" onClick={() => setSelected(task.id)}>Read &amp; reply</button></div>
      <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{task.patient_statement}</p>
      <span className="small muted">{task.queue} queue · {task.assignee ?? "Unassigned"}</span>
    </div>)}
    {rows.length > 8 ? <Link href="/tasks">View all tasks</Link> : null}
    {selected ? <TaskPanel taskId={selected} onClose={() => setSelected(null)} onChanged={reload} /> : null}
  </section>;
}

