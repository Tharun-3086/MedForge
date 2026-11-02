"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import type { ApiError } from "@/lib/api";
import type { Provenance as ProvenanceKind } from "@/lib/types";

/* --------------------------------------------------------------- brand */
export function BrandMark({ className = "brand-mark" }: { className?: string }) {
  // Follow-ups at regular intervals; the amber one is due.
  const dots = Array.from({ length: 8 }, (_, i) => {
    const a = (i / 8) * Math.PI * 2 - Math.PI / 2;
    return { x: 16 + Math.cos(a) * 11, y: 16 + Math.sin(a) * 11, due: i === 0 };
  });
  return (
    <svg className={className} viewBox="0 0 32 32" aria-hidden="true">
      {dots.map((d, i) => (
        <circle key={i} cx={d.x} cy={d.y} r={d.due ? 3.6 : 2.1} fill={d.due ? "#F2A65A" : "#7FB7C9"} />
      ))}
    </svg>
  );
}

/* --------------------------------------------------------------- provenance and status */
const PROVENANCE: Record<ProvenanceKind, [string, string]> = {
  PATIENT_REPORTED: ["prov--patient", "Patient said"],
  AI_PROPOSED: ["prov--ai", "AI proposed, unverified"],
  STAFF_CONFIRMED: ["prov--staff", "Staff confirmed"],
  CLINICIAN_APPROVED: ["prov--clinician", "Clinician approved"],
  SYSTEM_EVENT: ["prov--system", "System"],
};

export function Provenance({ kind, label }: { kind: ProvenanceKind; label?: string }) {
  const [cls, text] = PROVENANCE[kind] ?? PROVENANCE.SYSTEM_EVENT;
  return <span className={`prov ${cls}`}>{label ?? text}</span>;
}

type Tone = "neutral" | "wait" | "done" | "fail" | "info" | "urgent";

export function Pill({ tone = "neutral", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span className={`pill${tone === "neutral" ? "" : ` pill--${tone}`}`} title={title}>
      {children}
    </span>
  );
}

const MESSAGE_TONE: Record<string, Tone> = {
  DELIVERED: "done", FAILED: "fail", UNKNOWN: "fail", SUPPRESSED: "neutral", SCHEDULED: "info",
  QUEUED: "info", SENDING: "info", SENT_TO_PROVIDER: "wait",
};
export function MessageStatus({ status, label }: { status: string; label: string }) {
  return <Pill tone={MESSAGE_TONE[status] ?? "neutral"}>{label}</Pill>;
}

const TASK_TONE: Record<string, Tone> = {
  OPEN: "wait", ASSIGNED: "info", IN_PROGRESS: "info", RESOLVED: "done", UNABLE_TO_RESOLVE: "fail", CANCELLED: "neutral",
};
export function TaskStatus({ status }: { status: string }) {
  const label = { OPEN: "Open", ASSIGNED: "Assigned", IN_PROGRESS: "In progress", RESOLVED: "Resolved",
    UNABLE_TO_RESOLVE: "Unable to resolve", CANCELLED: "Cancelled" }[status] ?? status;
  return <Pill tone={TASK_TONE[status] ?? "neutral"}>{label}</Pill>;
}

const REPLY_LABEL: Record<string, [string, Tone]> = {
  RECEIVED: ["Received, not processed yet", "info"], VALIDATED: ["Processing", "info"],
  TRANSCRIPTION_FAILED: ["Voice not understood", "fail"], CLASSIFIED: ["Understood", "info"],
  NEEDS_CLARIFICATION: ["Asked the patient to clarify", "wait"], NEEDS_CONFIRMATION: ["Waiting for the patient's choice", "wait"],
  ROUTED: ["Routed to staff", "info"], ACTION_PENDING: ["Action pending", "info"], ACTION_SUCCEEDED: ["Done", "done"],
  ACTION_FAILED: ["Action failed", "fail"], HUMAN_HANDOFF: ["Handed to a person", "wait"],
};
export function ReplyStatus({ status }: { status: string }) {
  const [label, tone] = REPLY_LABEL[status] ?? [status, "neutral" as Tone];
  return <Pill tone={tone}>{label}</Pill>;
}

/* --------------------------------------------------------------- feedback */
export function ErrorNote({ error }: { error: ApiError | Error | string | null | undefined }) {
  if (!error) return null;
  const text = typeof error === "string" ? error : error.message;
  return <p className="notice notice--fail" role="alert">{text}</p>;
}

export function Loading({ text = "Loading…" }: { text?: string }) {
  return <p className="muted" aria-live="polite">{text}</p>;
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {children ? <p className="muted">{children}</p> : null}
      {action}
    </div>
  );
}

/* --------------------------------------------------------------- dialog */
export function Modal({ open, title, onClose, children, footer }: {
  open: boolean; title: string; onClose: () => void; children: ReactNode; footer?: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);
  return (
    <dialog ref={ref} className="modal" onClose={onClose} aria-labelledby="modal-title">
      {open ? (
        <>
          <div className="modal-body">
            <h2 id="modal-title">{title}</h2>
            {children}
          </div>
          {footer ? <div className="modal-foot">{footer}</div> : null}
        </>
      ) : null}
    </dialog>
  );
}

/* --------------------------------------------------------------- toasts */
type Toast = { id: number; text: string; fail?: boolean };
const ToastContext = createContext<(text: string, fail?: boolean) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((text: string, fail = false) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, fail }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), fail ? 7000 : 4000);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast${t.fail ? " toast--fail" : ""}`}>{t.text}</div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);

/** Runs an async action with a busy flag and a toast for the outcome. */
export function useAction() {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const run = useCallback(
    async <T,>(fn: () => Promise<T>, success?: string | ((r: T) => string)): Promise<T | null> => {
      setBusy(true);
      try {
        const result = await fn();
        if (success) toast(typeof success === "function" ? success(result) : success);
        return result;
      } catch (e) {
        toast(e instanceof Error ? e.message : "Something went wrong.", true);
        return null;
      } finally {
        setBusy(false);
      }
    },
    [toast],
  );
  return { busy, run };
}
