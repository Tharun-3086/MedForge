"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { EvidenceViewer } from "@/components/evidence-viewer";
import { FIELD_TO_ITEM, PROPOSAL_STATUS, REVIEW_REASONS } from "@/components/outcomes";
import { PageHead } from "@/components/staff-shell";
import { ErrorNote, Loading, Pill, Provenance, useAction } from "@/components/ui";
import { api, usePoll, useApi } from "@/lib/api";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { useStaff } from "@/lib/staff-context";
import type { Field, Proposal } from "@/lib/types";

function showValue(f: Field): string {
  if (!f.value) return "No exact value";
  if (f.name === "document_type") return f.value.charAt(0) + f.value.slice(1).toLowerCase().replace(/_/g, " ");
  return /^\d{4}-\d{2}-\d{2}$/.test(f.value) ? fmtDate(f.value) : f.value;
}

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const { refreshCounts } = useStaff();
  const { data, error, loading, reload, setData } = useApi<Proposal>(`/v1/intake-proposals/${id}`);
  const { busy, run } = useAction();
  const [active, setActive] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const [chosen, setChosen] = useState<string[]>([]);
  const [notes, setNotes] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  usePoll(data?.status === "EXTRACTION_PENDING", reload, 1500);

  useEffect(() => {
    if (data && !active) setActive(data.fields.find((f) => f.status === "NEEDS_REVIEW")?.id ?? data.fields[0]?.id ?? null);
  }, [data, active]);

  if (loading && !data) return <Loading />;
  if (error) return <ErrorNote error={error} />;
  if (!data) return null;
  const p = data;
  const [statusLabel, tone] = PROPOSAL_STATUS[p.status] ?? [p.status, "neutral"];
  const open = p.status === "NEEDS_REVIEW";
  const dateFields = p.fields.filter((f) => f.name in FIELD_TO_ITEM);
  const approvedDates = dateFields.filter((f) => f.status === "APPROVED");
  const unchecked = p.fields.filter((f) => f.status === "UNVERIFIED" || f.status === "NEEDS_REVIEW").length;

  async function review(f: Field, action: "APPROVE" | "CORRECT" | "REJECT") {
    const result = await run(
      () => api<Proposal>(`/v1/intake-proposals/${id}/fields/${f.id}`, {
        method: "PATCH", body: { action, value: action === "CORRECT" ? value : null, reason },
      }),
      action === "APPROVE" ? `${f.label}: confirmed.` : action === "CORRECT" ? `${f.label}: corrected and confirmed.` : `${f.label}: rejected.`,
    );
    if (result) {
      setData(result);
      setEditing(null);
      setReason("");
      if (action !== "REJECT" && f.name in FIELD_TO_ITEM) setChosen((c) => Array.from(new Set([...c, f.id])));
    }
  }

  async function approvePlan() {
    const result = await run(() => api<Proposal>(`/v1/intake-proposals/${id}/approve`, { body: { field_ids: chosen, notes } }),
      (r) => `Plan v${r.plan?.version} is active. Reminders are scheduled.`);
    if (result) {
      setData(result);
      refreshCounts();
    }
  }

  async function reject() {
    const result = await run(() => api<Proposal>(`/v1/intake-proposals/${id}/reject`, { body: { reason: rejectReason } }), "Document rejected.");
    if (result) setData(result);
  }

  return (
    <>
      <PageHead
        title={p.artifact?.filename ?? "Document"}
        lede={<>
          {p.patient ? <Link href={`/patients/${p.patient.id}`}>{p.patient.name}</Link> : "No patient linked"}
          {", "}{p.artifact?.uploaded_by_patient ? "shared by the patient" : "uploaded by staff"} {fmtDateTime(p.created_at)}.
        </>}
        actions={<Pill tone={tone}>{statusLabel}</Pill>}
      />
      {p.status === "EXTRACTION_PENDING" ? <p className="notice" aria-live="polite">Reading the document. This page updates by itself.</p> : null}
      {p.status === "EXTRACTION_FAILED" ? (
        <div className="notice notice--fail stack" style={{ marginBottom: 16 }}>
          <span>The document could not be read ({p.error_code || "unknown error"}). {p.notes.join(" ")}</span>
          <div className="row">
            <button className="btn btn--quiet btn--small" disabled={busy} onClick={() => run(() => api<Proposal>(`/v1/intake-proposals/${id}/retry`, { method: "POST" }), "Trying again.").then((r) => r && setData(r))}>Try again</button>
            <span className="small">Or enter the plan by hand from the patient record.</span>
          </div>
        </div>
      ) : null}
      {p.notes.length > 0 && p.status !== "EXTRACTION_FAILED" ? (
        <div className={`notice ${p.notes.some((n) => n.includes("instruction-like")) ? "notice--warn" : ""}`} style={{ marginBottom: 16 }}>
          {p.notes.map((n, i) => <p key={i}>{n}</p>)}
        </div>
      ) : null}
      {p.plan_id ? (
        <p className="notice notice--ok" style={{ marginBottom: 16 }}>
          Approved into a follow-up plan. {p.patient ? <Link href={`/patients/${p.patient.id}`}>See the plan and reminders</Link> : null}
        </p>
      ) : null}

      <div className="review">
        <EvidenceViewer proposal={p} activeField={active} onPick={setActive} />

        <div className="stack">
          <div className="spread">
            <h2 style={{ fontSize: 19 }}>Proposed fields</h2>
            <span className="small muted">Read by {p.extractor === "rules" ? `${p.ocr_provider === "pdf-text-layer" ? "PDF text" : "Tesseract OCR"} and offline rules` : p.extractor}</span>
          </div>
          {open ? <p className="small muted">{unchecked > 0 ? `${unchecked} field${unchecked === 1 ? "" : "s"} still need a person to check them.` : "Every field has been checked."}</p> : null}
          {p.fields.map((f) => (
            <div key={f.id} className="field-card" data-status={f.status} aria-current={f.id === active} onClick={() => setActive(f.id)}>
              <div className="spread">
                <span className="small muted">{f.label}</span>
                <Provenance kind={f.status === "APPROVED" ? "STAFF_CONFIRMED" : "AI_PROPOSED"}
                  label={f.status === "APPROVED" ? "Staff confirmed" : f.status === "REJECTED" ? "Rejected" : undefined} />
              </div>
              <span className="field-value">{showValue(f)}</span>
              {f.name === "document_type" ? (
                <span className="source-quote">Based on: “{p.blocks?.find((b) => b.id === f.evidence.block_ids?.[0])?.text ?? f.extracted_value}”</span>
              ) : f.extracted_value ? (
                <span className="source-quote">Written as: “{f.extracted_value}”{f.evidence.page ? `, page ${f.evidence.page}` : ""}</span>
              ) : null}
              {f.evidence.computed ? <span className="small muted">{f.evidence.computed}</span> : null}
              {f.status === "APPROVED" && f.proposed_value !== f.value ? <span className="small">Corrected from {f.proposed_value ? fmtDate(f.proposed_value) : "no value"}</span> : null}
              {f.review_reasons.map((r) => <span key={r} className="small" style={{ color: "var(--amber)" }}>{REVIEW_REASONS[r] ?? r}</span>)}
              {open && f.status !== "APPROVED" && f.status !== "REJECTED" ? (
                editing === f.id ? (
                  <div className="stack" onClick={(e) => e.stopPropagation()}>
                    {f.name === "document_type" ? (
                      <select value={value} onChange={(e) => setValue(e.target.value)}>
                        {["PRESCRIPTION", "LAB_REPORT", "DISCHARGE_SUMMARY", "REGISTER", "OTHER"].map((v) => <option key={v} value={v}>{v.toLowerCase().replace("_", " ")}</option>)}
                      </select>
                    ) : (
                      <input type="date" value={value} onChange={(e) => setValue(e.target.value)} aria-label={`Correct ${f.label}`} />
                    )}
                    <input type="text" placeholder="Why the correction (required)" value={reason} onChange={(e) => setReason(e.target.value)} />
                    <div className="row">
                      <button className="btn btn--small" disabled={busy || !value || !reason.trim()} onClick={() => review(f, "CORRECT")}>Save correction</button>
                      <button className="btn btn--ghost btn--small" onClick={() => setEditing(null)}>Cancel</button>
                    </div>
                  </div>
                ) : (
                  <div className="row" onClick={(e) => e.stopPropagation()}>
                    <button className="btn btn--small" disabled={busy || !f.value} onClick={() => review(f, "APPROVE")}>Matches the original</button>
                    <button className="btn btn--quiet btn--small" disabled={busy} onClick={() => { setEditing(f.id); setValue(f.value ?? ""); setReason(""); }}>Correct</button>
                    <button className="btn btn--ghost btn--small" disabled={busy} onClick={() => review(f, "REJECT")}>Reject</button>
                  </div>
                )
              ) : null}
            </div>
          ))}

          {open ? (
            <section className="panel stack">
              <h3>Make it the follow-up plan</h3>
              {approvedDates.length === 0 ? (
                <p className="small muted">Confirm at least one follow-up date above. Only confirmed dates can go into the plan.</p>
              ) : (
                <div className="stack" style={{ gap: 6 }}>
                  {approvedDates.map((f) => (
                    <label key={f.id} className="check">
                      <input type="checkbox" checked={chosen.includes(f.id)} onChange={(e) => setChosen((c) => e.target.checked ? [...c, f.id] : c.filter((x) => x !== f.id))} />
                      <span>{FIELD_TO_ITEM[f.name]} by {showValue(f)}</span>
                    </label>
                  ))}
                </div>
              )}
              <label className="field">
                <span>Note for the plan (optional)</span>
                <input type="text" value={notes} onChange={(e) => setNotes(e.target.value)} />
              </label>
              {p.can_approve ? (
                <button className="btn btn--approve" disabled={busy || chosen.length === 0} onClick={approvePlan}>Approve plan and schedule reminders</button>
              ) : (
                <p className="notice">A doctor or nurse approves plans in this clinic. Your checks above are saved for them.</p>
              )}
              <details>
                <summary className="small" style={{ cursor: "pointer" }}>Reject the whole document</summary>
                <div className="row" style={{ marginTop: 8 }}>
                  <input type="text" placeholder="Reason, for example: wrong patient" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} />
                  <button className="btn btn--danger btn--small" disabled={busy || rejectReason.trim().length < 3} onClick={reject}>Reject document</button>
                </div>
              </details>
            </section>
          ) : null}
        </div>
      </div>
    </>
  );
}
