"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { PROPOSAL_STATUS } from "@/components/outcomes";
import { PageHead } from "@/components/staff-shell";
import { Empty, ErrorNote, Loading, Pill, useAction } from "@/components/ui";
import { api, usePoll, useApi } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import type { PatientBrief, Proposal } from "@/lib/types";

type Filter = "open" | "APPROVED" | "REJECTED" | "all";

export default function ReportsPage() {
  const router = useRouter();
  const [filter, setFilter] = useState<Filter>("open");
  const { data, error, loading, reload } = useApi<{ proposals: Proposal[] }>(`/v1/intake-proposals?status=${filter}`);
  const { data: pts } = useApi<{ patients: PatientBrief[] }>("/v1/patients?limit=500");
  const { busy, run } = useAction();
  const [patientId, setPatientId] = useState("");
  const [sourceType, setSourceType] = useState("PRESCRIPTION");
  const [file, setFile] = useState<File | null>(null);
  const reading = (data?.proposals ?? []).some((p) => p.status === "EXTRACTION_PENDING");
  usePoll(reading, reload, 2000);

  async function upload(e: FormEvent) {
    e.preventDefault();
    if (!file || !patientId) return;
    const form = new FormData();
    form.set("file", file);
    form.set("patient_id", patientId);
    form.set("source_type", sourceType);
    const created = await run(() => api<Proposal>("/v1/intake-artifacts", { form }), "Uploaded. The document is being read.");
    if (created) router.push(`/reports/${created.id}`);
  }

  return (
    <>
      <PageHead
        title="Report inbox"
        lede="Upload a prescription or lab report. The AI proposes follow-up dates and shows where it found each one. Nothing is scheduled until a person checks every date against the original."
      />
      <form className="panel" onSubmit={upload} style={{ marginBottom: 20 }}>
        <div className="upload-form">
          <label className="field">
            <span>Patient</span>
            <select value={patientId} onChange={(e) => setPatientId(e.target.value)} required>
              <option value="">Choose a patient</option>
              {pts?.patients.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.external_ref || p.phone})</option>)}
            </select>
          </label>
          <label className="field">
            <span>Document type</span>
            <select value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
              <option value="PRESCRIPTION">Prescription or clinic note</option>
              <option value="LAB_REPORT">Lab report</option>
              <option value="REGISTER">Register page</option>
              <option value="SPREADSHEET">Spreadsheet</option>
              <option value="OTHER">Other</option>
            </select>
          </label>
          <label className="field">
            <span>File</span>
            <input type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.xlsx,.csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
            <small>PDF (up to 10 pages), image, XLSX or CSV, at most 10 MB. Use synthetic documents only.</small>
          </label>
          <button className="btn" type="submit" disabled={busy || !file || !patientId}>{busy ? "Uploading…" : "Upload and read"}</button>
        </div>
      </form>

      <div className="filters" role="group" aria-label="Which documents">
        {([["open", "To review"], ["APPROVED", "Approved"], ["REJECTED", "Rejected"], ["all", "All"]] as [Filter, string][]).map(([k, label]) => (
          <button key={k} className="filter" aria-pressed={filter === k} onClick={() => setFilter(k)}>{label}</button>
        ))}
      </div>
      <ErrorNote error={error} />
      {loading && !data ? <Loading /> : null}
      <div className="panel panel--flush">
        {data && data.proposals.length === 0 ? <Empty title="No documents here">Upload a synthetic prescription above, or try the samples in backend/samples.</Empty> : null}
        {data && data.proposals.length > 0 ? (
          <div className="table-wrap">
            <table className="table reports-table">
              <thead>
                <tr><th>Patient</th><th>Document</th><th>Status</th><th>Read by</th><th>Received</th><th /></tr>
              </thead>
              <tbody>
                {data.proposals.map((p) => {
                  const [label, tone] = PROPOSAL_STATUS[p.status] ?? [p.status, "neutral"];
                  const unverified = p.fields.filter((f) => f.status !== "APPROVED" && f.status !== "REJECTED").length;
                  return (
                    <tr key={p.id}>
                      <td data-label="Patient">{p.patient ? <Link href={`/patients/${p.patient.id}`}>{p.patient.name}</Link> : "Not linked"}</td>
                      <td data-label="Document">
                        {p.artifact?.filename}
                        <span className="small muted" style={{ display: "block" }}>
                          {p.artifact?.source_type.toLowerCase().replace("_", " ")}{p.artifact?.uploaded_by_patient ? ", shared by the patient" : ""}
                        </span>
                      </td>
                      <td data-label="Status">
                        <Pill tone={tone}>{label}</Pill>
                        {p.status === "NEEDS_REVIEW" ? <span className="small muted" style={{ display: "block" }}>{unverified} of {p.fields.length} fields unchecked</span> : null}
                      </td>
                      <td data-label="Read by" className="small">{readerLabel(p)}</td>
                      <td data-label="Received" className="small nowrap">{fmtDateTime(p.created_at)}</td>
                      <td data-label="Action"><Link className="btn btn--small" href={`/reports/${p.id}`}>{p.status === "NEEDS_REVIEW" ? "Review" : "Open"}</Link></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </>
  );
}

function readerLabel(p: Proposal): string {
  if (!p.extractor) return "…";
  const ocr = { "pdf-text-layer": "PDF text", tesseract: "Tesseract OCR", spreadsheet: "Spreadsheet" }[p.ocr_provider] ?? p.ocr_provider;
  if (p.extractor === "rules") return `${ocr} and offline rules`;
  if (p.extractor === "sarvam-vision-extract") return "Sarvam Vision";
  return `${ocr} and ${p.extractor.replace("llm:", "")}`;
}
