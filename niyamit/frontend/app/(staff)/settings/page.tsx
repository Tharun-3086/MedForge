"use client";

import { useEffect, useState } from "react";

import { StaffAccess } from "@/components/staff-access";
import { templateName } from "@/components/outcomes";
import { PageHead } from "@/components/staff-shell";
import { ErrorNote, Loading, Pill, useAction } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useStaff } from "@/lib/staff-context";

type Clinic = {
  name: string; timezone: string; phone: string; quiet_hours_start: number; quiet_hours_end: number; reminder_send_hour: number;
  reminder_offsets_days: number[]; overdue_nudge_days: number[]; overdue_task_after_days: number; plan_approver_roles: string[];
  clinical_queue: string; urgent_queue: string; task_due_hours: number; require_patient_verification: boolean;
  audio_retention_days: number; document_retention_days: number; message_unit_cost_inr: number;
};
type Providers = {
  llm: { configured: string; active: string }; asr: { configured: string; active: string }; tts: { configured: string; active: string };
  documents: { configured: string; vision: string | null; local_ocr: string }; sarvam_key_present: boolean; openai_key_present: boolean;
  whatsapp: { enabled: boolean; configured: boolean; reminder_template: string | null }; demo_mode: boolean; tasks_mode: string;
};
type Template = { id: string; key: string; language: string; version: number; body: string; status: string; approved_by: string; approved_at: string | null; placeholders: string[] };

const LANG = { en: "English", hi: "Hindi", te: "Telugu" } as Record<string, string>;
const listToText = (v: number[]) => v.join(", ");
const textToList = (v: string) => v.split(",").map((x) => Number(x.trim())).filter((x) => !Number.isNaN(x));

export default function SettingsPage() {
  const { me, can } = useStaff();
  const isAdmin = me.user.role === "ADMIN";
  const canTemplates = ["ADMIN", "DOCTOR"].includes(me.user.role);
  const clinic = useApi<Clinic>("/v1/clinic");
  const providers = useApi<Providers>("/v1/providers");
  const templates = useApi<{ templates: Template[] }>(can("patients") || isAdmin ? "/v1/clinic/templates" : null);
  const { busy, run } = useAction();
  const [form, setForm] = useState<Record<string, string | boolean | string[]>>({});
  const [draftFor, setDraftFor] = useState<Template | null>(null);
  const [draftBody, setDraftBody] = useState("");

  useEffect(() => {
    const c = clinic.data;
    if (!c) return;
    setForm({
      phone: c.phone, quiet_hours_start: String(c.quiet_hours_start), quiet_hours_end: String(c.quiet_hours_end),
      reminder_send_hour: String(c.reminder_send_hour), reminder_offsets_days: listToText(c.reminder_offsets_days),
      overdue_nudge_days: listToText(c.overdue_nudge_days), overdue_task_after_days: String(c.overdue_task_after_days),
      plan_approver_roles: c.plan_approver_roles, clinical_queue: c.clinical_queue, urgent_queue: c.urgent_queue,
      task_due_hours: String(c.task_due_hours), require_patient_verification: c.require_patient_verification,
      audio_retention_days: String(c.audio_retention_days), document_retention_days: String(c.document_retention_days),
      message_unit_cost_inr: String(c.message_unit_cost_inr),
    });
  }, [clinic.data]);

  async function save() {
    const f = form;
    const body = {
      phone: f.phone, quiet_hours_start: Number(f.quiet_hours_start), quiet_hours_end: Number(f.quiet_hours_end),
      reminder_send_hour: Number(f.reminder_send_hour), reminder_offsets_days: textToList(String(f.reminder_offsets_days)),
      overdue_nudge_days: textToList(String(f.overdue_nudge_days)), overdue_task_after_days: Number(f.overdue_task_after_days),
      plan_approver_roles: f.plan_approver_roles, clinical_queue: f.clinical_queue, urgent_queue: f.urgent_queue,
      task_due_hours: Number(f.task_due_hours), require_patient_verification: f.require_patient_verification,
      audio_retention_days: Number(f.audio_retention_days), document_retention_days: Number(f.document_retention_days),
      message_unit_cost_inr: Number(f.message_unit_cost_inr),
    };
    const r = await run(() => api<Clinic>("/v1/clinic", { method: "PATCH", body }), "Settings saved. The change is in the audit log.");
    if (r) clinic.setData(r);
  }

  async function draft() {
    if (!draftFor) return;
    const r = await run(() => api("/v1/clinic/templates", { body: { key: draftFor.key, language: draftFor.language, body: draftBody } }), "Draft saved. It is not used until approved.");
    if (r) {
      setDraftFor(null);
      await templates.reload();
    }
  }

  const input = (key: string, label: string, hint?: string, type = "text") => (
    <label className="field">
      <span>{label}</span>
      <input type={type} value={String(form[key] ?? "")} disabled={!isAdmin} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
      {hint ? <small>{hint}</small> : null}
    </label>
  );

  const grouped = new Map<string, Template[]>();
  templates.data?.templates.forEach((t) => grouped.set(t.key, [...(grouped.get(t.key) ?? []), t]));

  return (
    <>
      <PageHead title="Settings" lede={isAdmin ? "Clinic rules for reminders, queues and retention. Every change is written to the audit log." : "Clinic rules. Only a clinic admin can change them."} />
      <div className="stack-l">
        {isAdmin ? <StaffAccess /> : null}
        <section className="panel stack">
          <h2 style={{ fontSize: 19 }}>AI and messaging</h2>
          <ErrorNote error={providers.error} />
          {providers.data ? (
            <>
              <dl className="kv">
                <dt>Understanding replies</dt><dd>{providers.data.llm.active}</dd>
                <dt>Voice to text</dt><dd>{providers.data.asr.active}</dd>
                <dt>Read-aloud</dt><dd>{providers.data.tts.active}</dd>
                <dt>Reading documents</dt><dd>{providers.data.documents.vision ?? "On this server only"} (OCR: {providers.data.documents.local_ocr})</dd>
                <dt>Sarvam AI key</dt><dd>{providers.data.sarvam_key_present ? <Pill tone="done">Added</Pill> : <Pill>Not added</Pill>}</dd>
                <dt>OpenAI key</dt><dd>{providers.data.openai_key_present ? <Pill tone="done">Added</Pill> : <Pill>Not added (optional)</Pill>}</dd>
                <dt>WhatsApp</dt><dd>{providers.data.whatsapp.configured && providers.data.whatsapp.enabled ? "Connected" : "Not connected: messages go to the simulated phone"}</dd>
                <dt>Background jobs</dt><dd>{providers.data.tasks_mode === "celery" ? "Celery worker" : "Inline"}</dd>
              </dl>
              {!providers.data.sarvam_key_present ? (
                <p className="notice small">Without a Sarvam key, replies are understood by offline rules and voice notes are turned off. Add <code>SARVAM_API_KEY</code> to <code>backend/.env</code> and restart to switch Sarvam on. Keys are never shown here.</p>
              ) : null}
            </>
          ) : <Loading />}
        </section>

        <section className="panel stack">
          <div className="spread">
            <h2 style={{ fontSize: 19 }}>Clinic rules</h2>
            {isAdmin ? <button className="btn" disabled={busy} onClick={save}>Save changes</button> : null}
          </div>
          <ErrorNote error={clinic.error} />
          {clinic.data ? (
            <>
              <p className="small muted">{clinic.data.name}, time zone {clinic.data.timezone}.</p>
              <div className="form-grid">
                {input("phone", "Clinic phone", "Shown in messages for patients who need help.")}
                {input("quiet_hours_start", "Quiet hours start (hour)", "No reminders from this hour…", "number")}
                {input("quiet_hours_end", "Quiet hours end (hour)", "…until this hour.", "number")}
                {input("reminder_send_hour", "Reminder hour", "Local hour reminders are sent.", "number")}
                {input("reminder_offsets_days", "Reminders before the due date", "Days relative to the due date, e.g. -3, -1, 0")}
                {input("overdue_nudge_days", "Reminders after a missed date", "Days after the due date, e.g. 3, 7")}
                {input("overdue_task_after_days", "Open a call task after (days late)", undefined, "number")}
                {input("task_due_hours", "Tasks are due within (hours)", undefined, "number")}
                {input("audio_retention_days", "Keep voice notes for (days)", undefined, "number")}
                {input("document_retention_days", "Keep documents for (days)", undefined, "number")}
                {input("message_unit_cost_inr", "Cost per message (₹, for the estimate)", undefined, "number")}
                <label className="field"><span>Clinical questions go to</span>
                  <select disabled={!isAdmin} value={String(form.clinical_queue ?? "")} onChange={(e) => setForm({ ...form, clinical_queue: e.target.value })}>
                    <option value="NURSE">Nurse queue</option><option value="DOCTOR">Doctor queue</option>
                  </select>
                </label>
                <label className="field"><span>Possible urgent concerns go to</span>
                  <select disabled={!isAdmin} value={String(form.urgent_queue ?? "")} onChange={(e) => setForm({ ...form, urgent_queue: e.target.value })}>
                    <option value="DOCTOR">Doctor queue</option><option value="NURSE">Nurse queue</option>
                  </select>
                </label>
              </div>
              <fieldset className="choice-row">
                <legend>Who can approve plans</legend>
                {["DOCTOR", "NURSE"].map((role) => (
                  <label key={role} className="check">
                    <input type="checkbox" disabled={!isAdmin} checked={(form.plan_approver_roles as string[] | undefined)?.includes(role) ?? false}
                      onChange={(e) => {
                        const current = (form.plan_approver_roles as string[]) ?? [];
                        setForm({ ...form, plan_approver_roles: e.target.checked ? [...current, role] : current.filter((r) => r !== role) });
                      }} />
                    <span>{role === "DOCTOR" ? "Doctors" : "Nurses"}</span>
                  </label>
                ))}
              </fieldset>
              <fieldset className="choice-row">
                <legend>Patient app</legend>
                <label className="check">
                  <input type="checkbox" disabled={!isAdmin} checked={Boolean(form.require_patient_verification)} onChange={(e) => setForm({ ...form, require_patient_verification: e.target.checked })} />
                  <span>Patients confirm their year of birth before seeing details</span>
                </label>
              </fieldset>
            </>
          ) : <Loading />}
        </section>

        {templates.data ? (
          <section className="panel stack">
            <h2 style={{ fontSize: 19 }}>Message templates</h2>
            <p className="small muted">Only approved wording is ever sent. The demo wording is a draft and must be reviewed by the clinical lead before real use. Reminders deliberately say nothing about diabetes, so a lock screen reveals no health details.</p>
            {Array.from(grouped.entries()).map(([key, list]) => (
              <details key={key}>
                <summary style={{ cursor: "pointer", fontWeight: 600 }}>{templateName(key)}</summary>
                <div className="stack" style={{ marginTop: 8 }}>
                  {list.map((t) => (
                    <div key={t.id} className="stack" style={{ gap: 4, borderLeft: `3px solid ${t.status === "APPROVED" ? "var(--approve)" : t.status === "DRAFT" ? "var(--amber-bright)" : "var(--rule)"}`, paddingLeft: 10 }}>
                      <span className="row small">
                        <b>{LANG[t.language]}</b> v{t.version}
                        <Pill tone={t.status === "APPROVED" ? "done" : t.status === "DRAFT" ? "wait" : "neutral"}>{t.status.toLowerCase()}</Pill>
                        {t.approved_at ? <span className="muted">{t.approved_by}, {fmtDateTime(t.approved_at)}</span> : null}
                      </span>
                      <span>{t.body}</span>
                      {canTemplates ? (
                        <span className="row">
                          {t.status === "APPROVED" ? <button className="btn btn--ghost btn--small" onClick={() => { setDraftFor(t); setDraftBody(t.body); }}>Draft new wording</button> : null}
                          {t.status === "DRAFT" ? <button className="btn btn--approve btn--small" disabled={busy}
                            onClick={async () => { const r = await run(() => api(`/v1/clinic/templates/${t.id}/approve`, { method: "POST" }), "Approved. This wording is used from now on."); if (r) await templates.reload(); }}>Approve this wording</button> : null}
                        </span>
                      ) : null}
                      {draftFor?.id === t.id ? (
                        <div className="stack">
                          <textarea value={draftBody} onChange={(e) => setDraftBody(e.target.value)} />
                          <span className="small muted">Keep the placeholders in braces: {t.placeholders.map((p) => `{${p}}`).join(" ") || "none"}.</span>
                          <span className="row">
                            <button className="btn btn--small" disabled={busy} onClick={draft}>Save draft</button>
                            <button className="btn btn--ghost btn--small" onClick={() => setDraftFor(null)}>Cancel</button>
                          </span>
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              </details>
            ))}
          </section>
        ) : null}
      </div>
    </>
  );
}
