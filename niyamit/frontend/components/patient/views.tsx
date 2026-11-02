"use client";

import { useState } from "react";

import { api, ApiError, useApi } from "@/lib/api";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { BARRIER_KEYS, t, tBarrier, tItemKind, tItemStatus, tMessageStatus, tRequestStatus, type Lang } from "@/lib/i18n";
import type { AppointmentRequest, Plan } from "@/lib/types";

export function BarrierPicker({ lang, busy, onPick }: { lang: Lang; busy: boolean; onPick: (key: string) => void }) {
  return (
    <section className="card">
      <h2>{t(lang, "barrierTitle")}</h2>
      <p className="muted">{t(lang, "barrierHelp")}</p>
      <div className="big-actions">
        {BARRIER_KEYS.map((k) => (
          <button key={k} className="big" disabled={busy} onClick={() => onPick(k)}>{tBarrier(lang, k)}</button>
        ))}
      </div>
    </section>
  );
}

export function ReportUpload({ lang, onDone }: { lang: Lang; onDone: () => void }) {
  const [state, setState] = useState<"idle" | "sending" | "done">("idle");
  const [problem, setProblem] = useState<string | null>(null);

  async function send(file: File) {
    setState("sending");
    setProblem(null);
    const form = new FormData();
    form.set("file", file);
    form.set("source_type", "LAB_REPORT");
    try {
      await api("/v1/p/documents", { form });
      setState("done");
      onDone();
    } catch (e) {
      setProblem(e instanceof ApiError ? e.message : String(e));
      setState("idle");
    }
  }

  return (
    <section className="card">
      <h2>{t(lang, "shareReport")}</h2>
      <p className="muted">{t(lang, "shareReportHelp")}</p>
      {state === "done" ? <p className="notice notice--ok">{t(lang, "reportReceived")}</p> : (
        <label className="record" style={{ cursor: state === "sending" ? "wait" : "pointer" }}>
          {state === "sending" ? t(lang, "uploading") : t(lang, "chooseFile")}
          <input type="file" accept="image/*,application/pdf" className="sr-only" disabled={state === "sending"}
            onChange={(e) => e.target.files?.[0] && void send(e.target.files[0])} />
        </label>
      )}
      {problem ? <p className="notice notice--fail">{problem}</p> : null}
    </section>
  );
}

type Passport = {
  patient: { name: string; language: string; opted_out: boolean };
  clinic: { name: string; phone: string };
  plan: Plan | null;
  checklist: { label: string; due_date: string; status: string }[];
  appointments: { id: string; status: string; reference: string; slot_label: string | null }[];
  requests: AppointmentRequest[];
  you_told_us: { what: string; your_words: string | null; barrier: string | null; status: string; at: string }[];
  documents: { filename: string; uploaded_at: string }[];
  messages: { kind: string; status_label: string; at: string; channel: string }[];
  consents: Record<string, string>;
};

export function PassportView({ lang, onStop, onStart, busy }: { lang: Lang; onStop: () => void; onStart: () => void; busy: boolean }) {
  const { data, error } = useApi<Passport>("/v1/p/passport");
  const [confirmStop, setConfirmStop] = useState(false);
  if (error) return <p className="notice notice--fail">{error.message}</p>;
  if (!data) return <p className="muted">{t(lang, "loading")}</p>;
  const plan = data.plan;
  return (
    <div className="stack" style={{ gap: 16 }}>
      <section className="card">
        <h2>{t(lang, "planTitle")}</h2>
        {plan ? (
          <>
            <p className="small muted">{t(lang, "planApproved", { date: fmtDate(plan.approved_at, lang) })}</p>
            <ul className="stack" style={{ listStyle: "none", padding: 0, margin: 0, gap: 8 }}>
              {plan.items.filter((i) => i.status !== "CANCELLED").map((i) => (
                <li key={i.id} className="spread">
                  <span><b>{tItemKind(lang, i.kind)}</b><span className="small muted" style={{ display: "block" }}>{fmtDate(i.due_date, lang)}</span></span>
                  <span className="small">{tItemStatus(lang, i.status)}</span>
                </li>
              ))}
            </ul>
          </>
        ) : <p className="muted">{t(lang, "noFollowUp")}</p>}
      </section>

      {data.appointments.length ? (
        <section className="card">
          <h2>{t(lang, "appointments")}</h2>
          {data.appointments.map((a) => <p key={a.id}>{a.slot_label}<span className="small muted" style={{ display: "block" }}>{t(lang, "ref", { ref: a.reference })}</span></p>)}
        </section>
      ) : null}

      {data.requests.length ? (
        <section className="card">
          <h2>{t(lang, "requests")}</h2>
          {data.requests.map((r) => (
            <p key={r.id} className="spread"><span>{r.requested_day_text ? `“${r.requested_day_text}”` : fmtDate(r.created_at, lang)}</span><span className="small">{tRequestStatus(lang, r.status)}</span></p>
          ))}
        </section>
      ) : null}

      <section className="card">
        <h2>{t(lang, "toldUs")}</h2>
        {data.you_told_us.length === 0 ? <p className="muted">{t(lang, "nothingYet")}</p> : data.you_told_us.map((x, i) => (
          <div key={i} className="stack" style={{ gap: 2 }}>
            <span className="said">{x.your_words ? `“${x.your_words}”` : x.barrier ? tBarrier(lang, x.barrier) : x.what}</span>
            <span className="small muted">{fmtDateTime(x.at, lang)}, {x.status === "Closed" ? t(lang, "closed") : t(lang, "workingOnIt")}</span>
          </div>
        ))}
      </section>

      {data.documents.length ? (
        <section className="card">
          <h2>{t(lang, "documents")}</h2>
          {data.documents.map((d, i) => <p key={i}>{d.filename}<span className="small muted" style={{ display: "block" }}>{fmtDateTime(d.uploaded_at, lang)}</span></p>)}
        </section>
      ) : null}

      {data.messages.length ? (
        <section className="card">
          <h2>{t(lang, "messages")}</h2>
          {data.messages.map((m, i) => (
            <p key={i} className="spread small"><span>{fmtDateTime(m.at, lang)}</span><span>{tMessageStatus(lang, statusKey(m.status_label))}</span></p>
          ))}
        </section>
      ) : null}

      <section className="card">
        <h2>{t(lang, "reminders")}</h2>
        <p>{data.patient.opted_out ? t(lang, "remindersOff") : t(lang, "remindersOn")}</p>
        {data.patient.opted_out ? (
          <button className="btn" disabled={busy} onClick={onStart}>{t(lang, "startReminders")}</button>
        ) : confirmStop ? (
          <div className="stack">
            <p>{t(lang, "optOutQuestion")}</p>
            <div className="big-actions">
              <button className="big" disabled={busy} onClick={onStop}>{t(lang, "yesStop")}</button>
              <button className="big" onClick={() => setConfirmStop(false)}>{t(lang, "noKeep")}</button>
            </div>
          </div>
        ) : (
          <button className="btn btn--quiet" onClick={() => setConfirmStop(true)}>{t(lang, "stopReminders")}</button>
        )}
      </section>
    </div>
  );
}

function statusKey(label: string): string {
  if (label.startsWith("Delivered")) return "DELIVERED";
  if (label.startsWith("Sent")) return "SENT_TO_PROVIDER";
  if (label.startsWith("Failed")) return "FAILED";
  if (label.startsWith("Suppressed")) return "SUPPRESSED";
  if (label.startsWith("Status unknown")) return "UNKNOWN";
  return "QUEUED";
}

type Grant = { id: string; name: string; phone: string; scopes: string[]; status: string; expires_at: string; revoked_at: string | null };

export function FamilyView({ lang }: { lang: Lang }) {
  const { data, reload } = useApi<{ caregivers: Grant[] }>("/v1/p/caregivers");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [scopes, setScopes] = useState<string[]>(["VIEW_APPOINTMENTS"]);
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function invite() {
    setBusy(true);
    setProblem(null);
    try {
      const r = await api<{ link: string }>("/v1/p/caregivers", { body: { name, phone, scopes } });
      setLink(r.link);
      setName("");
      setPhone("");
      await reload();
    } catch (e) {
      setProblem(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function revoke(id: string) {
    setBusy(true);
    try {
      await api(`/v1/p/caregivers/${id}`, { method: "DELETE" });
      await reload();
    } finally {
      setBusy(false);
    }
  }

  async function share() {
    if (!link) return;
    if (navigator.share) {
      await navigator.share({ url: link }).catch(() => undefined);
      return;
    }
    await navigator.clipboard?.writeText(link);
    setCopied(true);
  }

  const active = (data?.caregivers ?? []).filter((g) => g.status === "ACTIVE");
  return (
    <div className="stack" style={{ gap: 16 }}>
      <section className="card">
        <h2>{t(lang, "family")}</h2>
        <p className="muted">{t(lang, "familyHelp")}</p>
        {active.map((g) => (
          <div key={g.id} className="spread">
            <span><b>{g.name}</b><span className="small muted" style={{ display: "block" }}>{g.scopes.map((s) => t(lang, `scope_${s}`)).join("; ")}</span></span>
            <button className="btn btn--quiet" disabled={busy} onClick={() => revoke(g.id)}>{t(lang, "removeAccess")}</button>
          </div>
        ))}
      </section>
      <section className="card">
        <label className="field"><span>{t(lang, "theirName")}</span><input type="text" value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label className="field"><span>{t(lang, "theirPhone")}</span><input type="tel" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} /></label>
        {["VIEW_APPOINTMENTS", "REQUEST_RESCHEDULE"].map((s) => (
          <label key={s} className="check">
            <input type="checkbox" checked={scopes.includes(s)} onChange={(e) => setScopes((c) => e.target.checked ? [...c, s] : c.filter((x) => x !== s))} />
            <span>{t(lang, `scope_${s}`)}</span>
          </label>
        ))}
        <button className="btn" disabled={busy || !name.trim() || !phone.trim() || scopes.length === 0} onClick={invite}>{t(lang, "giveAccess")}</button>
        {problem ? <p className="notice notice--fail">{problem}</p> : null}
        {link ? (
          <div className="stack">
            <p>{t(lang, "shareLink")}</p>
            <input type="text" readOnly value={link} onFocus={(e) => e.currentTarget.select()} />
            <button className="btn btn--quiet" onClick={share}>{copied ? t(lang, "copied") : t(lang, "copyLink")}</button>
          </div>
        ) : null}
      </section>
    </div>
  );
}
