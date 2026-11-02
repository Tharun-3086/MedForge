"use client";

import { useState, type FormEvent } from "react";

import { Modal, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import type { Plan } from "@/lib/types";

const KINDS: [string, string][] = [
  ["REVIEW_VISIT", "Review visit"], ["HBA1C_TEST", "HbA1c test"], ["EYE_EXAM", "Eye (retina) check"],
  ["FOOT_EXAM", "Foot check"], ["KIDNEY_TEST", "Kidney test"], ["MEDICINE_REFILL", "Medicine refill"], ["OTHER", "Other follow-up"],
];

type Row = { kind: string; due_date: string; label: string };

export function PlanEditor({ open, patientId, canApprove, onClose, onSaved }: {
  open: boolean; patientId: string; canApprove: boolean; onClose: () => void; onSaved: (plan: Plan) => void;
}) {
  const { busy, run } = useAction();
  const [rows, setRows] = useState<Row[]>([{ kind: "REVIEW_VISIT", due_date: "", label: "" }]);
  const [notes, setNotes] = useState("");

  function update(i: number, patch: Partial<Row>) {
    setRows((r) => r.map((row, j) => (j === i ? { ...row, ...patch } : row)));
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    const plan = await run(() => api<Plan>("/v1/follow-up-plans", {
      body: { patient_id: patientId, notes, approve: true,
        items: rows.map((r) => ({ kind: r.kind, due_date: r.due_date, label: r.label.trim() || null })) },
    }), (p) => (p.status === "ACTIVE" ? `Plan v${p.version} approved. Reminders are scheduled.` : "Plan saved. A doctor or nurse needs to approve it."));
    if (plan) {
      onSaved(plan);
      setRows([{ kind: "REVIEW_VISIT", due_date: "", label: "" }]);
      setNotes("");
    }
  }

  return (
    <Modal open={open} title="New follow-up plan" onClose={onClose}
      footer={<>
        <button className="btn btn--ghost" onClick={onClose}>Cancel</button>
        <button className="btn" type="submit" form="plan-editor" disabled={busy || rows.some((r) => !r.due_date)}>
          {canApprove ? "Approve plan" : "Save for approval"}
        </button>
      </>}>
      <form id="plan-editor" className="stack" onSubmit={save}>
        <p className="small muted">
          A new plan replaces the current one as a new version; the old version stays in the history.
          {canApprove ? " Approving schedules reminders straight away." : " Your role can draft plans; a doctor or nurse approves them."}
        </p>
        {rows.map((row, i) => (
          <div key={i} className="form-grid" style={{ gridTemplateColumns: "1.2fr 1fr 1.2fr auto", alignItems: "end" }}>
            <label className="field"><span>Follow-up</span>
              <select value={row.kind} onChange={(e) => update(i, { kind: e.target.value })}>
                {KINDS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
              </select>
            </label>
            <label className="field"><span>Due date</span>
              <input type="date" required value={row.due_date} onChange={(e) => update(i, { due_date: e.target.value })} />
            </label>
            <label className="field"><span>Label (optional)</span>
              <input type="text" value={row.label} onChange={(e) => update(i, { label: e.target.value })} />
            </label>
            <button type="button" className="btn btn--ghost btn--small" disabled={rows.length === 1}
              onClick={() => setRows((r) => r.filter((_, j) => j !== i))} aria-label={`Remove row ${i + 1}`}>Remove</button>
          </div>
        ))}
        <button type="button" className="btn btn--quiet btn--small" style={{ justifySelf: "start" }}
          onClick={() => setRows((r) => [...r, { kind: "HBA1C_TEST", due_date: r[r.length - 1]?.due_date ?? "", label: "" }])}>
          Add another follow-up
        </button>
        <label className="field"><span>Note (optional)</span>
          <input type="text" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
      </form>
    </Modal>
  );
}
