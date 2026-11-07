"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { BrandMark, ErrorNote } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import type { Me } from "@/lib/types";

type DemoUsers = { password: string; users: { email: string; name: string; role: string; clinic: string }[] };

const ROLE_HINT: Record<string, string> = {
  ADMIN: "Clinic admin: settings, templates, audit",
  DOCTOR: "Doctor: approves plans, answers clinical questions",
  NURSE: "Nurse: reviews reports, follow-up calls",
  RECEPTION: "Reception: calls, bookings, reminders",
  OPERATOR: "Platform support: no patient details",
};

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { data: demo, error: demoError, loading: demoLoading, reload: reloadDemo } = useApi<DemoUsers>("/v1/auth/demo-users");

  async function signIn(mail: string, pass: string) {
    setBusy(true);
    setError(null);
    try {
      const me = await api<Me>("/v1/auth/login", { body: { email: mail, password: pass } });
      const next = new URLSearchParams(window.location.search).get("next");
      const safeNext = next && next.startsWith("/") && !next.startsWith("//") ? next : null;
      router.replace(safeNext ?? (me.user.role === "OPERATOR" ? "/metrics" : "/today"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign-in failed.");
      setBusy(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void signIn(email.trim(), password);
  }

  const clinics = demo ? Array.from(new Set(demo.users.map((u) => u.clinic))) : [];

  return (
    <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: "32px 16px" }}>
      <div style={{ width: "min(940px, 100%)", display: "grid", gap: 24, gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", alignItems: "start" }}>
        <section className="panel stack" style={{ padding: 28 }}>
          <div className="row" style={{ gap: 12 }}>
            <BrandMark className="brand-mark" />
            <div>
              <h1 style={{ fontSize: 26 }}>Clinic staff sign in</h1>
              <p className="muted">Diabetes follow-ups that do not slip through.</p>
            </div>
          </div>
          <Link className="btn btn--quiet" href="/patient">Are you a patient? Open patient app</Link><form onSubmit={onSubmit} className="stack" style={{ marginTop: 8 }}>
            <label className="field">
              <span>Email</span>
              <input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </label>
            <label className="field">
              <span>Password</span>
              <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </label>
            <ErrorNote error={error} />
            <button className="btn" type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
          </form>
          <p className="small muted">Patients can sign in with their phone number or use a personal clinic link.</p>
        </section>

        <section id="demo-accounts" className="panel stack" style={{ padding: 28 }} aria-labelledby="demo-title">
          {demoLoading ? <p role="status">Loading demo clinics… The service may take a moment to wake up.</p> : null}
          {demoError ? <div className="stack" role="status"><h2 id="demo-title">Demo clinic access</h2><p>{demoError.status === 404 ? "Demo accounts are disabled on this deployment. Use your clinic staff account to sign in." : "Could not load demo clinics. Please retry the connection in a moment."}</p>{demoError.status !== 404 ? <button className="btn btn--quiet" type="button" disabled={demoLoading} onClick={()=>void reloadDemo()}>Retry demo clinics</button> : null}</div> : null}
        {demo ? <>
            <div className="stack" style={{ gap: 4 }}>
              <h2 id="demo-title" style={{ fontSize: 20 }}>Demo accounts</h2>
              <p className="muted small">
                Synthetic clinics and patients only. Every account uses the password <b>{demo.password}</b>.
              </p>
            </div>
            {clinics.map((clinic) => (
              <div key={clinic} className="stack" style={{ gap: 6 }}>
                <h3 style={{ fontSize: 15 }}>{clinic}</h3>
                {demo.users.filter((u) => u.clinic === clinic).map((u) => (
                  <button key={u.email} className="btn btn--quiet account" disabled={busy} onClick={() => signIn(u.email, demo.password)}>
                    <span className="who">{u.name}</span>
                    <span className="small muted">{u.email}</span>
                    <span className="small muted" style={{ gridColumn: "1 / -1" }}>{ROLE_HINT[u.role] ?? u.role}</span>
                  </button>
                ))}
              </div>
            ))}
            {!demo.users.length ? <p className="notice">Demo accounts have not been seeded on this deployment. Ask the administrator to check demo setup.</p> : null}
            <Link className="btn btn--quiet" href="/patient#demo-patient">Try the demo patient instead</Link>
          </> : null}
        </section>
        <p>New clinic owner? <Link href="/register-clinic">Register your clinic</Link>. Staff members: ask your administrator for an invitation.</p>
      </div>
    </main>
  );
}
