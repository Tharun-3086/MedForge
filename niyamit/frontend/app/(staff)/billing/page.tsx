"use client";
import {useState} from "react";
import {api,useApi} from "@/lib/api";
import {useStaff} from "@/lib/staff-context";
import {PageHead} from "@/components/staff-shell";
import {ErrorNote} from "@/components/ui";
type Plan={key:string;name:string;patient_limit:number;monthly_paise:number};
type Billing={selection_enabled:boolean;active_patients:number;active_definition:string;plans:Plan[];subscription:null|{plan_key:string;period_start:string;period_end:string;status:string};invoices:{reference:string;plan:string;amount_paise:number;created_at:string}[]};
const money=(p:number)=>new Intl.NumberFormat("en-IN",{style:"currency",currency:"INR",maximumFractionDigits:0}).format(p/100);
export default function BillingPage(){const {me}=useStaff();const allowed=me.user.role==="ADMIN";const data=useApi<Billing>(allowed?"/v1/billing":null);const [busy,setBusy]=useState(false);const [message,setMessage]=useState("");const [error,setError]=useState<string|null>(null);
 async function choose(plan_key:string){setBusy(true);setError(null);try{const r=await api<{message:string}>("/v1/billing/simulate",{body:{plan_key}});setMessage(r.message);await data.reload();}catch(e){setError(e instanceof Error?e.message:"Could not select plan");}finally{setBusy(false);}}
 if(!allowed)return <p>Only your clinic administrator can manage billing.</p>;
 return <><PageHead title="Clinic subscription" lede="Illustrative monthly plans in INR. Demo only: no payment is collected."/><p className="notice">These are demo prices, not a commercial offer or tax invoice. SMS, AI and hosting costs are not included or metered here. No card or bank information is requested.</p><ErrorNote error={error||data.error}/>{message?<p role="status" className="notice">{message}</p>:null}
 {data.data?<div className="stack-l"><section className="panel stack"><h2>{data.data.active_patients} active patients</h2><p>{data.data.active_definition}</p><p>Current plan: {data.data.subscription?`${data.data.subscription.plan_key} · ${data.data.subscription.status} · ${data.data.subscription.period_start} to ${data.data.subscription.period_end} (end exclusive)`:'No demo plan selected'}</p><p>Plan limits are advisory in this demo. Existing care and record access are never blocked by billing.</p></section>
 <div className="cols-3">{data.data.plans.map(p=><section className="panel stack" key={p.key}><h2>{p.name}</h2><p><strong>{money(p.monthly_paise)}</strong> / month</p><p>Up to {p.patient_limit.toLocaleString('en-IN')} active patients</p><button className="btn" disabled={busy||!data.data?.selection_enabled||data.data.active_patients>p.patient_limit} onClick={()=>void choose(p.key)}>Select {p.name} demo plan</button></section>)}</div>
 {!data.data.selection_enabled?<p className="notice">Demo activation is disabled in this deployment. Real payments are not configured.</p>:null}
 <section className="panel stack"><h2>Simulated billing history</h2><p>Changing plans creates a demonstration entry at the full illustrative monthly price. There is no payment, refund, proration or automatic renewal.</p>{data.data.invoices.length===0?<p>No demo billing entries yet.</p>:data.data.invoices.map(i=><article className="card stack" key={i.reference}><strong>{i.plan} · {money(i.amount_paise)}</strong><span>{i.reference}</span><span>{new Date(i.created_at).toLocaleDateString()}</span><span>Simulated — no payment collected</span></article>)}</section></div>:!data.error?<p>Loading subscription…</p>:null}</>;
}
