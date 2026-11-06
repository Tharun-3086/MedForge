"use client";
import { useEffect, useRef, useState } from "react";
import { BrandMark } from "@/components/ui";
const steps = [
 {title:"Welcome to Niyamit", text:"One app connects patients and their clinic. Choose Patient for your care or Clinic for authorised staff work.", detail:"తెలుగు · हिन्दी · English"},
 {title:"Your care, in one place", text:"Patients sign in with their clinic-registered phone number, upload a report, send messages and check follow-ups.", detail:"Automatic analysis can contain errors. Clinic-reviewed information is shown separately."},
 {title:"Your clinic team stays connected", text:"Clinic staff add patients, review reports and respond to requests. Clinic administrators approve staff access and roles.", detail:"Only share records through your authorised clinic account. Demo mode uses fictional records and test codes."}
];
export function AppTour() {
 const dialog=useRef<HTMLDialogElement>(null);const [step,setStep]=useState(0);const [open,setOpen]=useState(false);
 useEffect(()=>{let seen=false;try{seen=localStorage.getItem("niyamit-tour-v1")==="done";}catch{}
 if(seen)return;const timer=setTimeout(()=>setOpen(true),1700);return()=>clearTimeout(timer);},[]);
 useEffect(()=>{if(open&&!dialog.current?.open)dialog.current?.showModal();},[open]);
 function finish(){try{localStorage.setItem("niyamit-tour-v1","done");}catch{}dialog.current?.close();setOpen(false);setStep(0);}
 return <><button type="button" className="tour-launch" onClick={()=>{setStep(0);setOpen(true);}}>App tour</button>
 <dialog ref={dialog} className="app-tour" aria-labelledby="tour-title" onCancel={finish}>
 <div className="stack-l"><div className="spread"><BrandMark/><button className="pt-link" onClick={finish}>Skip tour</button></div>
 <p className="small muted" aria-live="polite">Step {step+1} of {steps.length}</p>
 <h2 id="tour-title">{steps[step].title}</h2><p>{steps[step].text}</p><p className="notice">{steps[step].detail}</p>
 <div className="spread">{step>0?<button className="btn btn--quiet" onClick={()=>setStep(step-1)}>Back</button>:<span/>}
 <button className="btn" onClick={()=>step===steps.length-1?finish():setStep(step+1)}>{step===steps.length-1?"Get started":"Next"}</button></div></div>
 </dialog></>;
}
