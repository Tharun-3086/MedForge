"use client";

import { Fragment } from "react";

import { PageHead } from "@/components/staff-shell";
import { ErrorNote, Loading } from "@/components/ui";
import { useApi } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useStaff } from "@/lib/staff-context";

type Metric = { name: string; numerator: number; denominator: number; value: number | null; definition: string };
type Metrics = {
  data_label: string; today: string; metrics: Metric[];
  tasks: { open: number; escalated: number; median_hours_to_close: number | null; p90_hours_to_close: number | null; oldest_open_hours: number };
  messages: Record<string, number>;
  cost: { messages_sent: number; unit_cost_inr: number; estimated_messaging_cost_inr: number; completed_follow_ups: number; cost_per_completed_follow_up_inr: number | null; note: string };
};
type Ops = {
  messages: Record<string, number>; stuck_queued: number; replies: Record<string, number>; provider_events: Record<string, number>;
  duplicate_events_ignored: number; extractions: Record<string, number>; tasks_past_due: number; checked_at: string;
  providers: { llm: { active: string }; asr: { active: string }; tts: { active: string }; documents: { vision: string | null; local_ocr: string } };
};

const MESSAGE_LABEL: Record<string, string> = {
  SCHEDULED: "Scheduled", QUEUED: "Queued", SENDING: "Sending", SENT_TO_PROVIDER: "Sent, not confirmed", DELIVERED: "Delivered",
  FAILED: "Failed", SUPPRESSED: "Suppressed", UNKNOWN: "Unknown",
};

export default function MetricsPage() {
  const { me } = useStaff();
  const { data, error, loading } = useApi<Metrics>("/v1/metrics");
  const ops = useApi<Ops>(["ADMIN", "OPERATOR"].includes(me.user.role) ? "/v1/ops/health" : null);

  return (
    <>
      <PageHead title="Metrics" lede="Measured from recorded events only. Each number shows how it was counted." />
      <ErrorNote error={error} />
      {loading && !data ? <Loading /> : null}
      {data ? (
        <div className="stack-l">
          <p className="notice notice--warn">{data.data_label}.</p>
          <section className="panel">
            {data.metrics.map((m) => (
              <div key={m.name} className="metric">
                <div className="stack" style={{ gap: 2 }}>
                  <b>{m.name}</b>
                  <span className="small muted">{m.definition}</span>
                </div>
                <div>
                  <div className="val">{m.value === null ? "n/a" : `${Math.round(m.value * 100)}%`}</div>
                  <div className="frac">{m.numerator} of {m.denominator}</div>
                </div>
                <div className="bar-track" aria-hidden="true"><div className="bar-fill" style={{ width: `${(m.value ?? 0) * 100}%` }} /></div>
              </div>
            ))}
          </section>
          <div className="cols-3">
            <section className="panel stack">
              <h2 style={{ fontSize: 17 }}>Tasks</h2>
              <dl className="kv">
                <dt>Open</dt><dd>{data.tasks.open}</dd>
                <dt>Escalated (no owner, past due)</dt><dd>{data.tasks.escalated}</dd>
                <dt>Median time to close</dt><dd>{data.tasks.median_hours_to_close === null ? "none closed yet" : `${data.tasks.median_hours_to_close} h`}</dd>
                <dt>90th percentile</dt><dd>{data.tasks.p90_hours_to_close === null ? "n/a" : `${data.tasks.p90_hours_to_close} h`}</dd>
                <dt>Oldest open</dt><dd>{data.tasks.open === 0 ? "none open" : data.tasks.oldest_open_hours < 1 ? "under 1 h" : `${data.tasks.oldest_open_hours} h`}</dd>
              </dl>
            </section>
            <section className="panel stack">
              <h2 style={{ fontSize: 17 }}>Messages by status</h2>
              <dl className="kv">
                {Object.entries(data.messages).filter(([, n]) => n > 0).map(([k, n]) => (<Fragment key={k}><dt>{MESSAGE_LABEL[k] ?? k}</dt><dd>{n}</dd></Fragment>))}
              </dl>
            </section>
            <section className="panel stack">
              <h2 style={{ fontSize: 17 }}>Messaging cost estimate</h2>
              <dl className="kv">
                <dt>Messages sent</dt><dd>{data.cost.messages_sent}</dd>
                <dt>Rate used</dt><dd>₹{data.cost.unit_cost_inr} per message</dd>
                <dt>Estimated cost</dt><dd>₹{data.cost.estimated_messaging_cost_inr}</dd>
                <dt>Per completed follow-up</dt><dd>{data.cost.cost_per_completed_follow_up_inr === null ? "no completed follow-ups yet" : `₹${data.cost.cost_per_completed_follow_up_inr}`}</dd>
              </dl>
              <p className="small muted">{data.cost.note}</p>
            </section>
          </div>
          {ops.data ? (
            <section className="panel stack">
              <div className="spread">
                <h2 style={{ fontSize: 17 }}>System health</h2>
                <span className="small muted">Checked {fmtDateTime(ops.data.checked_at)}. No patient details are shown here.</span>
              </div>
              <div className="cols-3">
                <dl className="kv">
                  <dt>Stuck in queue over 2 min</dt><dd>{ops.data.stuck_queued}</dd>
                  <dt>Tasks past due</dt><dd>{ops.data.tasks_past_due}</dd>
                  <dt>Duplicate events ignored</dt><dd>{ops.data.duplicate_events_ignored}</dd>
                </dl>
                <dl className="kv">
                  {Object.entries(ops.data.replies).map(([k, n]) => (<Fragment key={k}><dt>Replies {k.toLowerCase().replace(/_/g, " ")}</dt><dd>{n}</dd></Fragment>))}
                </dl>
                <dl className="kv">
                  <dt>Understanding</dt><dd>{ops.data.providers.llm.active}</dd>
                  <dt>Speech to text</dt><dd>{ops.data.providers.asr.active}</dd>
                  <dt>Document reading</dt><dd>{ops.data.providers.documents.vision ?? "local"}, OCR {ops.data.providers.documents.local_ocr}</dd>
                </dl>
              </div>
            </section>
          ) : null}
        </div>
      ) : null}
    </>
  );
}
