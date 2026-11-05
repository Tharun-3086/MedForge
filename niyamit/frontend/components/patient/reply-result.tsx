"use client";

import { useEffect, useRef, useState } from "react";

import { api, ApiError, clientKey, usePoll } from "@/lib/api";
import { fmtDate, fmtLongDay, fmtTime } from "@/lib/format";
import { t, tActionStatus, tIntent, type Lang } from "@/lib/i18n";
import type { ReplyAction, Slot } from "@/lib/types";

export type ReplyView = {
  id: string; status: string; processing: boolean; input_mode: string; text: string | null; transcript: string | null;
  corrected_text: string | null; error_code: string | null; can_correct: boolean; created_at: string;
  understood: { intents: string[]; day_words: string | null; time_window: string | null; barrier: string | null; source: string };
  actions: ReplyAction[];
};

type BookResult = { booked: boolean; reason: string; appointment?: { reference: string; label: string; starts_at: string; date: string; with: string } };

export function ReplyResult({ lang, reply, onReply, onChanged, onUpload, tts, clinicPhone }: {
  lang: Lang; reply: ReplyView; onReply: (r: ReplyView) => void; onChanged: () => void; onUpload: () => void;
  tts: boolean; clinicPhone: string;
}) {
  const [correcting, setCorrecting] = useState(false);
  const [fix, setFix] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [audioLoading, setAudioLoading] = useState(false);
  const player = useRef<HTMLAudioElement | null>(null);
  useEffect(() => () => { if (audioUrl) URL.revokeObjectURL(audioUrl); }, [audioUrl]);
  useEffect(() => { setAudioUrl(null); }, [reply.id]);

  usePoll(reply.processing, async () => {
    const fresh = await api<ReplyView>(`/v1/p/replies/${reply.id}`).catch(() => null);
    if (fresh) {
      onReply(fresh);
      if (!fresh.processing) onChanged();
    }
  }, 1000);

  async function call<T>(fn: () => Promise<T>): Promise<T | null> {
    setBusy(true);
    setProblem(null);
    try {
      return await fn();
    } catch (e) {
      setProblem(e instanceof ApiError ? e.message : String(e));
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function button(choice: string) {
    const r = await call(() => api<ReplyView>("/v1/p/replies/button", { body: { choice, client_key: clientKey() } }));
    if (r) {
      onReply(r);
      onChanged();
    }
  }

  async function sendFix() {
    const r = await call(() => api<ReplyView>(`/v1/p/replies/${reply.id}/correct`, { body: { text: fix } }));
    if (r) {
      setCorrecting(false);
      setFix("");
      onReply(r);
      onChanged();
    }
  }

  async function listen(i: number) {
    if (audioLoading) return;
    player.current?.pause();
    setAudioUrl(null);
    setAudioLoading(true);
    const blob = await call(() => api<Blob>(`/v1/p/replies/${reply.id}/audio?i=${i}`));
    if (blob) setAudioUrl(URL.createObjectURL(blob));
    setAudioLoading(false);
  }

  const words = reply.corrected_text || reply.transcript || reply.text;
  const isButton = reply.input_mode === "BUTTON";
  return (
    <section className="card understood" aria-live="polite">
      {!isButton && words ? (
        <div className="stack" style={{ gap: 6 }}>
          <span className="small muted">{reply.input_mode === "VOICE" ? t(lang, "weHeard") : t(lang, "youSaid")}</span>
          <p className="said">{words}</p>
        </div>
      ) : null}
      {reply.processing ? <p className="muted">{t(lang, "working")}</p> : null}
      {reply.understood.intents.includes("OPT_IN") ? <p className="notice notice--ok">{t(lang, "remindersOn")}</p> : null}
      {reply.status === "TRANSCRIPTION_FAILED" ? (
        <p className="notice notice--warn">{reply.error_code === "NO_AI_CONSENT" ? t(lang, "voiceNeedsConsent") : t(lang, "voiceFailed")}</p>
      ) : null}

      {!reply.processing && reply.actions.length > 0 ? (
        <div className="stack">
          <h2>{t(lang, "understood")}</h2>
          {reply.actions.map((a, i) => (
            <ActionBlock key={i} lang={lang} action={a} index={i} busy={busy || audioLoading} tts={tts} clinicPhone={clinicPhone}
              onButton={button} onListen={listen} onUpload={onUpload}
              onOptOut={async (confirm) => {
                const r = await call(() => api<ReplyView>(`/v1/p/replies/${reply.id}/opt-out`, { body: { confirm } }));
                if (r) {
                  onReply(r);
                  onChanged();
                }
              }}
              onBooked={onChanged} />
          ))}
        </div>
      ) : null}

      {audioLoading ? <p role="status">{t(lang, "preparingAudio")}</p> : null}
      {audioUrl ? <div className="stack"><p className="small">{t(lang, "audioReady")}</p>
        <audio ref={player} controls src={audioUrl} style={{ width: "100%" }}
          onCanPlay={() => { void player.current?.play().catch(() => undefined); }}
          onError={() => setProblem(t(lang, "audioFailed"))} />
      </div> : null}
      {problem ? <p role="alert" className="notice notice--fail">{problem}</p> : null}

      {reply.can_correct && !reply.processing ? (
        correcting ? (
          <div className="stack">
            <label className="field"><span>{t(lang, "correctHelp")}</span>
              <textarea value={fix} onChange={(e) => setFix(e.target.value)} />
            </label>
            <button className="btn" disabled={busy || !fix.trim()} onClick={sendFix}>{t(lang, "saveCorrection")}</button>
          </div>
        ) : (
          <button className="pt-link" onClick={() => { setCorrecting(true); setFix(words ?? ""); }}>{t(lang, "correct")}</button>
        )
      ) : null}
    </section>
  );
}

function questionFor(lang: Lang, a: ReplyAction): string | null {
  switch (a.question_key) {
    case "PICK_DAY": return t(lang, "pickDay");
    case "WHICH_DAY": return a.date_options && a.date_options.length === 2
      ? t(lang, "whichOfTwoDays", { a: fmtLongDay(a.date_options[0], lang), b: fmtLongDay(a.date_options[1], lang) })
      : t(lang, "pickDay");
    case "CONFIRM_DAY": return t(lang, "confirmDay", { day: a.day_words ?? "", date: a.candidate_date ? fmtLongDay(a.candidate_date, lang) : "" });
    case "NO_SLOTS_ON_DAY": return t(lang, "noSlotsDay", { date: a.candidate_date ? fmtLongDay(a.candidate_date, lang) : "" });
    case "CONFIRM_MISMATCH": return t(lang, "mismatch", { due: a.due_date ? fmtLongDay(a.due_date, lang) : "", day: a.day_words ?? "" });
    case "CLARIFY": return t(lang, "clarify");
    case "CONFIRM_OPT_OUT": return t(lang, "optOutQuestion");
    default: return a.question ?? null;
  }
}

function ActionBlock({ lang, action: a, index, busy, tts, clinicPhone, onButton, onListen, onOptOut, onUpload, onBooked }: {
  lang: Lang; action: ReplyAction; index: number; busy: boolean; tts: boolean; clinicPhone: string;
  onButton: (choice: string) => void; onListen: (i: number) => void; onOptOut: (confirm: boolean) => void;
  onUpload: () => void; onBooked: () => void;
}) {
  const [booked, setBooked] = useState(false);
  const waiting = a.status.startsWith("AWAITING") && !booked;
  const human = a.status === "HANDED_TO_CLINICIAN" || a.status === "HANDED_TO_STAFF" || a.intent === "URGENT_CONCERN";
  const question = waiting ? questionFor(lang, a) : null;
  const urgent = a.intent === "URGENT_CONCERN";
  return (
    <div className={`act${waiting ? " act--wait" : human ? " act--human" : ""}`}>
      <div className="spread">
        <b>{tIntent(lang, a.intent)}</b>
        <span className="small muted">{tActionStatus(lang, booked ? "BOOKED" : a.status)}</span>
      </div>
      {a.patient_text ? (
        <p className={urgent ? "notice notice--fail" : undefined} style={urgent ? { fontSize: 18 } : undefined}>{a.patient_text}</p>
      ) : null}
      {urgent ? (
        <div className="row">
          <a className="btn btn--danger" href="tel:108">108</a>
          <a className="btn btn--danger" href="tel:112">112</a>
          {clinicPhone ? <a className="btn btn--quiet" href={`tel:${clinicPhone}`}>{t(lang, "callClinic", { phone: clinicPhone })}</a> : null}
        </div>
      ) : null}
      {question ? <p>{question}</p> : null}
      {a.note ? <p className="notice notice--warn">{t(lang, "slotTaken")}</p> : null}
      {a.booking_reference ? <p className="notice notice--ok">{t(lang, "bookedRef", { ref: a.booking_reference })}</p> : null}

      {a.status === "AWAITING_SLOT_CHOICE" ? (
        <SlotPicker lang={lang} slots={a.slots ?? []} requestId={a.request_id ?? null} onBooked={() => { setBooked(true); onBooked(); }} />
      ) : null}
      {a.status === "AWAITING_CONFIRMATION" && a.intent === "OPT_OUT" ? (
        <div className="big-actions">
          <button className="big" disabled={busy} onClick={() => onOptOut(true)}>{t(lang, "yesStop")}</button>
          <button className="big" disabled={busy} onClick={() => onOptOut(false)}>{t(lang, "noKeep")}</button>
        </div>
      ) : null}
      {a.status === "AWAITING_CONFIRMATION" && a.intent === "CONFIRM_FOLLOWUP" ? (
        <div className="big-actions">
          <button className="big big--primary" disabled={busy} onClick={() => onButton("CONFIRM")}>
            {t(lang, "keepDate", { due: a.due_date ? fmtDate(a.due_date, lang) : "" })}
          </button>
          <button className="big" disabled={busy} onClick={() => onButton("RESCHEDULE")}>{t(lang, "reschedule")}</button>
        </div>
      ) : null}
      {a.status === "AWAITING_CLARIFICATION" ? (
        <div className="big-actions">
          {(a.options ?? ["CONFIRM", "RESCHEDULE", "CALLBACK"]).map((o) => (
            <button key={o} className="big" disabled={busy} onClick={() => onButton(o)}>
              {o === "CONFIRM" ? t(lang, "confirm") : o === "RESCHEDULE" ? t(lang, "reschedule") : t(lang, "callMe")}
            </button>
          ))}
        </div>
      ) : null}
      {a.status === "AWAITING_UPLOAD" ? <button className="btn btn--quiet" onClick={onUpload}>{t(lang, "shareReport")}</button> : null}
      {tts && (a.patient_text || question) ? (
        <button className="pt-link" disabled={busy} onClick={() => onListen(index)}>{t(lang, "listen")}</button>
      ) : null}
    </div>
  );
}

export function SlotPicker({ lang, slots: initial, requestId, onBooked, bookPath = "/v1/p/book" }: {
  lang: Lang; slots: Slot[]; requestId: string | null; onBooked: () => void; bookPath?: string;
}) {
  const [slots, setSlots] = useState<Slot[]>(initial);
  const [chosen, setChosen] = useState<Slot | null>(null);
  const [result, setResult] = useState<BookResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [down, setDown] = useState(false);

  async function more() {
    setBusy(true);
    try {
      const r = await api<{ slots: Slot[] }>("/v1/p/slots");
      setSlots(r.slots);
    } catch {
      setDown(true);
    } finally {
      setBusy(false);
    }
  }

  async function book() {
    if (!chosen) return;
    setBusy(true);
    try {
      const body: Record<string, unknown> = { slot_id: chosen.id, request_id: requestId };
      if (bookPath === "/v1/p/book") body.client_key = clientKey();
      const r = await api<BookResult>(bookPath, { body });
      setResult(r);
      if (r.booked) onBooked();
      else if (r.reason === "SLOT_UNAVAILABLE") {
        setChosen(null);
        if (bookPath === "/v1/p/book") await more();
        else setSlots((list) => list.filter((s) => s.id !== chosen.id));
      }
    } catch {
      setResult({ booked: false, reason: "PROVIDER_UNAVAILABLE" });
    } finally {
      setBusy(false);
    }
  }

  if (result?.booked && result.appointment) {
    const when = `${fmtLongDay(result.appointment.date, lang)}, ${fmtTime(result.appointment.starts_at, lang)}`;
    return <p className="notice notice--ok" style={{ fontSize: 18 }}>{t(lang, "booked", { time: when, ref: result.appointment.reference })}</p>;
  }
  if (down || result?.reason === "PROVIDER_UNAVAILABLE") return <p className="notice notice--warn">{t(lang, "notBooked")}</p>;
  const groups = new Map<string, Slot[]>();
  slots.forEach((s) => groups.set(s.date, [...(groups.get(s.date) ?? []), s]));
  return (
    <div className="stack" style={{ gap: 8 }}>
      {result && result.reason === "SLOT_UNAVAILABLE" ? <p className="notice notice--warn">{t(lang, "slotTaken")}</p> : null}
      {slots.length === 0 ? <p className="muted">{t(lang, "noSlots")}</p> : null}
      {Array.from(groups.entries()).map(([date, list]) => (
        <div key={date} className="stack" style={{ gap: 6 }}>
          <span className="day-label">{fmtLongDay(date, lang)}</span>
          <div className="slots">
            {list.map((s) => (
              <button key={s.id} className="slot" aria-pressed={chosen?.id === s.id} onClick={() => setChosen(s)}>
                {fmtTime(s.starts_at, lang)}
              </button>
            ))}
          </div>
        </div>
      ))}
      {chosen ? (
        <button className="btn" disabled={busy} onClick={book}>{t(lang, "book", { time: `${fmtLongDay(chosen.date, lang)}, ${fmtTime(chosen.starts_at, lang)}` })}</button>
      ) : slots.length < 6 && bookPath === "/v1/p/book" ? (
        <button className="pt-link" disabled={busy} onClick={more}>{t(lang, "showTimes")}</button>
      ) : null}
    </div>
  );
}
