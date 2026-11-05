"use client";
import Link from "next/link";
import { PhoneLogin } from "@/components/patient/phone-login";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { BrandMark, ErrorNote } from "@/components/ui";
export default function PatientEntrance() {
 const router = useRouter();
 const [link, setLink] = useState("");
 const [error, setError] = useState<string | null>(null);
 const [busy, setBusy] = useState(false);
 async function pasteLink() {
  try {
   if (!navigator.clipboard?.readText) throw new Error("Clipboard unavailable");
   const text = await navigator.clipboard.readText();
   if (!text.trim()) throw new Error("Clipboard empty");
   setLink(text.trim()); setError(null);
  } catch { setError("Could not read the clipboard. Copy the clinic link again, then press and hold the link box and choose Paste. In an emulator, enable clipboard sharing first."); }
 }
 function openCare(event: FormEvent) {
  event.preventDefault();
  try {
   const url = new URL(link.trim(), window.location.origin);
   if (url.origin !== window.location.origin || !/^\/p\/[A-Za-z0-9_-]+\/?$/.test(url.pathname) || url.search || url.hash) throw new Error("Invalid link");
   setError(null); setBusy(true); router.push(url.pathname);
  } catch { setError("Enter a valid patient app link from this clinic's Niyamit website."); }
 }
 return <main className="welcome-shell"><section className="panel stack-l patient-entrance"><div className="spread"><BrandMark className="brand-mark"/><Link href="/">Niyamit</Link></div><header className="stack"><h1>Welcome to your care</h1><p lang="te">మీ సంరక్షణకు స్వాగతం</p><p lang="hi">आपकी देखभाल में आपका स्वागत है</p><p className="muted">Sign in with your phone to see your reports and care plan. Your care page supports Telugu, Hindi and English.</p></header><PhoneLogin/><details><summary>Have a clinic link? Open it here</summary><form className="stack" onSubmit={openCare}><label className="field"><span>Your patient app link</span><input type="text" value={link} onChange={(e) => setLink(e.target.value)} autoComplete="off" spellCheck={false} autoCapitalize="none" required /></label><button type="button" className="btn btn--quiet" onClick={() => void pasteLink()}>Paste link</button><ErrorNote error={error}/><button className="btn" disabled={busy || !link.trim()}>{busy ? "Opening…" : "Continue to my care"}</button><p className="small muted">Your clinic may ask you to verify your birth year before showing your information.</p></form></details><p>No link, or has it expired? Ask your clinic for a new patient app link.</p><Link href="/login" className="small">Clinic staff sign in</Link></section></main>;
}
