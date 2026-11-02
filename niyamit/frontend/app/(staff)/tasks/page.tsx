"use client";

import { useEffect, useState } from "react";

import { CATEGORY_LABELS } from "@/components/outcomes";
import { PageHead } from "@/components/staff-shell";
import { TaskPanel } from "@/components/task-panel";
import { Empty, ErrorNote, Loading, Pill, TaskStatus } from "@/components/ui";
import { useApi } from "@/lib/api";
import { age, dueIn } from "@/lib/format";
import { useStaff } from "@/lib/staff-context";
import type { Task } from "@/lib/types";

type Scope = "open" | "mine" | "closed";

export default function TasksPage() {
  const { refreshCounts } = useStaff();
  const [scope, setScope] = useState<Scope>("open");
  const [queue, setQueue] = useState("");
  const [category, setCategory] = useState("");
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get("queue")) setQueue(q.get("queue") ?? "");
    if (q.get("task")) setSelected(q.get("task"));
  }, []);

  const params = new URLSearchParams({ status: scope === "closed" ? "closed" : "open" });
  if (scope === "mine") params.set("mine", "true");
  if (queue) params.set("queue", queue);
  if (category) params.set("category", category);
  const { data, error, loading, reload } = useApi<{ tasks: Task[] }>(`/v1/tasks?${params}`);
  const tasks = data?.tasks ?? [];

  function select(id: string | null) {
    setSelected(id);
    const url = new URL(window.location.href);
    if (id) url.searchParams.set("task", id);
    else url.searchParams.delete("task");
    window.history.replaceState(null, "", url);
  }

  return (
    <>
      <PageHead
        title="Tasks"
        lede="Every barrier, call-back request, clinical question and failed message stays here with an owner until it is closed with an outcome."
      />
      <div className="spread">
        <div className="filters" role="group" aria-label="Which tasks">
          {([["open", "Open"], ["mine", "Mine"], ["closed", "Closed"]] as [Scope, string][]).map(([k, label]) => (
            <button key={k} className="filter" aria-pressed={scope === k} onClick={() => setScope(k)}>{label}</button>
          ))}
        </div>
        <div className="row" style={{ marginBottom: 14 }}>
          <select aria-label="Queue" value={queue} onChange={(e) => setQueue(e.target.value)} style={{ width: "auto", minHeight: 32 }}>
            <option value="">All queues</option>
            <option value="RECEPTION">Reception</option>
            <option value="NURSE">Nurse</option>
            <option value="DOCTOR">Doctor</option>
          </select>
          <select aria-label="Category" value={category} onChange={(e) => setCategory(e.target.value)} style={{ width: "auto", minHeight: 32 }}>
            <option value="">All kinds</option>
            {Object.entries(CATEGORY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
      </div>
      <ErrorNote error={error} />
      {loading && !data ? <Loading /> : null}
      <div className="register" role="listbox" aria-label="Tasks">
        {data && tasks.length === 0 ? (
          <Empty title={scope === "closed" ? "No closed tasks yet" : "No open tasks"}>
            {scope === "mine" ? "Nothing is assigned to you. Pick a task from Open and choose “Assign to me”." : "When a patient reports a problem or a message fails, a task appears here."}
          </Empty>
        ) : null}
        {tasks.map((t) => (
          <div key={t.id} className="task-row" role="option" aria-selected={selected === t.id} tabIndex={0}
            onClick={() => select(t.id)} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && select(t.id)}>
            <span className={`bar bar--${t.priority}`} aria-hidden="true" />
            <div className="stack" style={{ gap: 4, minWidth: 0 }}>
              <div className="row">
                <b>{t.title}</b>
                {t.priority === "URGENT" ? <Pill tone="urgent">Urgent</Pill> : null}
              </div>
              <div className="reg-meta">
                <span>{t.patient?.name}</span>
                <span>{CATEGORY_LABELS[t.category] ?? t.category}</span>
                <span>{t.queue.charAt(0) + t.queue.slice(1).toLowerCase()} queue</span>
                <span>{t.assignee ? `Owner ${t.assignee}` : "No owner yet"}</span>
                <span>Opened {age(t.created_at)}</span>
              </div>
              {t.patient_statement ? <p className="small" style={{ color: "var(--ink-2)" }}>“{t.patient_statement.slice(0, 160)}{t.patient_statement.length > 160 ? "…" : ""}”</p> : null}
            </div>
            <div className="stack" style={{ gap: 6, justifyItems: "end" }}>
              <TaskStatus status={t.status} />
              {t.status !== "RESOLVED" && t.status !== "CANCELLED" && t.status !== "UNABLE_TO_RESOLVE" ? (
                <span className={`small ${t.overdue ? "" : "muted"}`} style={t.overdue ? { color: "var(--amber)", fontWeight: 600 } : undefined}>{dueIn(t.due_at)}</span>
              ) : null}
              {t.escalated_at && !t.resolved_at ? <Pill tone="wait">Escalated</Pill> : null}
            </div>
          </div>
        ))}
      </div>
      {selected ? (
        <TaskPanel taskId={selected} onClose={() => select(null)} onChanged={() => { void reload(); refreshCounts(); }} />
      ) : null}
    </>
  );
}
