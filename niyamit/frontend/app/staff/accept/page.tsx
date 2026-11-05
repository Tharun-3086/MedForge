"use client";
import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
export default function AcceptStaff() {
 const [token,setToken]=useState(""); const [password,setPassword]=useState(""); const [confirm,setConfirm]=useState("");
 const [error,setError]=useState("");const [done,setDone]=useState("");const [busy,setBusy]=useState(false);
 useEffect(()=>{const incoming=window.location.hash.slice(1);if(incoming)setToken(incoming);window.history.replaceState(null,"",window.location.pathname);},[]);
 async function accept(e:FormEvent){e.preventDefault();setError("");if(password!==confirm){setError("Passwords do not match.");return;}setBusy(true);
  try{const r=await api<{email:string}>("/v1/auth/staff-invitations/accept",{body:{token,password}});setDone(r.email);setPassword("");setConfirm("");setToken("");}
  catch(e){setError(e instanceof Error?e.message:"Could not accept invitation.");}finally{setBusy(false);}}
 return <main className="welcome-shell"><section className="panel stack-l patient-entrance"><h1>Join your clinic</h1>
 {done?<><p>Account created for {done}. Your clinic administrator has approved your role.</p><Link href="/login" className="btn">Sign in to clinic</Link></>:<>
 <p>Use the private invitation provided by your clinic administrator. Choose your own password; do not share it.</p>
 {!token?<p>Open your complete invitation link. If you refreshed this page, reopen the original link.</p>:null}
 <form onSubmit={accept} className="stack">
 <label className="field"><span>New password</span><input type="password" autoComplete="new-password" minLength={12} maxLength={200} required value={password} onChange={e=>setPassword(e.target.value)}/><small>At least 12 characters.</small></label>
 <label className="field"><span>Confirm password</span><input type="password" autoComplete="new-password" required value={confirm} onChange={e=>setConfirm(e.target.value)}/></label>
 {error?<p role="alert">{error}</p>:null}<button className="btn" disabled={busy||!token}>{busy?"Creating account…":"Accept invitation"}</button>
 </form></>}
 </section></main>;
}
