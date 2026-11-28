"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

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
  const { me, counts, refreshCounts } = useStaff();
  const requests = useApi<{ requests: AppointmentRequest[] }>("/v1/appointment-requests?status=open");
  const { data: pts } = useApi<{ patients: PatientBrief[] }>("/v1/patients?limit=500");
  const [day, setDay] = useState<string>("");
  const query = new URLSearchParams();
  if (day) query.set("date", day);
  const slots = useApi<{ slots: Slot[]; source: string }>(`/v1/availability?${query}`);
  const { busy, run } = useAction();
  const [patientId, setPatientId] = useState("");
  const [timeChoice, setTimeChoice] = useState("");
  const [provider, setProvider] = useState(me.user.name);
  const [moveContext,setMoveContext]=useState<{task:string;appointment:string;action:"POSTPONE"|"PREPONE"}|null>(null);
  const [patientMessage,setPatientMessage]=useState("");
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const patient = params.get("patient");
    if (patient) setPatientId(patient);
    if (params.get("date")) setDay(params.get("date")!);
    if(params.get("task")&&params.get("appointment")&&["POSTPONE","PREPONE"].includes(params.get("move")??""))setMoveContext({task:params.get("task")!,appointment:params.get("appointment")!,action:params.get("move") as "POSTPONE"|"PREPONE"});
  }, []);
  const [requestId, setRequestId] = useState<string | null>(null);
  const [slotId, setSlotId] = useState<string | null>(null);
  const [dayWords, setDayWords] = useState("");
  const [offered, setOffered] = useState<{ slots: Slot[]; question: string | null; request: AppointmentRequest } | null>(null);

  function withinClinicHours(slot: Slot) {
    const clock = new Intl.DateTimeFormat("en-GB", { timeZone: me.clinic.timezone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(slot.starts_at));
    return clock >= "11:00" && clock <= "19:00";
  }

  const byDay = useMemo(() => {
    const groups = new Map<string, Slot[]>();
    (slots.data?.slots ?? []).filter(withinClinicHours).forEach((s) => groups.set(s.date, [...(groups.get(s.date) ?? []), s]));
    return Array.from(groups.entries());
  }, [slots.data]);

  function pickRequest(r: AppointmentRequest) {
    setRequestId(r.id);
    setPatientId(r.patient?.id ?? "");
    setDay(r.requested_date ?? "");
    setSlotId(null);
    setTimeChoice("");
    setOffered(null);
    document.getElementById("book")?.scrollIntoView({ behavior: "smooth" });
  }

  async function book() {
    if (!patientId || (!slotId && (!day || !timeChoice || !provider.trim()))) return;
    const result = await run(async () => {
      let chosenId = slotId;
      if (!chosenId && timeChoice.startsWith("clock:")) {
        const clock = timeChoice.slice(6);
        chosenId = (slots.data?.slots ?? []).find(slot => slot.date === day &&
          slot.provider.trim().toLowerCase() === provider.trim().toLowerCase() &&
          new Intl.DateTimeFormat("en-GB", { timeZone: me.clinic.timezone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(slot.starts_at)) === clock)?.id ?? null;
      }
      if (!chosenId) {
        const created = await api<Slot>("/v1/availability", {
          body: { starts_at: `${day}T${timeChoice.replace("clock:", "")}:00`, provider_label: provider.trim() },
        });
        chosenId = created.id;
        setSlotId(chosenId);
        setTimeChoice(`slot:${chosenId}`);
      }
      if(moveContext){
        const message=patientMessage.trim().length>=3?patientMessage.trim():`Your appointment has been ${moveContext.action==="POSTPONE"?"postponed":"moved earlier"}. Please check the confirmed date and time in your app.`;
        return api<{appointment:{reference:string}}>(`/v1/tasks/${moveContext.task}/appointment-action`,{body:{action:moveContext.action,appointment_id:moveContext.appointment,slot_id:chosenId,message}});
      }
      return api<{ appointment: { reference: string } }>("/v1/appointments", {
        body: { patient_id: patientId, slot_id: chosenId, request_id: requestId, client_key: clientKey() },
      });
    }, (r) => `Booked. Reference ${r.appointment.reference}. The patient gets a confirmation message.`);
    if (result) {
      setSlotId(null);
      setTimeChoice("");
      setRequestId(null);
      setOffered(null);
      if(moveContext){setMoveContext(null);setPatientMessage("");window.history.replaceState(null,"",`/schedule?patient=${patientId}`);}
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

  const choosable = offered ? offered.slots.filter(withinClinicHours) : null;

  function selectSlot(id: string) {
    const selected = [...(slots.data?.slots ?? []), ...(offered?.slots ?? [])].find(slot => slot.id === id);
    setSlotId(id); setTimeChoice(`slot:${id}`);
    if (selected) setDay(selected.date);
  }

  return (
    <>
      <PageHead title="Schedule"
        lede={<>Only times from the clinic&rsquo;s availability are offered, and nothing is confirmed until the booking is saved with a reference. {counts?.waiting_on_patient_choice ? `${counts.waiting_on_patient_choice} patient${counts.waiting_on_patient_choice === 1 ? " is" : "s are"} choosing a time in the app.` : ""}</>} />

      {!moveContext?<section className="panel" style={{ marginBottom: 20 }}>
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
      </section>:null}

      <section id="book" className="panel stack">
        <h2 style={{ fontSize: 19 }}>Book a time</h2>
        {moveContext?<p className="notice">{moveContext.action==="POSTPONE"?"Postpone: select a later appointment slot.":"Prepone: select an earlier appointment slot."} The original stays reserved until the replacement booking succeeds.</p>:null}
        <div className="form-grid">
          <label className="field"><span>Patient</span>
            <select disabled={busy||Boolean(moveContext)} value={patientId} onChange={(e) => { setPatientId(e.target.value); setRequestId(null); setOffered(null); }}>
              <option value="">Choose a patient</option>
              {pts?.patients.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.external_ref})</option>)}
            </select>
          </label>
          <label className="field"><span>Day</span>
            <input disabled={busy} type="date" value={day} onChange={(e) => { setDay(e.target.value); setSlotId(null); setTimeChoice(""); setOffered(null); }} />
          </label>
          <label className="field"><span>Time slot</span>
            <select disabled={busy || !day} value={timeChoice} onChange={e => {
              setTimeChoice(e.target.value);
              if(e.target.value.startsWith("slot:")) selectSlot(e.target.value.slice(5));
              else { setSlotId(null); setOffered(null); }
            }}>
              <option value="">{day ? "Choose a time" : "Choose the day first"}</option>
              <optgroup label="Available clinic slots">{(slots.data?.slots ?? []).filter(slot=>slot.date===day && withinClinicHours(slot)).map(slot=><option key={slot.id} value={`slot:${slot.id}`}>{slot.label.split(", ").slice(-1)[0]} · {slot.provider}</option>)}</optgroup>
              <optgroup label="Set a clinic time">{Array.from({length:25},(_,i)=>{
                const hour=11+Math.floor(i/3),minute=(i%3)*20;
                const clock=`${String(hour).padStart(2,"0")}:${String(minute).padStart(2,"0")}`;
                return <option key={clock} value={`clock:${clock}`}>{hour%12||12}:{String(minute).padStart(2,"0")} {hour<12?"AM":"PM"}</option>;
              })}</optgroup>
            </select>
          </label>
          <label className="field"><span>Clinician or room</span><input disabled={busy || Boolean(slotId)} maxLength={120} value={slotId ? ([...(slots.data?.slots ?? []),...(offered?.slots ?? [])].find(slot=>slot.id===slotId)?.provider ?? provider) : provider} onChange={e=>setProvider(e.target.value)} /></label>
        </div>
        <p className="small muted">Start times: 11 AM–7 PM ({me.clinic.timezone}). New appointments use a standard 20-minute slot.</p>
        {moveContext?<label className="field"><span>Extra note to patient (optional)</span><textarea maxLength={1000} placeholder="The confirmed appointment update is sent automatically. Add a note if needed." value={patientMessage} onChange={e=>setPatientMessage(e.target.value)}/></label>:null}
        {!moveContext?<div className="field" style={{ maxWidth: 640 }}>
          <span>Or type what the patient said</span>
          <form className="row" style={{ flexWrap: "nowrap" }} onSubmit={(e) => { e.preventDefault(); void ask(); }}>
            <input type="text" placeholder="Saturday morning, repu, 12 tareekh" value={dayWords} onChange={(e) => setDayWords(e.target.value)} style={{ flex: 1, width: "auto", minWidth: 0 }} />
            <button type="submit" className="btn btn--quiet" disabled={busy || !patientId || !dayWords.trim()}>Find times</button>
          </form>
          <small>Understood the same way as a patient&rsquo;s message, in English, Hindi or Telugu mixed with English.</small>
        </div>:null}
        {requestId ? <p className="small">Booking for an open request. It closes when the booking is saved.</p> : null}
        {offered?.question ? <p className="notice notice--warn">{offered.question}</p> : null}
        {offered && offered.request.status === "HANDED_TO_STAFF" ? <p className="notice notice--fail">The booking service is unavailable or has no free times. A task was created; arrange the time by phone.</p> : null}
        <ErrorNote error={slots.error} />
        {choosable ? (
          <SlotGrid groups={[["Offered times", choosable]]} selected={slotId} onSelect={selectSlot} />
        ) : byDay.length ? (
          <SlotGrid groups={byDay.map(([d, s]) => [fmtLongDay(d), s])} selected={slotId} onSelect={selectSlot} />
        ) : slots.data ? <p className="muted">{timeChoice.startsWith("clock:")?"A new 20-minute slot will be created for this time when you confirm, subject to availability.":"No existing open slots for this day. Choose a clinic time above."}</p> : null}
        <div className="row">
          <button className="btn" disabled={busy || !patientId || (!slotId && (!day || !timeChoice || !provider.trim()))} onClick={book}>{moveContext?`Confirm ${moveContext.action==="POSTPONE"?"postponement":"earlier appointment"} and notify patient`:"Book and send confirmation"}</button>
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
