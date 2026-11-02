"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { SlotPicker } from "@/components/patient/reply-result";
import { BrandMark } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { asLang, dueText, LANGS, t, tItemKind, type Lang } from "@/lib/i18n";
import type { AppointmentRequest, Item, Slot } from "@/lib/types";

type CaregiverHome = {
  caregiver_name: string; patient_first_name: string; clinic: { name: string; short_name: string; phone: string }; scopes: string[];
  today: string;
  items: Item[] | null; appointments: { id: string; reference: string; starts_at: string; label: string }[] | null;
  can_request_reschedule: boolean; language: string;
};

export default function CaregiverApp() {
  const { token } = useParams<{ token: string }>();
  const [home, setHome] = useState<CaregiverHome | null>(null);
  const [lang, setLang] = useState<Lang>("en");
  const [broken, setBroken] = useState(false);
  const [dayText, setDayText] = useState("");
  const [windowName, setWindowName] = useState("");
  const [offer, setOffer] = useState<{ request: AppointmentRequest; slots: Slot[]; question: string | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function refresh() {
    setHome(await api<CaregiverHome>("/v1/c/home"));
  }

  useEffect(() => {
    api<CaregiverHome>("/v1/c/session", { body: { token } })
      .then((h) => { setHome(h); setLang(asLang(h.language)); })
      .catch(() => setBroken(true));
  }, [token]);

  async function ask() {
    setBusy(true);
    setProblem(null);
    try {
      setOffer(await api("/v1/c/reschedule", { body: { day_text: dayText, window: windowName || null } }));
    } catch (e) {
      setProblem(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const top = (
    <header className="pt-top">
      <span className="row" style={{ gap: 8 }}><BrandMark className="brand-mark" /><span className="pt-clinic">{home?.clinic.short_name}</span></span>
      <div className="lang" role="group" aria-label="Language">
        {LANGS.map((l) => <button key={l.code} aria-pressed={lang === l.code} onClick={() => setLang(l.code)} lang={l.code}>{l.label}</button>)}
      </div>
    </header>
  );

  if (broken) return <main className="pt"><div className="pt-wrap">{top}<p className="card">{t(lang, "revokedAccess")}</p></div></main>;
  if (!home) return <main className="pt"><div className="pt-wrap">{top}<p className="muted">{t(lang, "loading")}</p></div></main>;

  return (
    <main className="pt" lang={lang}>
      <div className="pt-wrap">
        {top}
        <h1>{t(lang, "caregiverHello", { name: home.caregiver_name.split(" (")[0] })}</h1>
        <p>{t(lang, "caregiverFor", { name: home.patient_first_name, clinic: home.clinic.name })}</p>
        <p className="small muted">{home.scopes.map((s) => t(lang, `scope_${s}`)).join("; ")}</p>

        {home.items ? (
          <section className="card">
            <h2>{t(lang, "nextFollowUp")}</h2>
            {home.items.length === 0 ? <p className="muted">{t(lang, "noFollowUp")}</p> : home.items.map((i) => (
              <p key={i.id} className="spread"><span><b>{tItemKind(lang, i.kind)}</b><span className="small muted" style={{ display: "block" }}>{fmtDate(i.due_date, lang)}</span></span><span className="small">{dueText(lang, i, home.today)}</span></p>
            ))}
          </section>
        ) : null}
        {home.appointments && home.appointments.length ? (
          <section className="card">
            <h2>{t(lang, "appointments")}</h2>
            {home.appointments.map((a) => <p key={a.id}>{fmtDate(a.starts_at, lang)}, {a.label.split(", ").slice(-1)[0]}<span className="small muted" style={{ display: "block" }}>{t(lang, "ref", { ref: a.reference })}</span></p>)}
          </section>
        ) : null}

        {home.can_request_reschedule ? (
          <section className="card">
            <h2>{t(lang, "caregiverAsk")}</h2>
            {offer ? (
              <>
                {offer.question ? <p>{offer.question}</p> : null}
                {offer.request.status === "HANDED_TO_STAFF" ? <p className="notice notice--warn">{t(lang, "notBooked")}</p> : (
                  <SlotPicker lang={lang} slots={offer.slots} requestId={offer.request.id} bookPath="/v1/c/book" onBooked={() => void refresh()} />
                )}
              </>
            ) : (
              <>
                <label className="field"><span>{t(lang, "whichDay")}</span><input type="text" value={dayText} onChange={(e) => setDayText(e.target.value)} /></label>
                <div className="lang" role="group" aria-label="Time of day" style={{ justifySelf: "start" }}>
                  {[["", "anyTime"], ["MORNING", "morning"], ["AFTERNOON", "afternoon"], ["EVENING", "evening"]].map(([k, key]) => (
                    <button key={k} aria-pressed={windowName === k} onClick={() => setWindowName(k)}>{t(lang, key)}</button>
                  ))}
                </div>
                <button className="btn" disabled={busy} onClick={ask}>{t(lang, "showTimes")}</button>
              </>
            )}
            {problem ? <p className="notice notice--fail">{problem}</p> : null}
          </section>
        ) : null}
        <div className="pt-foot">
          {home.clinic.phone ? <a className="pt-link" href={`tel:${home.clinic.phone}`}>{t(lang, "callClinic", { phone: home.clinic.phone })}</a> : null}
          <span>{t(lang, "emergency")}</span>
          <span>{t(lang, "demoNote")}</span>
        </div>
      </div>
    </main>
  );
}
