"use client";
import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { BrandMark, ErrorNote } from "@/components/ui";
export default function RegisterClinic() {
 const router=useRouter();const [busy,setBusy]=useState(false);const [error,setError]=useState<string|null>(null);
 const [form,setForm]=useState({clinic_name:"",short_name:"",owner_name:"",email:"",password:""});
 const [confirm,setConfirm]=useState("");const [agreed,setAgreed]=useState(false);
 async function submit(e:FormEvent){e.preventDefault();setError(null);if(form.password!==confirm){setError("Passwords do not match.");return;}if(!agreed)return;
 setBusy(true);try{await api("/v1/auth/register-clinic",{body:form});router.push("/settings");}catch(e){setError(e instanceof Error?e.message:"Could not register clinic.");}finally{setBusy(false);}}
 return <main className="welcome-shell"><section className="panel stack-l patient-entrance"><BrandMark/><h1>Register your clinic</h1><p>Create your clinic workspace immediately. You become its administrator and can invite your team from Settings.</p>
 <form className="stack" onSubmit={submit}>
 {([{key:"clinic_name",label:"Clinic name",max:200},{key:"short_name",label:"Short clinic name",max:60},{key:"owner_name",label:"Your name",max:120},{key:"email",label:"Your work email",max:200},{key:"password",label:"Create password",max:200}] as const).map(f=><label className="field" key={f.key}><span>{f.label}</span><input required minLength={f.key==="password"?12:2} maxLength={f.max} type={f.key==="email"?"email":f.key==="password"?"password":"text"} autoComplete={f.key==="password"?"new-password":f.key==="email"?"email":f.key==="owner_name"?"name":"off"} value={form[f.key]} onChange={e=>setForm({...form,[f.key]:e.target.value})}/></label>)}
 <p className="small muted">Use at least 12 characters for your password.</p><label className="field"><span>Confirm password</span><input type="password" autoComplete="new-password" required value={confirm} onChange={e=>setConfirm(e.target.value)}/></label>
 <label className="check"><input type="checkbox" required checked={agreed} onChange={e=>setAgreed(e.target.checked)}/><span>I am authorised to create this clinic workspace. I understand a demo workspace must contain fictional patient information only.</span></label>
 <ErrorNote error={error}/><button className="btn" disabled={busy||!agreed}>{busy?"Creating clinic…":"Create clinic account"}</button></form><Link href="/login">Already registered? Sign in</Link>
 <p className="small muted">Registration does not verify your email address or professional credentials. Staff should accept an invitation from their clinic administrator rather than create a second clinic.</p>
 </section></main>;
}
