"use client";
import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { api, useApi } from "@/lib/api";
import { ErrorNote } from "@/components/ui";

type Challenge = { challenge_id: string; development_code?: string; message: string; resend_after_seconds: number };
export function PhoneLogin() {
  const router = useRouter();
  const { data: config } = useApi<{available:boolean;development:boolean}>("/v1/p/otp/config");
  const [phone,setPhone]=useState(""); const [code,setCode]=useState("");
  const [challenge,setChallenge]=useState<Challenge|null>(null);
  const [profiles,setProfiles]=useState<{id:string;clinic:string}[]>([]);
  const [busy,setBusy]=useState(false); const [error,setError]=useState<string|null>(null);
  const [wait,setWait]=useState(0);
  useEffect(()=>{if(!wait)return;const id=setTimeout(()=>setWait(wait-1),1000);return()=>clearTimeout(id)},[wait]);
  async function requestCode(){
    setBusy(true);setError(null);
    try{const r=await api<Challenge>("/v1/p/otp/request",{body:{phone}});setChallenge(r);setCode("");setWait(r.resend_after_seconds);setProfiles([])}
    catch(e){setError(e instanceof Error?e.message:"Could not request code.")}finally{setBusy(false)}
  }
  async function verify(e:FormEvent){
    e.preventDefault();if(!challenge){await requestCode();return}
    setBusy(true);setError(null);
    try{const r=await api<{authenticated:boolean;profiles?:{id:string;clinic:string}[];message?:string}>("/v1/p/otp/verify",{body:{phone,code,challenge_id:challenge.challenge_id}});
      if(r.authenticated)router.push("/patient/dashboard");else{setProfiles(r.profiles??[]);setChallenge(null);setCode("");if(r.message)setError(r.message)}
    }catch(e){setError(e instanceof Error?e.message:"Could not verify code.")}finally{setBusy(false)}
  }
  async function choose(id:string){setBusy(true);try{await api("/v1/p/otp/select",{body:{patient_id:id}});router.push("/patient/dashboard")}catch(e){setError(e instanceof Error?e.message:"Could not open record.")}finally{setBusy(false)}}
  return <section className="stack">
    <h2>Sign in with your phone</h2>
    <p className="muted">Use the number registered with your clinic. No patient link is needed.</p>
    {config?.development?<p className="notice">Development test login — no SMS is sent. Test codes appear here and only open synthetic records.</p>:null}
    {config && !config.available?<p className="notice">Phone login is not configured. Use your clinic link below.</p>:null}
    {profiles.length?<div className="stack"><h3>Choose your clinic</h3>{profiles.map(p=><button key={p.id} className="btn" disabled={busy} onClick={()=>void choose(p.id)}>{p.clinic}</button>)}</div>:<form className="stack" onSubmit={verify}>
      <label className="field"><span>Phone number</span><input type="tel" autoComplete="tel" placeholder="+91 90000 00000" required value={phone} disabled={Boolean(challenge)||busy} onChange={e=>setPhone(e.target.value)}/></label>
      {challenge?<><p role="status">{challenge.message}</p>{challenge.development_code?<p className="notice"><b>Development code: <span data-testid="development-code">{challenge.development_code}</span></b><br/>Expires in 5 minutes. This is not proof of phone ownership.</p>:null}
        <label className="field"><span>6-digit code</span><input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required value={code} onChange={e=>setCode(e.target.value.replace(/\D/g,""))}/></label></>:null}
      <button className="btn" disabled={busy||!config?.available}>{busy?"Please wait…":challenge?"Verify and sign in":"Get test code"}</button>
      {challenge?<div className="row"><button className="btn btn--quiet" type="button" disabled={busy||wait>0} onClick={()=>void requestCode()}>{wait?`Resend in ${wait}s`:"Get a new code"}</button><button className="pt-link" type="button" disabled={busy} onClick={()=>{setChallenge(null);setCode("");setError(null)}}>Change number</button></div>:null}
    </form>}
    <ErrorNote error={error}/>
    <p className="small muted">New patient? Ask your clinic to register your number. Verification does not automatically share your records with another clinic.</p>
  </section>;
}
