"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { PageHead } from "@/components/staff-shell";
import { Empty, ErrorNote, Loading, Modal, Pill, useAction } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { fmtShortDate, LANGUAGE_NAME } from "@/lib/format";
import { useStaff } from "@/lib/staff-context";
import type { Item, PatientBrief } from "@/lib/types";

type Row = PatientBrief & { next_item: Item | null; open_tasks: number };

export default function PatientsPage() {
  const router = useRouter();
  const { me } = useStaff();
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [adding, setAdding] = useState(false);
  const { data, error, loading } = useApi<{ patients: Row[] }>(`/v1/patients?q=${encodeURIComponent(query)}`);
  const { busy, run } = useAction();
  const [form, setForm] = useState({ display_name: "", phone: "", birth_year: "", preferred_language: "te",
    preferred_channel: "SIMULATED", external_ref: "", consent_reminders: false, consent_ai: false });

  async function create(e: FormEvent) {
    e.preventDefault();
    const created = await run(() => api<PatientBrief>("/v1/patients", {
      body: { ...form, birth_year: form.birth_year ? Number(form.birth_year) : null },
    }), "Patient added.");
    if (created) router.push(`/patients/${created.id}`);
  }

  return (
    <>
      <PageHead title="Patients" lede={me.clinic.is_synthetic ? "Synthetic demo records. Search by name, mobile number or clinic number." : "Search clinic patients by name, mobile number or clinic number."}
        actions={<button className="btn" onClick={() => setAdding(true)}>Add patient</button>} />
      <form className="row" style={{ marginBottom: 14, maxWidth: 520 }} onSubmit={(e) => { e.preventDefault(); setQuery(q); }}>
        <input type="search" placeholder="Name, mobile or clinic number" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search patients" className="grow" style={{ width: "auto", flex: 1 }} />
        <button className="btn btn--quiet" type="submit">Search</button>
      </form>
      <ErrorNote error={error} />
      {loading && !data ? <Loading /> : null}
      <div className="panel panel--flush">
        {data && data.patients.length === 0 ? <Empty title="No patients match">Check the spelling or add the patient.</Empty> : null}
        {data && data.patients.length > 0 ? (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Name</th><th>Clinic number</th><th>Language</th><th>Next follow-up</th><th>Open tasks</th><th>Messages</th></tr></thead>
              <tbody>
                {data.patients.map((p) => (
                  <tr key={p.id}>
                    <td><Link href={`/patients/${p.id}`}>{p.name}</Link><span className="small muted" style={{ display: "block" }}>{p.phone}</span></td>
                    <td>{p.external_ref}</td>
                    <td>{LANGUAGE_NAME[p.language] ?? p.language}</td>
                    <td>
                      {p.next_item ? (
                        <>
                          {p.next_item.label}, {fmtShortDate(p.next_item.due_date)}
                          {p.next_item.days_overdue > 0 ? <span className="small" style={{ color: "var(--amber)", display: "block" }}>{p.next_item.days_overdue} days late</span> : null}
                        </>
                      ) : <span className="muted">None open</span>}
                    </td>
                    <td>{p.open_tasks || <span className="muted">0</span>}</td>
                    <td>{p.opted_out ? <Pill tone="fail">Opted out</Pill> : <span className="small">{p.channel === "SIMULATED" ? "Simulated phone" : "WhatsApp"}</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>

      <Modal open={adding} title="Add a patient" onClose={() => setAdding(false)}
        footer={<>
          <button className="btn btn--ghost" onClick={() => setAdding(false)}>Cancel</button>
          <button className="btn" form="add-patient" type="submit" disabled={busy}>Add patient</button>
        </>}>
        <form id="add-patient" className="stack" onSubmit={create}>
          {me.clinic.is_synthetic ? <p className="notice notice--warn small">Use made-up details only. This demo must never hold a real patient&rsquo;s data.</p> : <p className="small">Confirm patient identity and record consent only after the patient agrees.</p>}
          <div className="form-grid">
            <label className="field"><span>Name</span>
              <input type="text" required value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
            </label>
            <label className="field"><span>Mobile number</span>
              <input type="tel" required placeholder="10 digits" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            </label>
            <label className="field"><span>Year of birth</span>
              <input type="number" min={1900} max={2026} value={form.birth_year} onChange={(e) => setForm({ ...form, birth_year: e.target.value })} />
              <small>The patient enters this to open their link.</small>
            </label>
            <label className="field"><span>Clinic number</span>
              <input type="text" value={form.external_ref} onChange={(e) => setForm({ ...form, external_ref: e.target.value })} />
            </label>
            <label className="field"><span>Language for messages</span>
              <select value={form.preferred_language} onChange={(e) => setForm({ ...form, preferred_language: e.target.value })}>
                <option value="te">Telugu</option><option value="hi">Hindi</option><option value="en">English</option>
              </select>
            </label>
            <label className="field"><span>Messages go to</span>
              <select value={form.preferred_channel} onChange={(e) => setForm({ ...form, preferred_channel: e.target.value })}>
                <option value="SIMULATED">Simulated phone (demo)</option><option value="WHATSAPP">WhatsApp (needs setup)</option>
              </select>
            </label>
          </div>
          <label className="check">
            <input type="checkbox" checked={form.consent_reminders} onChange={(e) => setForm({ ...form, consent_reminders: e.target.checked })} />
            <span>The patient agreed to receive follow-up reminders.</span>
          </label>
          <label className="check">
            <input type="checkbox" checked={form.consent_ai} onChange={(e) => setForm({ ...form, consent_ai: e.target.checked })} />
            <span>The patient agreed that their messages, voice notes and reports may be read by an AI service (Sarvam AI, India). Without this, only offline rules are used.</span>
          </label>
        </form>
      </Modal>
    </>
  );
}
