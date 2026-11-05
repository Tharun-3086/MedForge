"use client";
import { useState, type FormEvent } from "react";
import { api, useApi } from "@/lib/api";

type Member = { id: string; name: string; email: string; role: string; can_revoke?: boolean };
export function StaffAccess() {
 const data = useApi<{staff: Member[]; invitations: Member[]}>("/v1/clinic/staff-access");
 const [name,setName]=useState(""); const [email,setEmail]=useState(""); const [role,setRole]=useState("NURSE");
 const [link,setLink]=useState(""); const [busy,setBusy]=useState(false); const [error,setError]=useState("");
 async function invite(e: FormEvent) { e.preventDefault(); setBusy(true); setError(""); setLink("");
  try { const r=await api<{invitation_url:string}>("/v1/clinic/staff/invitations",{body:{name,email,role}});
   setLink(r.invitation_url); setName(""); setEmail(""); await data.reload();
  } catch(e) {setError(e instanceof Error?e.message:"Could not create invitation.");} finally {setBusy(false);} }
 async function revoke(id:string, invitation:boolean) {
  if(!window.confirm(invitation?"Cancel this invitation?":"Remove this person's access to your clinic immediately?")) return;
  setBusy(true);setError("");
  try {await api(`/v1/clinic/staff/${invitation?"invitations/":""}${id}`,{method:"DELETE"});setLink("");await data.reload();}
  catch(e){setError(e instanceof Error?e.message:"Could not revoke access.");}finally{setBusy(false);}
 }
 return <section className="panel stack" aria-labelledby="staff-access-title">
  <h2 id="staff-access-title">Clinic staff access</h2>
  <p>Invite a new staff member after verifying their identity and clinic role. Only clinic administrators can grant access.</p>
  <form className="stack" onSubmit={invite}>
   <label className="field"><span>Staff name</span><input required maxLength={120} value={name} onChange={e=>setName(e.target.value)}/></label>
   <label className="field"><span>Staff email</span><input type="email" required maxLength={200} value={email} onChange={e=>setEmail(e.target.value)}/></label>
   <label className="field"><span>Staff role</span><select value={role} onChange={e=>setRole(e.target.value)}><option value="NURSE">Nurse</option><option value="DOCTOR">Doctor</option><option value="RECEPTION">Reception</option></select></label>
   <button className="btn" disabled={busy}>Approve and create invitation</button>
  </form>
  {error||data.error?<p role="alert">{error||data.error?.message}</p>:null}
  {link?<div className="stack"><p>Share this private link with the intended person. It expires in 24 hours and works once. No email has been sent.</p><label className="field"><span>Private staff invitation</span><input readOnly value={link} onFocus={e=>e.target.select()}/></label></div>:null}
  <h3>Current staff</h3>
  {data.data?.staff.map(m=><div className="spread" key={m.id}><div><strong>{m.name}</strong><p>{m.email} · {m.role}</p></div>{m.can_revoke?<button className="btn btn--quiet" disabled={busy} onClick={()=>void revoke(m.id,false)}>Revoke access</button>:null}</div>)}
  <h3>Pending invitations</h3>
  {data.data?.invitations.length===0?<p>No pending invitations.</p>:null}
  {data.data?.invitations.map(m=><div className="spread" key={m.id}><div>{m.name} · {m.email} · {m.role}</div><button className="btn btn--quiet" disabled={busy} onClick={()=>void revoke(m.id,true)}>Cancel invitation</button></div>)}
 </section>;
}
