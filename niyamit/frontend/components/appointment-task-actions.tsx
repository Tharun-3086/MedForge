"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAction } from "@/components/ui";
import type { Task } from "@/lib/types";

export function AppointmentTaskActions({task,onChanged}:{task:Task;onChanged:()=>void}) {
  const options=task.appointment_options??[];
  const [appointmentId,setAppointmentId]=useState(options.length===1?options[0].id:"");
  const [cancel,setCancel]=useState(false);
  const [message,setMessage]=useState("");
  const {busy,run}=useAction();
  useEffect(()=>{setAppointmentId(options.length===1?options[0].id:"");setCancel(false);setMessage("");},[task.id]);
  const appointment=options.find(a=>a.id===appointmentId);
  const path=(action:string)=>`/schedule?patient=${task.patient?.id}&task=${task.id}&appointment=${appointmentId}&move=${action}${appointment?`&date=${appointment.date}`:""}`;
  return <section className="panel stack"><h3>Update appointment</h3>
    {!options.length?<p>No upcoming booking is linked. <Link href={`/schedule?patient=${task.patient?.id}`}>Book an appointment</Link></p>:<>
      <label className="field"><span>Appointment to change</span><select value={appointmentId} onChange={e=>{setAppointmentId(e.target.value);setCancel(false);}}><option value="">Choose an appointment</option>{options.map(a=><option key={a.id} value={a.id}>{a.label} · {a.reference}</option>)}</select></label>
      {appointment?<><div className="row"><Link className="btn btn--quiet" href={path("POSTPONE")}>Postpone appointment</Link><Link className="btn btn--quiet" href={path("PREPONE")}>Prepone appointment</Link><button className="btn btn--danger" onClick={()=>setCancel(!cancel)}>Cancel appointment</button></div>
        <p className="small muted">Postpone selects a later slot; prepone selects an earlier slot. The patient receives the reply and confirmed change in their app.</p></>:null}
      {cancel?<form className="stack" onSubmit={async e=>{e.preventDefault();const result=await run(()=>api(`/v1/tasks/${task.id}/appointment-action`,{body:{action:"CANCEL",appointment_id:appointmentId,message}}),"Appointment cancelled. Patient notified in the app.");if(result){setCancel(false);onChanged();}}}>
        <p>Cancel {appointment?.reference}? This releases the reserved slot; it does not mark the visit completed.</p>
        <label className="field"><span>Message to patient (required)</span><textarea required minLength={3} maxLength={1000} value={message} onChange={e=>setMessage(e.target.value)}/></label>
        <button className="btn btn--danger" disabled={busy||message.trim().length<3}>Confirm cancellation and notify patient</button>
      </form>:null}
    </>}
  </section>;
}
