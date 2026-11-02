"use client";

import Link from "next/link";
import { Fragment, useState } from "react";

import { SUPPRESSED, templateName } from "@/components/outcomes";
import { PageHead } from "@/components/staff-shell";
import { Empty, ErrorNote, Loading, MessageStatus, useAction } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useStaff } from "@/lib/staff-context";
import type { Message } from "@/lib/types";

const GROUP_HINT: Record<string, string> = {
  attention: "The provider rejected these or their status is unknown. Each one also opened a task.",
  sent: "Latest first. “Delivered” only after the provider confirms it.",
  upcoming: "Soonest first. Quiet hours, opt-outs and confirmations are checked again just before sending.",
  not_sent: "Held back on purpose, for example after an opt-out.",
};

type Group = { key: string; title: string; total: number; messages: Message[] };
type Listing = { groups: Group[]; counts: Record<string, number> };

export default function MessagesPage() {
  const { refreshCounts } = useStaff();
  const [group, setGroup] = useState("");
  const { data, error, loading, reload } = useApi<Listing>(`/v1/messages${group ? `?group=${group}` : ""}`);
  const all = useApi<Listing>("/v1/messages?limit=1");
  const { busy, run } = useAction();

  async function retry(m: Message) {
    const r = await run(() => api<Message>(`/v1/messages/${m.id}/retry`, { method: "POST" }), "Queued again.");
    if (r) {
      await Promise.all([reload(), all.reload()]);
      refreshCounts();
    }
  }

  const tabs = all.data?.groups ?? [];

  return (
    <>
      <PageHead title="Messages"
        lede="Every message the clinic sends, with its real status. A failed message is never shown as sent." />
      <div className="filters" role="group" aria-label="Show">
        <button className="filter" aria-pressed={group === ""} onClick={() => setGroup("")}>Overview</button>
        {tabs.filter((g) => g.total > 0).map((g) => (
          <button key={g.key} className="filter" aria-pressed={group === g.key} onClick={() => setGroup(g.key)}>
            {g.title} <b>{g.total}</b>
          </button>
        ))}
      </div>
      <ErrorNote error={error} />
      {loading && !data ? <Loading /> : null}
      {data && data.groups.every((g) => g.messages.length === 0) ? (
        <div className="panel"><Empty title="No messages yet">Reminders appear here once a follow-up plan is approved.</Empty></div>
      ) : null}
      {data ? (
        <div className="panel panel--flush">
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Patient</th><th>Message</th><th>Status</th><th>When</th><th /></tr></thead>
              <tbody>
                {data.groups.filter((g) => g.messages.length > 0).map((g) => (
                  <Fragment key={g.key}>
                    <tr className="group-row">
                      <th colSpan={5} scope="colgroup">
                        <span className="group-title">{g.title}</span>
                        <span className="small muted"> {g.total} in all. {GROUP_HINT[g.key]}</span>
                        {!group && g.total > g.messages.length ? (
                          <button className="btn btn--ghost btn--small" onClick={() => setGroup(g.key)}>Show all {g.total}</button>
                        ) : null}
                      </th>
                    </tr>
                    {g.messages.map((m) => (
                      <tr key={m.id} className={m.status === "FAILED" ? "is-bad" : undefined}>
                        <td className="nowrap">
                          <Link href={`/patients/${m.patient_id}`}>{m.patient_name}</Link>
                          <span className="small muted" style={{ display: "block" }}>{m.simulated ? "Simulated phone" : m.channel.toLowerCase()}, {m.language}</span>
                        </td>
                        <td style={{ maxWidth: 460 }}>
                          <span className="small muted" style={{ display: "block" }}>{templateName(m.template_key)}{m.essential ? ", essential" : ""}</span>
                          {m.body}
                        </td>
                        <td>
                          <MessageStatus status={m.status} label={m.status_label} />
                          {m.suppressed_reason ? <span className="small muted" style={{ display: "block" }}>{SUPPRESSED[m.suppressed_reason] ?? m.suppressed_reason.toLowerCase().replace(/_/g, " ")}</span> : null}
                          {m.last_error_code ? <span className="small" style={{ display: "block", color: "var(--alarm)" }}>{m.last_error_code.toLowerCase().replace(/_/g, " ")}</span> : null}
                        </td>
                        <td className="small nowrap">
                          {m.status === "SCHEDULED" || m.status === "QUEUED" ? `Due ${fmtDateTime(m.scheduled_for)}` : fmtDateTime(m.failed_at ?? m.delivered_at ?? m.sent_at ?? m.created_at)}
                        </td>
                        <td>{m.status === "FAILED" ? <button className="btn btn--quiet btn--small" disabled={busy} onClick={() => retry(m)}>Retry</button> : null}</td>
                      </tr>
                    ))}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </>
  );
}
