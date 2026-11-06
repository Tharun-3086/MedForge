"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { ReplyResult, type ReplyView } from "@/components/patient/reply-result";
import { VoiceRecorder } from "@/components/patient/voice";
import { CareActions, CareNavigation, type CareDestination } from "@/components/patient/care-navigation";
import { HealthReadings } from "@/components/patient/health-readings";
import { DocumentAnalysis } from "@/components/patient/document-analysis";
import { BarrierPicker, FamilyView, PassportView, ReportUpload } from "@/components/patient/views";
import { BrandMark } from "@/components/ui";
import { api, ApiError, clientKey } from "@/lib/api";
import { fmtDate, fmtLongDay, fmtTime, leafParts } from "@/lib/format";
import { asLang, dueText, LANGS, t, tItemKind, type Lang } from "@/lib/i18n";
import type { Item } from "@/lib/types";

type Home = {
  patient: { first_name: string; language: string; opted_out: boolean };
  clinic: { name: string; short_name: string; phone: string };
  items: Item[];
  appointments: { id: string; reference: string; starts_at: string; date: string; item_id: string | null; label: string; with: string }[];
  pending: ReplyView | null;
  consents: Record<string, string>;
  voice_available: boolean;
  tts_available: boolean;
  today: string;
};
type View = "home" | "result" | "barrier" | "passport" | "family" | "report";

export default function PatientApp() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const [phase, setPhase] = useState<"loading" | "verify" | "ready" | "broken">("loading");
  const [lang, setLang] = useState<Lang>("te");
  const [clinicName, setClinicName] = useState("");
  const [home, setHome] = useState<Home | null>(null);
  const [view, setView] = useState<View>("home");
  const [reply, setReply] = useState<ReplyView | null>(null);
  const [year, setYear] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [focusMessage, setFocusMessage] = useState(false);
  function navigateCare(destination: CareDestination) {
    setView(destination === "message" ? "home" : destination);
    setFocusMessage(destination === "message");
    if (destination !== "message") window.scrollTo({ top: 0, behavior: "instant" });
  }
  useEffect(() => {
    if (!focusMessage || view !== "home") return;
    const field = document.getElementById("patient-message");
    field?.scrollIntoView({ block: "center", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
    field?.focus({ preventScroll: true });
    setFocusMessage(false);
  }, [focusMessage, view]);

  useEffect(() => { window.scrollTo({ top: 0, behavior: "instant" }); }, [view]);

  const loadHome = useCallback(async () => {
    const h = await api<Home>("/v1/p/home");
    setHome(h);
    setLang(asLang(h.patient.language));
    return h;
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  useEffect(() => {
    (async () => {
      try {
        if (!token) {
          await loadHome(); setPhase("ready"); return;
        }
        const info = await api<{ clinic_name: string; clinic_short_name: string; require_verification: boolean; language: string; already_verified: boolean }>(
          "/v1/p/link", { body: { token } });
        setClinicName(info.clinic_short_name || info.clinic_name);
        setLang(asLang(info.language));
        if (info.already_verified || !info.require_verification) {
          if (info.already_verified) {
            await loadHome();
            setPhase("ready");
            return;
          }
          const h = await api<Home>("/v1/p/verify", { body: { token, birth_year: null } });
          setHome(h);
          setPhase("ready");
          return;
        }
        setPhase("verify");
      } catch {
        if (!token) { router.replace("/patient"); return; }
        setPhase("broken");
      }
    })();
  }, [token, loadHome, router]);

  async function verify(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setProblem(null);
    try {
      const h = await api<Home>("/v1/p/verify", { body: { token, birth_year: Number(year) } });
      setHome(h);
      setLang(asLang(h.patient.language));
      setPhase("ready");
    } catch (err) {
      setProblem(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function changeLang(next: Lang) {
    setLang(next);
    if (phase === "ready") await api<Home>("/v1/p/profile", { method: "PATCH", body: { preferred_language: next } }).then(setHome).catch(() => undefined);
  }

  async function send(path: string, body: Record<string, unknown>) {
    setBusy(true);
    setProblem(null);
    try {
      const r = await api<ReplyView>(path, { body: { ...body, client_key: clientKey() } });
      setReply(r);
      setView("result");
      setText("");
      void loadHome().catch(() => setProblem(t(lang, "refreshHomeFailed")));
    } catch (err) {
      setProblem(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }
  const choose = (choice: string) => send("/v1/p/replies/button", { choice });

  const top = (
    <header className="pt-top">
      <span className="row" style={{ gap: 8 }}>
        <BrandMark className="brand-mark" />
        <span className="pt-clinic">{home?.clinic.short_name ?? clinicName}</span>
      </span>
      <div className="lang" role="group" aria-label="Language">
        {LANGS.map((l) => (
          <button key={l.code} aria-pressed={lang === l.code} onClick={() => void changeLang(l.code)} lang={l.code}>{l.label}</button>
        ))}
      </div>
    </header>
  );

  if (phase === "loading") return <main className="pt"><div className="pt-wrap">{top}<p className="muted">{t(lang, "loading")}</p></div></main>;
  if (phase === "broken") return <main className="pt"><div className="pt-wrap">{top}<p className="card">{t(lang, "linkProblem")}</p></div></main>;
  if (phase === "verify") {
    return (
      <main className="pt">
        <div className="pt-wrap">
          {top}
          <form className="card" onSubmit={verify}>
            <h1>{t(lang, "verifyTitle")}</h1>
            <p>{t(lang, "verifyHelp")}</p>
            <label className="field"><span>{t(lang, "birthYear")}</span>
              <input type="number" inputMode="numeric" min={1900} max={2026} required value={year} onChange={(e) => setYear(e.target.value)} />
            </label>
            {problem ? <p className="notice notice--fail">{problem}</p> : null}
            <button className="btn" type="submit" disabled={busy || year.length !== 4}>{t(lang, "continue")}</button>
          </form>
          <p className="pt-foot">{t(lang, "demoNote")}</p>
        </div>
      </main>
    );
  }
  if (!home) return null;

  const next = home.items[0];
  const later = home.items.slice(1);
  // A booked follow-up is shown on its appointment day, not on the plan's due date.
  const apptFor = (i: Item) => (i.status === "BOOKED" ? home.appointments.find((a) => a.item_id === i.id) : undefined);
  const when = (i: Item) => {
    const a = apptFor(i);
    return a ? `${fmtLongDay(a.date, lang)}, ${fmtTime(a.starts_at, lang)}` : fmtDate(i.due_date, lang);
  };
  const nextAppt = next ? apptFor(next) : undefined;
  const leaf = next ? leafParts(nextAppt ? nextAppt.date : next.due_date, lang) : null;
  const late = Boolean(next && next.days_overdue > 0 && next.status !== "BOOKED");
  const back = <button className="pt-link" onClick={() => { setView("home"); setReply(null); }}>{t(lang, "back")}</button>;

  return (
    <main className="pt">
      <div className="pt-wrap">
        {top}
        <Link href="/" className="pt-link">{lang === "hi" ? "ऐप चुनें: मरीज़ या क्लिनिक" : lang === "te" ? "యాప్ ఎంచుకోండి: రోగి లేదా క్లినిక్" : "Switch Patient / Clinic"}</Link>
        {problem ? <p role="alert" className="notice notice--fail">{problem}</p> : null}
        {view === "home" ? (
          <>
            <h1>{t(lang, "hello", { name: home.patient.first_name })}</h1>
            <button className="pt-link" onClick={async () => { await api("/v1/p/logout", {method:"POST"}); router.replace("/patient"); }}>{lang === "hi" ? "साइन आउट" : lang === "te" ? "సైన్ అవుట్" : "Sign out"}</button>
            <CareActions lang={lang} onSelect={navigateCare} />
            <HealthReadings lang={lang} />
            <DocumentAnalysis lang={lang} onRefresh={loadHome} />
            {home.patient.opted_out ? (
              <div className="notice">{t(lang, "remindersOff")} <button className="pt-link" onClick={() => choose("START")}>{t(lang, "startReminders")}</button></div>
            ) : null}

            {next && leaf ? (
              <section className="card" aria-labelledby="next-title">
                <h2 id="next-title" className="small muted" style={{ fontSize: 16, fontWeight: 600 }}>{t(lang, "nextFollowUp")}</h2>
                <div className="next">
                  <div className={`leaf${late ? " leaf--late" : ""}`} aria-hidden="true">
                    <div className="leaf-top"><span>{leaf.weekday}</span></div>
                    <div className="leaf-day">{leaf.day}</div>
                    <div className="leaf-month">{leaf.month}</div>
                  </div>
                  <div className="stack" style={{ gap: 4 }}>
                    <b style={{ fontSize: 21 }}>{tItemKind(lang, next.kind)}</b>
                    <span>{when(next)}</span>
                    <span className="small" style={{ color: late ? "var(--amber)" : "var(--ink-2)", fontWeight: 600 }}>
                      {dueText(lang, next, home.today)}
                    </span>
                  </div>
                </div>
                {later.length ? (
                  <p className="small muted">{t(lang, "alsoDue")}: {later.map((i) => `${tItemKind(lang, i.kind)} (${when(i)}, ${dueText(lang, i, home.today).toLowerCase()})`).join("; ")}</p>
                ) : null}
              </section>
            ) : <p className="card">{t(lang, "noFollowUp")}</p>}

            {home.appointments.length ? (
              <section className="card">
                <h2>{t(lang, "appointments")}</h2>
                {home.appointments.map((a) => (
                  <p key={a.id}><b>{fmtDate(a.starts_at, lang)}</b>, {a.label.split(", ").slice(-1)[0]}<span className="small muted" style={{ display: "block" }}>{t(lang, "ref", { ref: a.reference })}</span></p>
                ))}
              </section>
            ) : null}

            {home.pending ? (
              <ReplyResult lang={lang} reply={home.pending} tts={home.tts_available} clinicPhone={home.clinic.phone}
                onReply={(r) => { setReply(r); setView("result"); }} onChanged={() => void loadHome()} onUpload={() => setView("report")} />
            ) : null}

            {next ? (
              <div className="big-actions">
                <button className="big big--primary" disabled={busy} onClick={() => choose("CONFIRM")}>{t(lang, "confirm")}</button>
                <button className="big" disabled={busy} onClick={() => choose("RESCHEDULE")}>{t(lang, "reschedule")}</button>
                <button className="big" disabled={busy} onClick={() => setView("barrier")}>{t(lang, "problem")}</button>
                <button className="big" disabled={busy} onClick={() => choose("CALLBACK")}>{t(lang, "callMe")}</button>
              </div>
            ) : (
              <div className="big-actions">
                <button className="big" disabled={busy} onClick={() => choose("CALLBACK")}>{t(lang, "callMe")}</button>
              </div>
            )}

            <section className="card">
              <h2>{t(lang, "ownWords")}</h2>
              <form className="stack" onSubmit={(e) => { e.preventDefault(); if (text.trim()) void send("/v1/p/replies", { text }); }}>
                <textarea id="patient-message" aria-label={t(lang, "typeHere")} placeholder={t(lang, "typeHere")} value={text} onChange={(e) => setText(e.target.value)} />
                <button className="btn" type="submit" disabled={busy || !text.trim()}>{t(lang, "send")}</button>
              </form>
              <VoiceRecorder lang={lang} available={home.voice_available} consented={home.consents.AI_PROCESSING === "GRANTED"}
                onConsent={async () => { await api("/v1/p/consents", { body: { purpose: "AI_PROCESSING", granted: true } }); await loadHome(); }}
                onSent={(r) => { setReply(r); setView("result"); }} />
            </section>

            <div className="pt-foot">
              <button className="pt-link" onClick={() => setView("report")}>{t(lang, "shareReport")}</button>
              <button className="pt-link" onClick={() => setView("passport")}>{t(lang, "passport")}</button>
              <button className="pt-link" onClick={() => setView("family")}>{t(lang, "family")}</button>
              {home.clinic.phone ? <a className="pt-link" href={`tel:${home.clinic.phone}`}>{t(lang, "callClinic", { phone: home.clinic.phone })}</a> : null}
              <span>{t(lang, "emergency")}</span>
              <span>{t(lang, "demoNote")}</span>
            </div>
          </>
        ) : null}

        {view === "result" && reply ? (
          <>
            {back}
            <ReplyResult lang={lang} reply={reply} tts={home.tts_available} clinicPhone={home.clinic.phone}
              onReply={setReply} onChanged={() => void loadHome()} onUpload={() => setView("report")} />
            <p className="pt-foot">{t(lang, "emergency")}</p>
          </>
        ) : null}
        {view === "barrier" ? (<>{back}<BarrierPicker lang={lang} busy={busy} onPick={(k) => choose(`BARRIER:${k}`)} /></>) : null}
        {view === "report" ? (<>{back}<ReportUpload lang={lang} onDone={() => void loadHome()} onViewAnalysis={() => navigateCare("home")} /></>) : null}
        {view === "passport" ? (
          <>
            {back}
            <h1>{t(lang, "passport")}</h1>
            <PassportView lang={lang} busy={busy} onStop={() => choose("STOP")} onStart={() => choose("START")} />
          </>
        ) : null}
        {view === "family" ? (<>{back}<FamilyView lang={lang} /></>) : null}
        <CareNavigation lang={lang} current={view} onSelect={navigateCare} />
      </div>
    </main>
  );
}
