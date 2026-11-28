"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useAction } from "@/components/ui";
import type { Proposal } from "@/lib/types";

export function MissingReportField({ proposal, onSaved }: { proposal: Proposal; onSaved: (p: Proposal) => void }) {
  const [name, setName] = useState("blood_glucose");
  const [label, setLabel] = useState("");
  const [value, setValue] = useState("");
  const [quote, setQuote] = useState("");
  const [page, setPage] = useState(1);
  const [reason, setReason] = useState("");
  const { busy, run } = useAction();
  return <details className="panel" style={{ marginBottom: 18 }}>
    <summary>Add a missed reading from the original</summary>
    <form className="stack" onSubmit={async e => {
      e.preventDefault();
      const result = await run(() => api<Proposal>(`/v1/intake-proposals/${proposal.id}/fields`, {
        body: { name, label, value, quote, page, reason },
      }), "Reading checked and added by clinician. Patient and clinic records now use the same result.");
      if (result) { onSaved(result); setValue(""); setQuote(""); setReason(""); }
    }}>
      <p className="small">Compare the original first. Blood sugar is glucose: choose fasting, post-meal or random only when specified. Add other numeric lab tests with their exact units; clinical observations remain report-only. Correct existing fields instead of adding duplicates.</p>
      <label className="field"><span>Measurement</span><select value={name} onChange={e => setName(e.target.value)}>
        {proposal.measurement_options?.map(option => <option key={option.name} value={option.name}>{option.label}</option>)}
        <option value="custom_measurement">Other laboratory result (health numbers)</option>
        <option value="clinical_observation">Other clinical observation (report only)</option>
      </select></label>
      {["clinical_observation","custom_measurement"].includes(name) ? <label className="field"><span>Test or observation name</span><input required maxLength={80} value={label} onChange={e => setLabel(e.target.value)} /></label> : null}
      <label className="field"><span>Result including unit</span><input required maxLength={200} placeholder="75 mg/dL" value={value} onChange={e => setValue(e.target.value)} /></label>
      <label className="field"><span>Source page</span><input required type="number" min={1} value={page} onChange={e => setPage(Number(e.target.value))} /></label>
      <label className="field"><span>Copy the source text / row</span><textarea required maxLength={300} value={quote} onChange={e => setQuote(e.target.value)} /></label>
      <label className="field"><span>Verification note</span><input required minLength={3} maxLength={300} placeholder="Checked against the original; OCR omitted this result" value={reason} onChange={e => setReason(e.target.value)} /></label>
      <button className="btn" disabled={busy || !value.trim() || !quote.trim() || reason.trim().length < 3}>Confirm and add reading</button>
    </form>
  </details>;
}
