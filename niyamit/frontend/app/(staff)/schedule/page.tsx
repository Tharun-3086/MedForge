"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { PageHead } from "@/components/staff-shell";
import { Empty, ErrorNote, Loading, Pill, useAction } from "@/components/ui";
import { api, clientKey, useApi } from "@/lib/api";
import { fmtDateTime, fmtLongDay } from "@/lib/format";
import { useStaff } from "@/lib/staff-context";
import type { AppointmentRequest, PatientBrief, Slot } from "@/lib/types";

const REQUEST_TONE: Record<string, "wait" | "info" | "fail" | "done" | "neutral"> = {
  REQUESTED: "info", NEEDS_CLARIFICATION: "wait", SLOTS_OFFERED: "wait", HANDED_TO_STAFF: "fail", BOOKED: "done",
};

export default function SchedulePage() {
  const { counts, refreshCounts } = useStaff();
  const requests = useApi<{ requests: AppointmentRequest[] }>("/v1/appointment-requests?status=open");
  const { data: pts } = useApi<{ patients: PatientBrief[] }>("/v1/patients?limit=500");
  const [day, setDay] = useState<string>("");
  const [windowName, setWindowName] = useState("");
  const query = new URLSearchParams();
  if (day) query.set("date", day);
  if (windowName) query.set("window", windowName);
  const slots = useApi<{ slots: Slot[]; source: string }>(`/v1/availability?${query}`);
  const { busy, run } = useAction();
  const [patientId, setPatientId] = useState("");
  const [requestId, setRequestId] = useState<string | null>(null);
  const [slotId, setSlotId] = useState<string | null>(null);
  const [dayWords, setDayWords] = useState("");
  const [offered, setOffered] = useState<{ slots: Slot[]; question: string | null; request: AppointmentRequest } | null>(null);

  const byDay = useMemo(() => {
    const groups = new Map<string, Slot[]>();
    (slots.data?.slots ?? []).forEach((s) => groups.set(s.date, [...(groups.get(s.date) ?? []), s]));
    return Array.from(groups.entries());
  }, [slots.data]);

  function pickRequest(r: AppointmentRequest) {
    setRequestId(r.id);
    setPatientId(r.patient?.id ?? "");
    setDay(r.requested_date ?? "");
    setSlotId(null);
    document.getElementById("book")?.scrollIntoView({ behavior: "smooth" });
  }

  async function book() {
    if (!patientId || !slotId) return;
    const result = await run(() => api<{ appointment: { reference: string } }>("/v1/appointments", {
      body: { patient_id: patientId, slot_id: slotId, request_id: requestId, client_key: clientKey() },
    }), (r) => `Booked. Reference ${r.appointment.reference}. The patient gets a confirmation message.`);
    if (result) {
      setSlotId(null);
      setRequestId(null);
      setOffered(null);
      await Promise.all([requests.reload(), slots.reload()]);
      refreshCounts();
    } else {
      await slots.reload();
    }
  }

  async function ask() {
    const result = await run(() => api<{ slots: Slot[]; question: string | null; request: AppointmentRequest }>("/v1/appointment-requests", {
      body: { patient_id: patientId, day_text: dayWords },
    }));
    if (result) {
      setOffered(result);
      setRequestId(result.request.id);
      void requests.reload();
    }
  }

  const choosable = offered ? offered.slots : null;

  return (
    <>
      <PageHead title="Schedule"
        lede={<>Only times from the clinic&rsquo;s availability are offered, and nothing is confirmed until the booking is saved with a reference. {counts?.waiting_on_patient_choice ? `${counts.waiting_on_patient_choice} patient${counts.waiting_on_patient_choice === 1 ? " is" : "s are"} choosing a time in the app.` : ""}</>} />

      <section className="panel" style={{ marginBottom: 20 }}>
        <h2 style={{ fontSize: 19, marginBottom: 10 }}>Requests waiting for a time</h2>
        <ErrorNote error={requests.error} />
        {requests.loading && !requests.data ? <Loading /> : null}
        {requests.data && requests.data.requests.length === 0 ? <Empty title="No open requests">When a patient asks to change a date, the request appears here until it is booked.</Empty> : null}
        {requests.data && requests.data.requests.length > 0 ? (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Patient</th><th>Asked for</th><th>Status</th><th>From</th><th>Received</th><th /></tr></thead>
              <tbody>
                {requests.data.requests.map((r) => (
                  <tr key={r.id}>
                    <td>{r.patient ? <Link href={`/patients/${r.patient.id}`}>{r.patient.name}</Link> : null}</td>
                    <td>
                      {r.requested_day_text ? `“${r.requested_day_text}”` : "Any time"}
                      {r.requested_date ? <span className="small muted" style={{ display: "block" }}>{fmtLongDay(r.requested_date)}</span> : null}
                      {r.patient_statement ? <span className="small muted" style={{ display: "block" }}>{r.patient_statement}</span> : null}
                    </td>
                    <td><Pill tone={REQUEST_TONE[r.status] ?? "neutral"}>{r.status_label}</Pill>{r.failure_reason ? <span className="small muted" style={{ display: "block" }}>{r.failure_reason.toLowerCase().replace(/_/g, " ")}</span> : null}</td>
                    <td className="small">{r.requested_by.toLowerCase()}</td>
                    <td className="small nowrap">{fmtDateTime(r.created_at)}</td>
                    <td><button className="btn btn--small" onClick={() => pickRequest(r)}>Book a time</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <section id="book" className="panel stack">
        <h2 style={{ fontSize: 19 }}>Book a time</h2>
        <div className="form-grid">
          <label className="field"><span>Patient</span>
            <select value={patientId} onChange={(e) => { setPatientId(e.target.value); setRequestId(null); setOffered(null); }}>
              <option value="">Choose a patient</option>
              {pts?.patients.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.external_ref})</option>)}
            </select>
          </label>
          <label className="field"><span>Day</span>
            <input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
          </label>
          <label className="field"><span>Time of day</span>
            <select value={windowName} onChange={(e) => setWindowName(e.target.value)}>
              <option value="">Any</option><option value="MORNING">Morning</option><option value="AFTERNOON">Afternoon</option><option value="EVENING">Evening</option>
            </select>
          </label>
        </div>
        <div className="field" style={{ maxWidth: 640 }}>
          <span>Or type what the patient said</span>
          <form className="row" style={{ flexWrap: "nowrap" }} onSubmit={(e) => { e.preventDefault(); void ask(); }}>
            <input type="text" placeholder="Saturday morning, repu, 12 tareekh" value={dayWords} onChange={(e) => setDayWords(e.target.value)} style={{ flex: 1, width: "auto", minWidth: 0 }} />
            <button type="submit" className="btn btn--quiet" disabled={busy || !patientId || !dayWords.trim()}>Find times</button>
          </form>
          <small>Understood the same way as a patient&rsquo;s message, in English, Hindi or Telugu mixed with English.</small>
        </div>
        {requestId ? <p className="small">Booking for an open request. It closes when the booking is saved.</p> : null}
        {offered?.question ? <p className="notice notice--warn">{offered.question}</p> : null}
        {offered && offered.request.status === "HANDED_TO_STAFF" ? <p className="notice notice--fail">The booking service is unavailable or has no free times. A task was created; arrange the time by phone.</p> : null}
        <ErrorNote error={slots.error} />
        {choosable ? (
          <SlotGrid groups={[["Offered times", choosable]]} selected={slotId} onSelect={setSlotId} />
        ) : byDay.length ? (
          <SlotGrid groups={byDay.map(([d, s]) => [fmtLongDay(d), s])} selected={slotId} onSelect={setSlotId} />
        ) : slots.data ? <p className="muted">No open times for this choice.</p> : null}
        <div className="row">
          <button className="btn" disabled={busy || !patientId || !slotId} onClick={book}>Book and send confirmation</button>
          <span className="small muted">{slots.data?.source}</span>
        </div>
      </section>
    </>
  );
}

function SlotGrid({ groups, selected, onSelect }: { groups: [string, Slot[]][]; selected: string | null; onSelect: (id: string) => void }) {
  return (
    <div className="stack" style={{ gap: 10 }}>
      {groups.map(([label, list]) => (
        <div key={label} className="stack" style={{ gap: 6 }}>
          <span className="small" style={{ fontWeight: 600 }}>{label}</span>
          <div className="row">
            {list.map((s) => (
              <button key={s.id} className="filter" aria-pressed={selected === s.id} onClick={() => onSelect(s.id)} title={s.provider}>
                {label === "Offered times" ? s.label : s.label.split(", ").slice(-1)[0]}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
