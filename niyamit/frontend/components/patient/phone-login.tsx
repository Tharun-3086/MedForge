"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, useApi } from "@/lib/api";
import { ErrorNote } from "@/components/ui";

type Challenge = {
  challenge_id: string; development_code?: string; message: string;
  resend_after_seconds: number; expires_in_seconds: number;
};
type Pending = { phone: string; challenge: Challenge | null; expiresAt: number; retryAt: number; checkRetryAt: number };
const PENDING_KEY = "niyamit-patient-otp-v2";
function normalizedPhone(value: string) {
  const compact = value.replace(/[\s()-]/g, "");
  if (/^[6-9]\d{9}$/.test(compact)) return `+91${compact}`;
  if (compact.startsWith("+91")) return /^\+91[6-9]\d{9}$/.test(compact) ? compact : "";
  return /^\+[1-9]\d{7,14}$/.test(compact) ? compact : "";
}
const countdown = (seconds: number) => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
function remember(value: Pending | null) {
  try {
    if (value) {
      const challenge = value.challenge ? { ...value.challenge, development_code: undefined } : null;
      sessionStorage.setItem(PENDING_KEY, JSON.stringify({ ...value, challenge }));
    }
    else sessionStorage.removeItem(PENDING_KEY);
  } catch { /* Login still works when browser session storage is unavailable. */ }
}

export function PhoneLogin() {
  const router = useRouter();
  const { data: config, error: configError, loading: configLoading, reload: reloadConfig } = useApi<{available:boolean;development:boolean;demo_available?:boolean}>("/v1/p/otp/config");
  const [demoBusy,setDemoBusy] = useState(false);
  const [phone,setPhone] = useState("+91 ");
  const [code,setCode] = useState("");
  const [challenge,setChallenge] = useState<Challenge|null>(null);
  const [profiles,setProfiles] = useState<{id:string;clinic:string}[]>([]);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState<string|null>(null);
  const [retryAt,setRetryAt] = useState(0);
  const [checkRetryAt,setCheckRetryAt] = useState(0);
  const [expiresAt,setExpiresAt] = useState(0);
  const [now,setNow] = useState(Date.now());
  const inFlight = useRef(false);
  const wait = Math.max(0, Math.ceil((retryAt-now)/1000));
  const checkWait = Math.max(0, Math.ceil((checkRetryAt-now)/1000));
  const expired = Boolean(challenge && expiresAt && now >= expiresAt);
  const validPhone = normalizedPhone(phone);

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(PENDING_KEY);
      if (!raw) return;
      const saved = JSON.parse(raw) as Pending;
      if (typeof saved.phone !== "string" || saved.phone.length > 32 ||
          ![saved.expiresAt,saved.retryAt,saved.checkRetryAt].every(Number.isFinite)) {
        remember(null); return;
      }
      const current = Date.now();
      const active = saved.challenge && typeof saved.challenge.challenge_id === "string" && saved.expiresAt > current;
      if (!active && saved.retryAt <= current && saved.checkRetryAt <= current) { remember(null); return; }
      setPhone(saved.phone); setRetryAt(saved.retryAt); setCheckRetryAt(saved.checkRetryAt);
      setExpiresAt(active ? saved.expiresAt : 0); setChallenge(active ? saved.challenge : null); setNow(current);
      if (!active) setError("Please wait for the countdown before requesting another code.");
    } catch { remember(null); }
  }, []);

  useEffect(() => {
    if (!challenge && retryAt <= Date.now() && checkRetryAt <= Date.now()) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [challenge,retryAt,checkRetryAt]);

  function showError(e: unknown, checking = false) {
    setError(e instanceof Error ? e.message : "Could not complete phone verification.");
    const delay = e instanceof ApiError ? e.retryAfterSeconds ?? (e.status === 429 ? 60 : 0) : 0;
    if (delay > 0) {
      const deadline = Date.now() + delay*1000;
      const nextRetry = Math.max(retryAt,deadline);
      const nextCheck = checking ? Math.max(checkRetryAt,deadline) : checkRetryAt;
      setRetryAt(nextRetry); setCheckRetryAt(nextCheck); setNow(Date.now());
      remember({phone,challenge,expiresAt,retryAt:nextRetry,checkRetryAt:nextCheck});
    }
  }

  async function requestCode() {
    if (inFlight.current || wait > 0 || !validPhone || !config?.available) return;
    inFlight.current = true; setBusy(true); setError(null);
    try {
      const next = await api<Challenge>("/v1/p/otp/request", {body:{phone:validPhone}});
      const current = Date.now();
      const nextRetry = current + next.resend_after_seconds*1000;
      const nextExpiry = current + (next.expires_in_seconds ?? 300)*1000;
      setChallenge(next); setCode(""); setProfiles([]); setRetryAt(nextRetry);
      setCheckRetryAt(0); setExpiresAt(nextExpiry); setNow(current);
      remember({phone,challenge:next,expiresAt:nextExpiry,retryAt:nextRetry,checkRetryAt:0});
    } catch (e) { showError(e); }
    finally { inFlight.current = false; setBusy(false); }
  }

  async function verify(event: FormEvent) {
    event.preventDefault();
    if (!challenge) { await requestCode(); return; }
    if (inFlight.current || expired || checkWait > 0) return;
    inFlight.current = true; setBusy(true); setError(null);
    try {
      const result = await api<{authenticated:boolean;profiles?:{id:string;clinic:string}[];message?:string}>(
        "/v1/p/otp/verify", {body:{phone:validPhone,code,challenge_id:challenge.challenge_id}});
      remember(null); setCode("");
      if (result.authenticated) router.push("/patient/dashboard");
      else {
        setProfiles(result.profiles??[]); setChallenge(null);
        if (result.message) setError(result.message);
      }
    } catch (e) { showError(e,true); }
    finally { inFlight.current = false; setBusy(false); }
  }

  async function choose(id: string) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(null);
    try { await api("/v1/p/otp/select",{body:{patient_id:id}}); remember(null); router.push("/patient/dashboard"); }
    catch (e) { showError(e); }
    finally { inFlight.current = false; setBusy(false); }
  }

  function changeNumber() {
    remember(null); setChallenge(null); setCode(""); setError(null);
    setRetryAt(0); setCheckRetryAt(0); setExpiresAt(0); setNow(Date.now());
  }

  async function openDemo() {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setDemoBusy(true); setError(null);
    try {
      await api("/v1/p/demo-login", {method:"POST"});
      remember(null); setCode(""); router.push("/patient/dashboard");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not open the demo patient."); }
    finally { inFlight.current = false; setBusy(false); setDemoBusy(false); }
  }

  return <section className="stack">
    {config?.demo_available ? <div id="demo-patient" className="notice stack">
      <h2>Explore the patient demo</h2>
      <p>Try Ramesh Kumar at Sunrise Clinic without a phone number or SMS code.</p>
      <button type="button" className="btn" disabled={busy} onClick={()=>void openDemo()}>{demoBusy ? "Opening demo…" : "Try demo patient — no OTP"}</button>
      <p className="small">Shared synthetic account. Other testers can see demo activity. Upload fictional documents only.</p>
    </div> : null}
    <h2>Sign in with your phone</h2>
    <p className="muted">Use the number registered with your clinic. If you are new, ask the admin to add your phone number and enable SMS OTP access.</p>
    {configLoading ? <p role="status" className="small">Connecting to phone login… The service may take a moment to wake up.</p> : null}
    {configError ? <div className="notice stack" role="status"><p>Could not connect to phone login. Please retry in a moment.</p><button type="button" className="btn btn--quiet" disabled={configLoading} onClick={()=>void reloadConfig()}>Retry connection</button></div> : null}
    {config && !config.demo_available ? <p className="small muted">The demo patient is disabled on this deployment. Use your registered phone number or clinic link.</p> : null}
    {config?.development ? <p className="notice">Development test login — no SMS is sent. Test codes appear here and only open synthetic records.</p> : null}
    {config && !config.available ? <p className="notice">Phone login is not configured. Use your clinic link below.</p> : null}
    {profiles.length ? <div className="stack"><h3>Choose your clinic</h3>{profiles.map(p=><button key={p.id} className="btn" disabled={busy} onClick={()=>void choose(p.id)}>{p.clinic}</button>)}</div> : <form className="stack" onSubmit={verify}>
      <label className="field"><span>Phone number</span><input type="tel" inputMode="tel" autoComplete="tel" placeholder="+91 90000 00000" required value={phone} aria-describedby="phone-help"
        onPaste={e=>{const pasted=normalizedPhone(e.clipboardData.getData("text"));if(pasted&&!challenge&&!busy){e.preventDefault();setPhone(pasted);setRetryAt(0);setCheckRetryAt(0);remember(null);}}}
        disabled={Boolean(challenge)||busy} onChange={e=>{setPhone(e.target.value);setRetryAt(0);setCheckRetryAt(0);remember(null);}}/></label>
      <p id="phone-help" className="small muted">India (+91) is selected by default. Enter your 10-digit mobile number, or change the country code for another country.</p>
      {challenge ? <>
        <p role="status">{challenge.message}</p>
        {challenge.development_code ? <p className="notice"><b>Development code: <span data-testid="development-code">{challenge.development_code}</span></b><br/>Expires in 5 minutes. This is not proof of phone ownership.</p> : null}
        {expired ? <p className="notice">This code has expired. Request a new code when the countdown ends.</p> : null}
        <label className="field"><span>6-digit code</span><input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required
          value={code} onChange={e=>setCode(e.target.value.replace(/\D/g,""))}/></label>
      </> : null}
      <button className="btn" disabled={busy||configLoading||!config?.available||(challenge ? expired||checkWait>0 : wait>0||!validPhone)}>
        {busy ? "Please wait…" : challenge ? checkWait>0 ? `Verify again in ${countdown(checkWait)}` : "Verify and sign in" : wait>0 ? `Try again in ${countdown(wait)}` : config?.development ? "Get test code" : "Send SMS code"}
      </button>
      {challenge ? <div className="row">
        <button className="btn btn--quiet" type="button" disabled={busy||wait>0} onClick={()=>void requestCode()}>{wait>0 ? `Resend in ${countdown(wait)}` : "Get a new code"}</button>
        <button className="pt-link" type="button" disabled={busy} onClick={changeNumber}>Change number</button>
      </div> : null}
      {wait>0 ? <p className="small" data-testid="otp-retry-countdown">You can request another code in {countdown(wait)}. Check your SMS for the latest code.</p> : null}
    </form>}
    <ErrorNote error={error}/>
    <p className="small muted">New patient? Ask the admin to add your phone number and enable SMS OTP access. Verification does not automatically share your records with another clinic.</p>
    {config?.demo_available ? <p className="small muted">Here for testing? Choose “Try demo patient — no OTP” above to open the fixed demo patient, Ramesh Kumar at Sunrise Clinic. You do not need to add your own number.</p> : null}
  </section>;
}
