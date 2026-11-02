"use client";

import { useEffect, useRef, useState } from "react";

import { api, clientKey } from "@/lib/api";
import { t, type Lang } from "@/lib/i18n";

import type { ReplyView } from "./reply-result";

const LIMIT_SECONDS = 28; // the speech service accepts recordings under 30 seconds

function pickType(): { mime: string; ext: string } | null {
  if (typeof MediaRecorder === "undefined") return null;
  const options = [
    { mime: "audio/webm;codecs=opus", ext: "webm" },
    { mime: "audio/ogg;codecs=opus", ext: "ogg" },
    { mime: "audio/mp4", ext: "m4a" },
    { mime: "audio/webm", ext: "webm" },
  ];
  return options.find((o) => MediaRecorder.isTypeSupported(o.mime)) ?? null;
}

/** Tap to record, tap again to send. Text and buttons always remain available. */
export function VoiceRecorder({ lang, available, consented, onConsent, onSent }: {
  lang: Lang; available: boolean; consented: boolean; onConsent: () => Promise<void>; onSent: (r: ReplyView) => void;
}) {
  const [state, setState] = useState<"idle" | "asking" | "recording" | "sending">("idle");
  const [left, setLeft] = useState(LIMIT_SECONDS);
  const [problem, setProblem] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const timer = useRef<number | null>(null);
  const type = useRef<{ mime: string; ext: string } | null>(null);

  useEffect(() => () => {
    if (timer.current) window.clearInterval(timer.current);
    recorder.current?.stream.getTracks().forEach((tr) => tr.stop());
  }, []);
  useEffect(() => {
    if (state === "recording" && left <= 0) stop();
  }, [left, state]);

  // Decided after mount, so a server render and the first browser render always match.
  const [supported, setSupported] = useState(false);
  useEffect(() => setSupported(Boolean(navigator.mediaDevices?.getUserMedia) && pickType() !== null), []);
  if (!available || !supported) return <p className="small muted">{t(lang, "voiceOff")}</p>;

  async function start() {
    setProblem(null);
    if (!consented) {
      setState("asking");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      type.current = pickType();
      const rec = new MediaRecorder(stream, type.current ? { mimeType: type.current.mime } : undefined);
      chunks.current = [];
      rec.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      rec.onstop = () => void upload(stream);
      recorder.current = rec;
      rec.start();
      setState("recording");
      setLeft(LIMIT_SECONDS);
      timer.current = window.setInterval(() => setLeft((s) => s - 1), 1000);
    } catch {
      setProblem(t(lang, "micBlocked"));
      setState("idle");
    }
  }

  function stop() {
    if (timer.current) window.clearInterval(timer.current);
    timer.current = null;
    if (recorder.current?.state === "recording") recorder.current.stop();
  }

  async function upload(stream: MediaStream) {
    stream.getTracks().forEach((tr) => tr.stop());
    setState("sending");
    const ext = type.current?.ext ?? "webm";
    const blob = new Blob(chunks.current, { type: type.current?.mime.split(";")[0] ?? "audio/webm" });
    const form = new FormData();
    form.set("audio", blob, `voice.${ext}`);
    form.set("client_key", clientKey());
    try {
      onSent(await api<ReplyView>("/v1/p/replies/voice", { form }));
    } catch (e) {
      setProblem(e instanceof Error ? e.message : t(lang, "voiceFailed"));
    } finally {
      setState("idle");
    }
  }

  if (state === "asking") {
    return (
      <div className="card" role="dialog" aria-labelledby="consent-title">
        <h2 id="consent-title">{t(lang, "aiConsentTitle")}</h2>
        <p>{t(lang, "aiConsentBody")}</p>
        <div className="big-actions">
          <button className="big big--primary" onClick={async () => { await onConsent(); setState("idle"); }}>{t(lang, "allow")}</button>
          <button className="big" onClick={() => setState("idle")}>{t(lang, "notNow")}</button>
        </div>
      </div>
    );
  }
  return (
    <div className="stack" style={{ gap: 8 }}>
      {state === "recording" ? (
        <button className="record record--on" onClick={stop} aria-live="polite">{t(lang, "stopSend", { s: left })}</button>
      ) : (
        <button className="record" onClick={start} disabled={state === "sending"}>
          <svg className="ico" viewBox="0 0 24 24" aria-hidden="true" width="24" height="24"><path fill="currentColor" d="M12 15a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-2.08A7 7 0 0 0 19 12h-2Z" /></svg>
          {state === "sending" ? t(lang, "uploading") : t(lang, "record")}
        </button>
      )}
      {problem ? <p className="notice notice--warn">{problem}</p> : null}
    </div>
  );
}
